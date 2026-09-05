#!/usr/bin/env python3
"""
Hoplite Gateway v2 & Studio Server — LiteLLM-Style Dashboard
═════════════════════════════════════════════════════════════════════
- Web Dashboard at http://localhost:8085/ and /dashboard
- Endpoints & Virtual Keys Management:
    GET/POST/DELETE /api/endpoints
    GET             /api/endpoints/<ep_id>/stats
- Upstream Hoplite Key Pool:
    GET/POST/DELETE /api/keys
- GitHub Accounts Pool:
    GET             /api/accounts
    POST            /api/accounts/import
    POST            /api/accounts/delete
- Autoreg Pipeline Worker:
    POST            /api/autoreg/start
    POST            /api/autoreg/stop
    GET             /api/autoreg/status
- Settings & Config:
    GET/POST        /api/config
    GET             /api/captcha/balance
- Sandbox Proxy:
    POST            /v1/sandbox/execute
- OpenAI / LiteLLM Proxy API:
    POST            /v1/chat/completions (SSE streaming + tool use)
    GET             /v1/models
    GET             /health
═════════════════════════════════════════════════════════════════════
"""

import os
import sys
import json
import time
import uuid
import threading
import subprocess
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")
from typing import Optional, Tuple, Dict, Any, List
from collections import defaultdict
from datetime import datetime

from flask import Flask, request, Response, jsonify, send_from_directory, stream_with_context
from flask_cors import CORS
import requests

app = Flask(__name__, static_folder="static")
CORS(app)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
DATA_DIR.mkdir(parents=True, exist_ok=True)

STORE_PATH = DATA_DIR / "store.json"
SETTINGS_PATH = DATA_DIR / "settings.json"
ACCOUNTS_PATH = DATA_DIR / "gh_accounts.json"
KEYS_RECORD_PATH = DATA_DIR / "hoplite_keys.json"
ENDPOINTS_PATH = DATA_DIR / "endpoints.json"

HOPLITE_API = "https://api.hoplite.sh"
DEFAULT_GATEWAY_KEY = os.environ.get("GATEWAY_KEY", "sk-hop-gateway-8085")
FALLBACK_PROJECT_ID = os.environ.get("HOPLITE_PROJECT_ID", "proj_2857d93259a84fd9ac7dffe8dbae5330")

# Key rotation lock
_key_idx = 0
_key_lock = threading.Lock()

# Autoreg background process
_autoreg_proc = None
_autoreg_lock = threading.Lock()

# ── RPM Rate Limiter ──
# Per-key sliding window: { token: [timestamp1, timestamp2, ...] }
_rpm_tracker: Dict[str, list] = defaultdict(list)
_rpm_lock = threading.Lock()

def check_rpm(token: str) -> Tuple[bool, int]:
    """Check if `token` has exceeded its RPM limit. Returns (allowed, current_rpm)."""
    eps = load_endpoints()
    ep = next((e for e in eps if e.get("key") == token), None)
    if not ep:
        return True, 0
    limit = ep.get("rate_limit_rpm", 60)
    if limit <= 0:
        return True, 0

    now = time.time()
    with _rpm_lock:
        # Prune timestamps older than 60s
        window = now - 60
        ts_list = _rpm_tracker[token]
        _rpm_tracker[token] = [t for t in ts_list if t > window]
        current = len(_rpm_tracker[token])
        if current >= limit:
            return False, current
        _rpm_tracker[token].append(now)
        return True, current + 1


# ── Persistence Helpers ──

def load_store() -> dict:
    if STORE_PATH.exists():
        try:
            with open(STORE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"keys": [], "settings": {"port": 8085}}


def save_store(store: dict):
    with open(STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)


def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "card": {"number": "4874100085748500", "expiry": "05/30", "cvv": "674", "zip": "10001", "country": "US"},
        "captcha": {"provider": "anticaptcha", "key": "03ea83a89c837abf30695d43a93c0f29", "balance": 51.92},
        "proxies": [],
        "proxy_strategy": "direct"
    }


def save_settings(s: dict):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)


def load_endpoints() -> list:
    if ENDPOINTS_PATH.exists():
        try:
            with open(ENDPOINTS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # Default endpoint
    default_ep = [
        {
            "id": "ep_default",
            "name": "Production Hoplite Gateway",
            "key": DEFAULT_GATEWAY_KEY,
            "models": ["*"],
            "rate_limit_rpm": 60,
            "created_at": "2026-09-04T00:00:00Z"
        }
    ]
    save_endpoints(default_ep)
    return default_ep


def save_endpoints(eps: list):
    with open(ENDPOINTS_PATH, "w", encoding="utf-8") as f:
        json.dump(eps, f, indent=2, ensure_ascii=False)


def get_key() -> Tuple[Optional[str], Optional[str]]:
    global _key_idx
    store = load_store()
    live = [k for k in store.get("keys", []) if k.get("status") == "live" and k.get("key")]
    if live:
        with _key_lock:
            k = live[_key_idx % len(live)]
            _key_idx += 1
        return k["key"], k.get("projectId", FALLBACK_PROJECT_ID)

    # Fallback to .env
    keys_env = os.environ.get("HOPLITE_API_KEYS", "")
    if keys_env:
        ks = [x.strip() for x in keys_env.split(",") if x.strip()]
        if ks:
            with _key_lock:
                k = ks[_key_idx % len(ks)]
                _key_idx += 1
            return k, FALLBACK_PROJECT_ID
    return None, None


# ── Model Discovery & Cache ──
MODEL_CACHE = []
MODEL_CACHE_TTL = 300
MODEL_CACHE_TS = 0

def fetch_models():
    global MODEL_CACHE, MODEL_CACHE_TS
    now = time.time()
    if now - MODEL_CACHE_TS < MODEL_CACHE_TTL and MODEL_CACHE:
        return MODEL_CACHE
    try:
        key, _ = get_key()
        if not key:
            return MODEL_CACHE or [{"id": "deepseek/deepseek-v4-flash-0731", "object": "model"}]
        headers = {"X-Api-Key": key, "Content-Type": "application/json"}
        r = requests.get(f"{HOPLITE_API}/api/model-providers", headers=headers, timeout=15)
        data = r.json()
        models = []
        for m in data.get("models", []):
            models.append({
                "id": m["id"],
                "object": "model",
                "created": int(time.time()),
                "owned_by": m.get("provider", "hoplite"),
            })
        for fb in data.get("runConfig", {}).get("modelFallbackIds", []):
            if not any(mm["id"] == fb for mm in models):
                models.append({"id": fb, "object": "model", "created": int(time.time()), "owned_by": "hoplite"})
        MODEL_CACHE = models
        MODEL_CACHE_TS = now
        return models
    except Exception:
        return MODEL_CACHE or [{"id": "deepseek/deepseek-v4-flash-0731", "object": "model"}]


def hoplite_api(key: str, method: str, path: str, data: dict = None, timeout: int = 60):
    if not key:
        return {"error": "No API key available"}
    headers = {"X-Api-Key": key, "Content-Type": "application/json"}
    try:
        r = requests.request(method, f"{HOPLITE_API}{path}", headers=headers, json=data, timeout=timeout)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def create_thread(key: str, project_id: str, model: str, messages: list, tools: list = None):
    if not project_id:
        return None, "No project ID configured"

    prompt = ""
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if c.get("type") == "text")
        prompt += f"{role}: {content}\n"

    payload = {
        "projectId": project_id,
        "title": f"gw_{uuid.uuid4().hex[:8]}",
        "prompt": prompt.strip(),
        "model": model,
    }
    if tools:
        payload["tools"] = json.dumps(tools)

    result = hoplite_api(key, "POST", "/api/threads", payload, timeout=30)
    return result.get("thread", {}).get("id"), result.get("error")


def poll_thread(key: str, thread_id: str, timeout: int = 180):
    for _ in range(timeout):
        time.sleep(1)
        data = hoplite_api(key, "GET", f"/api/threads/{thread_id}", timeout=15)
        status = data.get("thread", {}).get("status", "unknown")
        if status in ("ready", "failed"):
            msgs = hoplite_api(key, "GET", f"/api/threads/{thread_id}/messages", timeout=15)
            for msg in reversed(msgs.get("messages", [])):
                if msg.get("role") == "assistant" and msg.get("content"):
                    return msg["content"], status
            return "", status
    return "", "timeout"


# ═════════════════════════════════════════════════════════════════
# ROUTES: Dashboard Web UI
# ═════════════════════════════════════════════════════════════════

@app.route("/", methods=["GET"])
@app.route("/dashboard", methods=["GET"])
def dashboard():
    return send_from_directory(STATIC_DIR, "index.html")


# ═════════════════════════════════════════════════════════════════
# ROUTES: OpenAI / LiteLLM Proxy
# ═════════════════════════════════════════════════════════════════

def resolve_token(auth_header: str) -> Optional[str]:
    """Extract bearer token from Authorization header."""
    if not auth_header:
        return None
    return auth_header.replace("Bearer ", "").strip()


def is_authorized(auth_header: str) -> bool:
    token = resolve_token(auth_header)
    if not token:
        return False
    # Check default gateway key
    if token == DEFAULT_GATEWAY_KEY:
        return True
    # Check virtual endpoints keys
    eps = load_endpoints()
    return any(ep.get("key") == token for ep in eps)


def require_auth():
    """Check Authorization header, return 401 if invalid."""
    auth = request.headers.get("Authorization", "")
    if not is_authorized(auth):
        return jsonify({"error": "Invalid API key"}), 401
    return None


@app.route("/health", methods=["GET"])
def health():
    key, pid = get_key()
    store = load_store()
    live = len([k for k in store.get("keys", []) if k.get("status") == "live"])
    return jsonify({
        "status": "ok" if key else "no_key",
        "service": "hoplite-gateway-v2",
        "keys_live": live,
        "keys_total": len(store.get("keys", [])),
        "project_id": pid or "unknown",
        "key_ok": key is not None
    })


@app.route("/v1/models", methods=["GET"])
def list_models():
    auth_err = require_auth()
    if auth_err:
        return auth_err
    return jsonify({"object": "list", "data": fetch_models()})


@app.route("/v1/chat/completions", methods=["POST"])
def chat_completions():
    auth_err = require_auth()
    if auth_err:
        return auth_err

    # RPM enforcement
    token = resolve_token(request.headers.get("Authorization", ""))
    if token:
        allowed, current = check_rpm(token)
        if not allowed:
            retry_after = 60
            resp = jsonify({
                "error": {
                    "message": f"Rate limit exceeded. Limit: {current} requests per minute",
                    "type": "rate_limit_error",
                    "code": "rate_limit_exceeded"
                }
            })
            resp.status_code = 429
            resp.headers["X-RateLimit-Limit"] = str(current)
            resp.headers["Retry-After"] = str(retry_after)
            return resp

    body = request.get_json(silent=True) or {}
    model = body.get("model", "deepseek/deepseek-v4-flash-0731")
    messages = body.get("messages", [])
    stream = body.get("stream", False)
    tools = body.get("tools", None)

    key, project_id = get_key()
    if not key or not project_id:
        return jsonify({"error": "No live keys available in pool"}), 503

    thread_id, error = create_thread(key, project_id, model, messages, tools)
    if error:
        return jsonify({"error": f"Thread creation failed: {error}"}), 502
    if not thread_id:
        return jsonify({"error": "No thread ID returned"}), 502

    if stream:
        return Response(
            stream_with_context(stream_completion(key, thread_id, model)),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        )
    else:
        content, status = poll_thread(key, thread_id)
        return jsonify({
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop" if status == "ready" else "error"
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        })


def stream_completion(key: str, thread_id: str, model: str):
    tid = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    yield f"data: {json.dumps({'id': tid, 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"

    full_content = ""
    for _ in range(180):
        time.sleep(1)
        data = hoplite_api(key, "GET", f"/api/threads/{thread_id}", timeout=15)
        status = data.get("thread", {}).get("status", "unknown")

        if status in ("ready", "failed"):
            msgs = hoplite_api(key, "GET", f"/api/threads/{thread_id}/messages", timeout=15)
            for msg in reversed(msgs.get("messages", [])):
                if msg.get("role") == "assistant" and msg.get("content"):
                    new_c = msg["content"]
                    delta = new_c[len(full_content):]
                    if delta:
                        yield f"data: {json.dumps({'id': tid, 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': model, 'choices': [{'index': 0, 'delta': {'content': delta}, 'finish_reason': None}]})}\n\n"
                    break
            yield f"data: {json.dumps({'id': tid, 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
            yield "data: [DONE]\n\n"
            return

        msgs = hoplite_api(key, "GET", f"/api/threads/{thread_id}/messages", timeout=15)
        for msg in reversed(msgs.get("messages", [])):
            if msg.get("role") == "assistant" and msg.get("content"):
                new_c = msg["content"]
                if len(new_c) > len(full_content):
                    delta = new_c[len(full_content):]
                    yield f"data: {json.dumps({'id': tid, 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': model, 'choices': [{'index': 0, 'delta': {'content': delta}, 'finish_reason': None}]})}\n\n"
                    full_content = new_c
                break

    yield f"data: {json.dumps({'id': tid, 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'error'}]})}\n\n"
    yield "data: [DONE]\n\n"


# ═════════════════════════════════════════════════════════════════
# ROUTES: Sandbox / Remote Server Proxy
# ═════════════════════════════════════════════════════════════════

@app.route("/v1/sandbox/execute", methods=["POST"])
def sandbox_execute():
    """Proxy a command to a Hoplite sandbox using cookies and project IDs.

    Expects JSON body:
    {
        "projectId": "proj_...",
        "command": "npm run build",
        "cookies": { "hoplite_session": "..." },
        "timeout": 60
    }
    """
    auth_err = require_auth()
    if auth_err:
        return auth_err

    body = request.get_json(silent=True) or {}
    project_id = body.get("projectId", "")
    command = body.get("command", "")
    cookies = body.get("cookies", {})
    timeout = min(int(body.get("timeout", 60)), 300)

    if not project_id:
        return jsonify({"error": "projectId is required"}), 400
    if not command:
        return jsonify({"error": "command is required"}), 400

    # Use an upstream key to authenticate the proxy request
    key, _ = get_key()
    if not key:
        return jsonify({"error": "No live upstream keys available"}), 503

    # Build sandbox execution request
    sandbox_url = f"{HOPLITE_API}/api/projects/{project_id}/sandbox/exec"
    headers = {
        "X-Api-Key": key,
        "Content-Type": "application/json",
    }
    if cookies:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())

    payload = {
        "command": command,
        "timeout": timeout,
    }

    try:
        r = requests.post(sandbox_url, headers=headers, json=payload, timeout=timeout + 5)
        result = r.json()
        return jsonify({
            "success": r.ok,
            "projectId": project_id,
            "command": command,
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "exitCode": result.get("exitCode", -1),
            "executionTime": result.get("executionTime", 0),
        })
    except requests.exceptions.Timeout:
        return jsonify({"error": "Sandbox execution timed out", "command": command}), 504
    except Exception as e:
        return jsonify({"error": f"Sandbox proxy error: {str(e)}"}), 502


# ═════════════════════════════════════════════════════════════════
# ROUTES: LiteLLM-Style Endpoints / Virtual Keys API
# ═════════════════════════════════════════════════════════════════

@app.route("/api/endpoints", methods=["GET"])
def api_get_endpoints():
    eps = load_endpoints()
    return jsonify({"endpoints": eps, "total": len(eps)})


@app.route("/api/endpoints", methods=["POST"])
def api_create_endpoint():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "Custom Gateway Key").strip()
    models = data.get("models", ["*"])
    rpm = int(data.get("rate_limit_rpm", 60))

    new_key = f"sk-hop-{uuid.uuid4().hex[:16]}"
    ep = {
        "id": f"ep_{uuid.uuid4().hex[:8]}",
        "name": name,
        "key": new_key,
        "models": models,
        "rate_limit_rpm": max(rpm, 1),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    eps = load_endpoints()
    eps.append(ep)
    save_endpoints(eps)
    return jsonify({"success": True, "endpoint": ep})


@app.route("/api/endpoints/<ep_id>", methods=["DELETE"])
def api_delete_endpoint(ep_id):
    eps = load_endpoints()
    eps = [e for e in eps if e.get("id") != ep_id]
    save_endpoints(eps)
    return jsonify({"success": True})


@app.route("/api/endpoints/<ep_id>/stats", methods=["GET"])
def api_endpoint_stats(ep_id):
    """Return RPM usage stats for a specific endpoint."""
    eps = load_endpoints()
    ep = next((e for e in eps if e.get("id") == ep_id), None)
    if not ep:
        return jsonify({"error": "Endpoint not found"}), 404

    token = ep.get("key", "")
    with _rpm_lock:
        now = time.time()
        window = now - 60
        ts_list = [t for t in _rpm_tracker.get(token, []) if t > window]
        current_rpm = len(ts_list)

    return jsonify({
        "id": ep_id,
        "name": ep.get("name"),
        "key_preview": token[:8] + "..." + token[-4:] if len(token) > 12 else token,
        "rate_limit_rpm": ep.get("rate_limit_rpm", 60),
        "current_rpm": current_rpm,
        "remaining": max(0, ep.get("rate_limit_rpm", 60) - current_rpm),
        "pct_used": round((current_rpm / max(ep.get("rate_limit_rpm", 1), 1)) * 100, 1),
    })


# ═════════════════════════════════════════════════════════════════
# ROUTES: Upstream Hoplite Key Pool
# ═════════════════════════════════════════════════════════════════

@app.route("/api/keys", methods=["GET"])
def api_get_keys():
    store = load_store()
    keys = store.get("keys", [])
    live = len([k for k in keys if k.get("status") == "live"])
    return jsonify({"keys": keys, "total": len(keys), "live_count": live})


@app.route("/api/keys", methods=["POST"])
def api_add_key():
    data = request.get_json(silent=True) or {}
    key = data.get("key", "").strip()
    label = data.get("label", "manual").strip()
    pid = data.get("projectId", "").strip() or None
    if not key:
        return jsonify({"error": "Key is required"}), 400

    sys.path.insert(0, str(BASE_DIR))
    from autoreg_pipeline import add_key_to_store
    ok = add_key_to_store(key, pid, label)
    if ok:
        return jsonify({"success": True, "message": "Key added successfully"})
    return jsonify({"error": "Key validation failed against api.hoplite.sh"}), 400


@app.route("/api/keys/<key_id>", methods=["DELETE"])
def api_delete_key(key_id):
    store = load_store()
    store["keys"] = [k for k in store.get("keys", []) if k.get("id") != key_id]
    save_store(store)
    return jsonify({"success": True})


# ═════════════════════════════════════════════════════════════════
# ROUTES: GitHub Accounts Pool
# ═════════════════════════════════════════════════════════════════

@app.route("/api/accounts", methods=["GET"])
def api_get_accounts():
    accounts = []
    if ACCOUNTS_PATH.exists():
        try:
            with open(ACCOUNTS_PATH, "r", encoding="utf-8") as f:
                accounts = json.load(f)
        except Exception:
            pass

    records = []
    if KEYS_RECORD_PATH.exists():
        try:
            with open(KEYS_RECORD_PATH, "r", encoding="utf-8") as f:
                records = json.load(f)
        except Exception:
            pass

    status_map = {r.get("login"): r.get("status") for r in records}
    formatted = []
    for a in accounts:
        formatted.append({
            "login": a.get("login"),
            "email": a.get("email"),
            "status": status_map.get(a.get("login"), "Ready")
        })
    return jsonify({"accounts": formatted, "total": len(formatted)})


@app.route("/api/accounts/import", methods=["POST"])
def api_import_accounts():
    data = request.get_json(silent=True) or {}
    text_data = data.get("text", "")
    new_accounts = []

    for line in text_data.strip().splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        parts = line.split(":")
        if len(parts) >= 4:
            new_accounts.append({
                "email": parts[0],
                "password": parts[1],
                "totp": parts[2],
                "login": parts[-1]
            })

    if not new_accounts:
        return jsonify({"error": "No valid accounts parsed. Expected: email:password:totp:login"}), 400

    existing = []
    if ACCOUNTS_PATH.exists():
        try:
            with open(ACCOUNTS_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass

    existing_logins = {a["login"] for a in existing}
    added = 0
    for a in new_accounts:
        if a["login"] not in existing_logins:
            existing.append(a)
            added += 1

    with open(ACCOUNTS_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    return jsonify({"success": True, "added": added, "total": len(existing)})


@app.route("/api/accounts/delete", methods=["POST"])
def api_delete_accounts():
    data = request.get_json(silent=True) or {}
    logins = data.get("logins", [])
    if not logins:
        return jsonify({"error": "No logins specified"}), 400

    existing = []
    if ACCOUNTS_PATH.exists():
        try:
            with open(ACCOUNTS_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass

    before = len(existing)
    existing = [a for a in existing if a.get("login") not in logins]
    removed = before - len(existing)

    with open(ACCOUNTS_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    return jsonify({"success": True, "removed": removed, "total": len(existing)})


# ═════════════════════════════════════════════════════════════════
# ROUTES: Config & Settings
# ═════════════════════════════════════════════════════════════════

@app.route("/api/config", methods=["GET"])
def api_get_config():
    return jsonify(load_settings())


@app.route("/api/config", methods=["POST"])
def api_save_config():
    data = request.get_json(silent=True) or {}
    s = load_settings()
    if "card" in data:
        s["card"] = data["card"]
    if "proxies" in data:
        s["proxies"] = data["proxies"]
    if "captcha" in data:
        s["captcha"] = data["captcha"]
    if "proxy_strategy" in data:
        s["proxy_strategy"] = data["proxy_strategy"]
    save_settings(s)
    return jsonify({"success": True, "settings": s})


@app.route("/api/captcha/balance", methods=["GET"])
def api_captcha_balance():
    s = load_settings()
    c = s.get("captcha", {})
    provider = c.get("provider", "anticaptcha")
    key = c.get("key", "03ea83a89c837abf30695d43a93c0f29")

    sys.path.insert(0, str(BASE_DIR))
    from captcha_solver import CaptchaSolver
    solver = CaptchaSolver(primary_provider=provider, key=key)
    bal = solver.get_balance()
    s["captcha"]["balance"] = bal
    save_settings(s)
    return jsonify({"provider": provider, "balance": bal})


# ═════════════════════════════════════════════════════════════════
# ROUTES: Autoreg Worker Control
# ═════════════════════════════════════════════════════════════════

@app.route("/api/autoreg/start", methods=["POST"])
def api_autoreg_start():
    global _autoreg_proc
    with _autoreg_lock:
        if _autoreg_proc and _autoreg_proc.poll() is None:
            return jsonify({"status": "running", "message": "Autoreg is already running"})

        data = request.get_json(silent=True) or {}
        count = data.get("count", 3)
        headful = data.get("headful", True)
        selected_logins = data.get("logins", [])

        cmd = [
            sys.executable,
            str(BASE_DIR / "autoreg_pipeline.py"),
            f"--count={count}"
        ]
        if headful:
            cmd.append("--headful")

        _autoreg_proc = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return jsonify({"status": "started", "message": f"Autoreg started for {count} account(s) (PID: {_autoreg_proc.pid})"})


@app.route("/api/autoreg/stop", methods=["POST"])
def api_autoreg_stop():
    global _autoreg_proc
    with _autoreg_lock:
        if _autoreg_proc and _autoreg_proc.poll() is None:
            _autoreg_proc.terminate()
            _autoreg_proc = None
            return jsonify({"status": "stopped", "message": "Autoreg worker stopped"})
    return jsonify({"status": "idle", "message": "No active worker to stop"})


@app.route("/api/autoreg/status", methods=["GET"])
def api_autoreg_status():
    global _autoreg_proc
    running = _autoreg_proc is not None and _autoreg_proc.poll() is None
    return jsonify({
        "running": running,
        "pid": _autoreg_proc.pid if running else None
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8085"))
    print(f"[+] Hoplite LiteLLM Gateway starting on :{port}")
    print(f"[+] Dashboard: http://localhost:{port}/")
    print(f"[+] Sandbox Proxy: POST http://localhost:{port}/v1/sandbox/execute")
    print(f"[+] RPM Enforcement: active on all virtual keys")
    app.run(host="0.0.0.0", port=port, threaded=True)