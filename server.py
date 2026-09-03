#!/usr/bin/env python3
"""Hoplite Unified Proxy Gateway — key rotation, health checks, dashboard API."""

import asyncio
import json
import time
import uuid
import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from httpx import TimeoutException as HttpxTimeoutException
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("hoplite-gateway")

DATA_DIR = Path(__file__).parent / "data"
STATIC_DIR = Path(__file__).parent / "static"
STORE_PATH = DATA_DIR / "store.json"
HOPLITE_API = "https://api.hoplite.sh"
PROJECT_ID = "proj_eec8a38028764dd3a00ed16ce02d0f5b"  # From existing proxy

# ---------------------------------------------------------------------------
# Store management (single lock for read-modify-write safety)
# ---------------------------------------------------------------------------
_store_lock = asyncio.Lock()


def load_store() -> dict:
    with open(STORE_PATH) as f:
        return json.load(f)


def save_store(data: dict) -> None:
    with open(STORE_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


async def atomic_store_update(fn):
    """Run fn(store_dict) under lock, then persist."""
    async with _store_lock:
        store = load_store()
        fn(store)
        save_store(store)
        return store


# ---------------------------------------------------------------------------
# SSE event bus
# ---------------------------------------------------------------------------
class EventBus:
    def __init__(self):
        self._queues: list[asyncio.Queue] = []
        self._history: list[dict] = []  # ring buffer for late joiners

    def publish(self, event: str, data: dict):
        payload = {"event": event, "data": data}
        self._history.append(payload)
        if len(self._history) > 200:
            self._history = self._history[-200:]
        for q in self._queues:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue(maxsize=256)
        self._queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._queues = [x for x in self._queues if x is not q]

    def recent(self, count: int = 50) -> list[dict]:
        return self._history[-count:]


bus = EventBus()

# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------
def mask_key(key: str) -> str:
    if len(key) <= 12:
        return key[:4] + "…" + key[-4:]
    return key[:8] + "…" + key[-4:]


async def get_live_key() -> dict:
    """Return the first live key, or raise 503."""
    async with _store_lock:
        store = load_store()
        live = [k for k in store["keys"] if k["status"] == "live"]
    if not live:
        raise HTTPException(status_code=503, detail="No live API keys available")
    return live[0]


async def test_key(api_key: str) -> dict:
    """Quick liveness probe via /api/model-providers with retries."""
    last_error = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{HOPLITE_API}/api/model-providers",
                    headers={"X-Api-Key": api_key},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    models = len(data.get("models", [])) if isinstance(data, dict) else 0
                    return {"alive": True, "models": models, "error": None}
                if resp.status_code == 429:
                    last_error = f"rate_limited_{resp.status_code}"
                    await asyncio.sleep(2 ** attempt)
                    continue
                last_error = f"HTTP_{resp.status_code}"
        except (HttpxTimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
            last_error = f"timeout_{type(exc).__name__}"
            await asyncio.sleep(2 ** attempt)
        except Exception as exc:
            last_error = str(exc)[:100]
            await asyncio.sleep(2 ** attempt)

    return {"alive": False, "models": 0, "error": last_error}


async def mark_key_dead(key: dict, error: str):
    async with _store_lock:
        store = load_store()
        for k in store["keys"]:
            if k["id"] == key["id"]:
                k["status"] = "dead"
                k["last_checked"] = datetime.now(timezone.utc).isoformat()
        save_store(store)
    bus.publish("key_dead", {"label": key["label"], "error": error})
    logger.warning("Key %s marked dead: %s", key["label"], error)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Hoplite Gateway", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    store = load_store()
    live = [k for k in store["keys"] if k["status"] == "live"]
    return {
        "status": "ok" if live else "degraded",
        "service": "hoplite-gateway",
        "keys_total": len(store["keys"]),
        "keys_live": len(live),
    }


# ---------------------------------------------------------------------------
# Proxy: /v1/models
# ---------------------------------------------------------------------------
@app.get("/v1/models")
async def proxy_models():
    key = await get_live_key()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{HOPLITE_API}/api/model-providers",
            headers={"X-Api-Key": key["key"]},
        )
        if resp.status_code not in (200, 201):
            await mark_key_dead(key, f"HTTP {resp.status_code}")
            raise HTTPException(502, f"Upstream error: {resp.status_code}")

        data = resp.json()
        models_list = []
        for m in data.get("models", []):
            models_list.append({
                "id": m["id"],
                "object": "model",
                "created": int(time.time()),
                "owned_by": m.get("provider", "hoplite"),
            })
        return {"object": "list", "data": models_list}


# ---------------------------------------------------------------------------
# Proxy: /v1/chat/completions
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    model: str
    messages: list[dict]
    max_tokens: Optional[int] = 1024
    temperature: Optional[float] = 0.7
    stream: Optional[bool] = False


@app.post("/v1/chat/completions")
async def proxy_chat(body: ChatRequest):
    key = await get_live_key()
    model = body.model or "claude-haiku-4-5"
    prompt = "\n".join(f"{m['role']}: {m.get('content', '')}" for m in body.messages)

    async with httpx.AsyncClient(timeout=30) as client:
        # Create thread
        tid = f"gw_{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            f"{HOPLITE_API}/api/threads",
            headers={"X-Api-Key": key["key"], "Content-Type": "application/json"},
            json={
                "projectId": PROJECT_ID,
                "title": f"Gateway: {tid}",
                "prompt": prompt,
                "model": model,
            },
        )

        if resp.status_code not in (200, 201):
            if resp.status_code in (401, 403):
                await mark_key_dead(key, f"HTTP {resp.status_code}")
            raise HTTPException(502, f"Thread creation failed: {resp.status_code}")

        result = resp.json()
        thread_id = result.get("thread", {}).get("id")
        if not thread_id:
            raise HTTPException(502, "No thread ID in response")

        # Poll for completion
        content = ""
        for _ in range(60):
            await asyncio.sleep(2)
            poll_resp = await client.get(
                f"{HOPLITE_API}/api/threads/{thread_id}",
                headers={"X-Api-Key": key["key"]},
            )
            if poll_resp.status_code != 200:
                continue
            tdata = poll_resp.json()
            status = tdata.get("thread", {}).get("status")
            if status in ("ready", "failed"):
                msgs_resp = await client.get(
                    f"{HOPLITE_API}/api/threads/{thread_id}/messages",
                    headers={"X-Api-Key": key["key"]},
                )
                if msgs_resp.status_code == 200:
                    msgs = msgs_resp.json().get("messages", [])
                    for msg in reversed(msgs):
                        if msg.get("role") == "assistant" and msg.get("content"):
                            content = msg.get("content", "")
                            break
                break

    if body.stream:
        async def stream_gen():
            if content:
                chunk = {
                    "id": f"chatcmpl-{tid}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }],
                }
                yield f"data: {json.dumps(chunk)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(stream_gen(), media_type="text/event-stream")

    return JSONResponse(content={
        "id": f"chatcmpl-{tid}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    })


# ---------------------------------------------------------------------------
# Key Management API
# ---------------------------------------------------------------------------
@app.get("/api/keys")
def list_keys():
    keys = load_store()["keys"]
    # Mask keys in the response
    return [
        {**{kk: vv for kk, vv in k.items() if kk != "key"}, "key": mask_key(k["key"])}
        for k in keys
    ]


@app.post("/api/keys")
def add_key(key_data: dict):
    key_data["id"] = key_data.get("id", f"key_{int(time.time())}")
    key_data.setdefault("status", "untested")
    key_data.setdefault("credits_total", 0)
    key_data.setdefault("credits_used", 0)
    key_data.setdefault("last_checked", None)

    store = load_store()
    store["keys"].append(key_data)
    save_store(store)
    bus.publish("key_added", {"label": key_data.get("label", key_data["id"])})
    return {**key_data, "key": mask_key(key_data["key"])}


@app.delete("/api/keys/{key_id}")
def delete_key(key_id: str):
    store = load_store()
    before = len(store["keys"])
    store["keys"] = [k for k in store["keys"] if k["id"] != key_id]
    if len(store["keys"]) == before:
        raise HTTPException(status_code=404, detail="Key not found")
    save_store(store)
    bus.publish("key_removed", {"key_id": key_id})
    return {"ok": True}


@app.post("/api/keys/{key_id}/test")
async def test_key_endpoint(key_id: str):
    store = load_store()
    key = next((k for k in store["keys"] if k["id"] == key_id), None)
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")

    bus.publish("status", {"text": f"Testing key {key['label']}…"})
    result = await test_key(key["key"])

    async with _store_lock:
        store = load_store()
        for k in store["keys"]:
            if k["id"] == key_id:
                k["status"] = "live" if result["alive"] else "dead"
                k["last_checked"] = datetime.now(timezone.utc).isoformat()
                if result["alive"]:
                    k["models_count"] = result["models"]
        save_store(store)

    bus.publish("key_tested", {
        "label": key["label"],
        "alive": result["alive"],
        "models": result["models"],
    })
    return {**key, "test_result": result}


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------
@app.get("/api/stats")
def stats():
    store = load_store()
    live = [k for k in store["keys"] if k["status"] == "live"]
    return {
        "keys_total": len(store["keys"]),
        "keys_live": len(live),
        "keys_dead": len(store["keys"]) - len(live),
        "total_credits": sum(k.get("credits_total", 0) for k in store["keys"]),
        "used_credits": sum(k.get("credits_used", 0) for k in store["keys"]),
        "uptime": "online",
    }


# ---------------------------------------------------------------------------
# SSE Events
# ---------------------------------------------------------------------------
@app.get("/api/events")
async def events():
    q = bus.subscribe()

    async def gen():
        try:
            # Initial stats snapshot
            yield {"event": "stats", "data": json.dumps(stats())}
            # Replay recent history
            for msg in bus.recent(30):
                yield msg
            while True:
                msg = await q.get()
                yield msg
        except asyncio.CancelledError:
            pass
        finally:
            bus.unsubscribe(q)

    return EventSourceResponse(gen())


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
@app.get("/api/settings")
def get_settings():
    return load_store().get("settings", {})


@app.patch("/api/settings")
def update_settings(body: dict):
    store = load_store()
    store.setdefault("settings", {})
    allowed = {"rotation", "health_check_interval"}
    store["settings"].update({k: v for k, v in body.items() if k in allowed})
    save_store(store)
    bus.publish("settings_updated", store["settings"])
    return store["settings"]


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------
@app.get("/api/cards")
def list_cards():
    store = load_store()
    cards = store.get("cards", [])
    # Mask card numbers for safety
    masked = []
    for c in cards:
        mc = dict(c)
        num = mc.get("number", "")
        if len(num) >= 8:
            mc["number"] = num[:4] + "••••••" + num[-4:]
        mc.pop("cvv", None)  # Never expose CVV via API
        masked.append(mc)
    return masked


# ---------------------------------------------------------------------------
# GitHub Accounts
# ---------------------------------------------------------------------------
@app.get("/api/github")
def list_github():
    store = load_store()
    return store.get("github_accounts", [])


# ---------------------------------------------------------------------------
# Static files + dashboard
# ---------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/dashboard")
def dashboard():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/")
def root():
    return FileResponse(STATIC_DIR / "index.html")


# ---------------------------------------------------------------------------
# Background health-check loop
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    asyncio.create_task(_health_check_loop())


async def _health_check_loop():
    """Periodically probe every key and update status."""
    # Track consecutive failures
    _failure_counts = {}

    while True:
        store = load_store()
        interval = store.get("settings", {}).get("health_check_interval", 3600)
        await asyncio.sleep(interval)

        store = load_store()
        for key in store["keys"]:
            if key["status"] == "dead":
                # Try to revive dead keys
                result = await test_key(key["key"])
                if result["alive"]:
                    key["status"] = "live"
                    logger.info("Key %s revived", key["label"])
                    bus.publish("key_status_change", {
                        "label": key["label"], "old": "dead", "new": "live"
                    })
                continue

            result = await test_key(key["key"])
            key["last_checked"] = datetime.now(timezone.utc).isoformat()

            if not result["alive"]:
                kid = key["id"]
                _failure_counts[kid] = _failure_counts.get(kid, 0) + 1
                if _failure_counts.get(kid, 0) >= 3:
                    key["status"] = "dead"
                    bus.publish("key_status_change", {
                        "label": key["label"], "old": "live", "new": "dead",
                        "error": result.get("error"),
                    })
                    logger.warning("Key %s marked dead after 3 failures: %s", key["label"], result.get("error"))
                    _failure_counts[kid] = 0
            else:
                _failure_counts[key["id"]] = 0  # Reset on success

        async with _store_lock:
            save_store(store)