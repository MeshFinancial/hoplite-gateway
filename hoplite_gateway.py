#!/home/nikita/Projects/hermes-agent/venv/bin/python3
"""
Hoplite → OpenAI-compatible API Gateway
Maps OpenAI /v1/chat/completions to Hoplite Threads API.
Supports streaming, tool use, reasoning/thinking, multi-key auth.
"""

import asyncio
import json
import os
import time
import uuid
from typing import Any, AsyncGenerator, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

# ── Config ──────────────────────────────────────────────────────────────────
HOPLITE_API_BASE = "https://api.hoplite.sh"
HOPLITE_PROJECT_ID = os.getenv("HOPLITE_PROJECT_ID", "proj_ceff361de3aa45e2914dec2fc2c539be")
HOPLITE_API_KEYS = os.getenv("HOPLITE_API_KEYS",
    "hop_n-ipwqnW_-Qc2SkVKSnLjU-OTNLCcyApe5N5bW-BIZ8ugvAzcHeLJIODkgfRBwXN,"
    "hop_uweNV8AwbwB_U1nrJYi3x9nVgDYrhDysx5HZ_f-szotc1LkQteYj7OTQad5QNnjo"
).split(",")
GATEWAY_API_KEY = os.getenv("GATEWAY_API_KEY", "sk-hoplite-gateway")

# Model mapping: what user asks → Hoplite model IDs
MODEL_MAP = {
    "claude-sonnet-4-6": "claude-sonnet-4-6",
    "claude-sonnet-4": "claude-sonnet-4-6",
    "claude-sonnet-5": "claude-sonnet-5",
    "claude-opus-4-8": "claude-opus-4-8",
    "claude-opus-4": "claude-opus-4-8",
    "claude-haiku-4-5": "claude-haiku-4-5",
    "claude-haiku-4": "claude-haiku-4-5",
    "gpt-5-6": "gpt-5.6",
    "gpt-5.6": "gpt-5.6",
    "gpt-5": "gpt-5.6",
    "gpt-5-3-codex": "gpt-5.3-codex",
    "gpt-4o": "gpt-4o",
    "fable-5": "fable-5",
    # Default
    "default": "claude-sonnet-5",
}

# Reasoning mapping
REASONING_MAP = {
    None: "off",
    "off": "off",
    "none": "none",
    "low": "low",
    "medium": "medium",
    "high": "high",
}

# ── Pydantic models ─────────────────────────────────────────────────────────

class FunctionDef(BaseModel):
    name: str
    description: str = ""
    parameters: dict = {}

class ToolDef(BaseModel):
    type: str = "function"
    function: FunctionDef

class ChatMessage(BaseModel):
    role: str
    content: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[list[dict]] = None
    name: Optional[str] = None

class ChatRequest(BaseModel):
    model: str = "default"
    messages: list[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    tools: Optional[list[ToolDef]] = None
    tool_choice: Optional[str] = None
    reasoning_effort: Optional[str] = None

# ── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(title="Hoplite Gateway", version="1.0.0")
hoplite_key_idx = 0
hoplite_key_lock = asyncio.Lock()

def get_hoplite_key() -> str:
    global hoplite_key_idx
    k = HOPLITE_API_KEYS[hoplite_key_idx % len(HOPLITE_API_KEYS)]
    hoplite_key_idx += 1
    return k.strip()

async def hoplite_request(method: str, path: str, json_body: dict = None) -> dict:
    """Make a request to Hoplite API with key rotation."""
    key = get_hoplite_key()
    headers = {
        "X-Api-Key": key,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.request(
            method,
            f"{HOPLITE_API_BASE}{path}",
            headers=headers,
            json=json_body,
        )
        data = resp.json()
        if not data.get("ok", False):
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Hoplite API error: {data.get('error', 'unknown')}",
            )
        return data

def build_prompt(messages: list[ChatMessage], tools: list[ToolDef] = None) -> str:
    """Build a Hoplite prompt from OpenAI messages."""
    parts = []
    for m in messages:
        if m.role == "system":
            parts.append(f"System: {m.content}")
        elif m.role == "user":
            parts.append(f"User: {m.content}")
        elif m.role == "assistant":
            if m.content:
                parts.append(f"Assistant: {m.content}")
            if m.tool_calls:
                for tc in m.tool_calls:
                    fn = tc.get("function", {})
                    parts.append(f"[Tool call: {fn.get('name', '?')} args={fn.get('arguments', '')}]")
        elif m.role == "tool":
            parts.append(f"[Tool result ({m.name or '?'}): {m.content}]")
    
    if tools:
        parts.append("\n\nAvailable tools:")
        for t in tools:
            fn = t.function
            parts.append(f"\n- {fn.name}: {fn.description}")
            parts.append(f"  Parameters: {json.dumps(fn.parameters, indent=2)}")
        parts.append("\n\nIMPORTANT: You are a helpful assistant. Use the tools above when needed.")
    
    prompt = "\n".join(parts)
    
    # Add tool use instructions
    if tools:
        prompt += "\n\nWhen you need to use a tool, respond with a JSON tool call in this format: {\"tool\": \"name\", \"arguments\": {...}}"
    
    return prompt

def resolve_model(model: str) -> str:
    return MODEL_MAP.get(model.lower(), MODEL_MAP.get("default"))

def resolve_reasoning(effort: Optional[str]) -> dict:
    mode = REASONING_MAP.get(effort, "off")
    return {"mode": mode}

async def poll_thread(thread_id: str, run_id: str, poll_interval: float = 1.0, timeout: float = 120.0) -> list[dict]:
    """Poll a Hoplite thread until it completes."""
    start = time.time()
    last_msg_count = 0
    all_messages = []
    
    while time.time() - start < timeout:
        data = await hoplite_request("GET", f"/api/threads/{thread_id}")
        status = data["thread"]["status"]
        
        msgs_data = await hoplite_request("GET", f"/api/threads/{thread_id}/messages")
        messages = msgs_data.get("messages", [])
        
        if len(messages) > last_msg_count:
            all_messages = messages
            last_msg_count = len(messages)
        
        if status in ("ready", "failed", "archived"):
            break
        
        await asyncio.sleep(poll_interval)
    
    return all_messages

def to_openai_response(
    messages: list[dict],
    model: str,
    req_id: str,
    stream: bool = False,
) -> dict:
    """Convert Hoplite messages to OpenAI chat completion format."""
    # Find the last assistant message with kind=chat
    content = ""
    thinking = ""
    tool_calls = []
    
    for m in messages:
        kind = m.get("kind", "chat")
        role = m.get("role", "")
        c = m.get("content", "") or ""
        
        if role == "assistant" and kind == "chat":
            content = c
        elif kind == "thinking":
            thinking = c
        elif role == "tool" and kind == "tool":
            if m.get("toolCallId") and m.get("toolName"):
                # This is a tool invocation from the agent
                tool_calls.append({
                    "id": m["toolCallId"],
                    "type": "function",
                    "function": {
                        "name": m["toolName"],
                        "arguments": c or "{}",
                    }
                })
    
    response = {
        "id": req_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": content or None,
            },
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }
    
    if tool_calls:
        response["choices"][0]["message"]["tool_calls"] = tool_calls
        if not content:
            response["choices"][0]["message"]["content"] = None
        response["choices"][0]["finish_reason"] = "tool_calls"
    
    if thinking:
        response["choices"][0]["message"]["reasoning_content"] = thinking
    
    return response

async def create_and_poll_thread(
    prompt: str,
    model: str,
    reasoning: dict,
    title: str = "api-request",
) -> tuple[str, list[dict]]:
    """Create a Hoplite thread and poll for completion."""
    body = {
        "projectId": HOPLITE_PROJECT_ID,
        "prompt": prompt,
        "model": model,
        "speed": "standard",
        "reasoning": reasoning,
        "title": title,
    }
    
    data = await hoplite_request("POST", "/api/threads", body)
    thread_id = data["thread"]["id"]
    run_id = None
    if data.get("run"):
        run_id = data["run"]["id"]
    
    messages = await poll_thread(thread_id, run_id)
    return thread_id, messages

# ── Auth middleware ─────────────────────────────────────────────────────────

async def verify_auth(request: Request):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        key = auth[7:]
    else:
        key = request.headers.get("X-Api-Key", "")
    
    if key != GATEWAY_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

# ── Routes ──────────────────────────────────────────────────────────────────

@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {"id": k, "object": "model", "created": int(time.time())}
            for k in sorted(set(MODEL_MAP.values()))
        ]
    }

@app.get("/health")
async def health():
    """Check both gateway and upstream Hoplite."""
    try:
        h = await hoplite_request("GET", "/health")
        return {"status": "ok", "hoplite": h["service"], "version": h["version"]}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}

@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest, request: Request):
    await verify_auth(request)
    
    model = resolve_model(req.model)
    reasoning = resolve_reasoning(req.reasoning_effort)
    prompt = build_prompt(req.messages, req.tools)
    req_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    
    if req.stream:
        return StreamingResponse(
            stream_response(prompt, model, reasoning, req_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
    
    try:
        thread_id, messages = await create_and_poll_thread(prompt, model, reasoning)
        resp = to_openai_response(messages, model, req_id)
        resp["_thread_id"] = thread_id
        return JSONResponse(resp)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def stream_response(
    prompt: str, model: str, reasoning: dict, req_id: str
) -> AsyncGenerator[str, None]:
    """Pseudo-streaming: poll Hoplite and yield SSE chunks as messages arrive."""
    # First, yield a placeholder to start the stream
    yield f'data: {json.dumps({"id": req_id, "object": "chat.completion.chunk", "created": int(time.time()), "model": model, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})}\n\n'
    
    try:
        thread_id, messages = await create_and_poll_thread(prompt, model, reasoning)
        
        content = ""
        for m in messages:
            kind = m.get("kind", "chat")
            role = m.get("role", "")
            c = m.get("content", "") or ""
            
            if role == "assistant" and kind == "chat":
                if c and c != content:
                    delta = c[len(content):]
                    if delta:
                        yield f'data: {json.dumps({"id": req_id, "object": "chat.completion.chunk", "created": int(time.time()), "model": model, "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}]})}\n\n'
                    content = c
            
            elif role == "tool" and kind == "tool" and m.get("toolCallId") and m.get("toolName"):
                yield f'data: {json.dumps({"id": req_id, "object": "chat.completion.chunk", "created": int(time.time()), "model": model, "choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": m["toolCallId"], "type": "function", "function": {"name": m["toolName"], "arguments": m.get("content", "")}}]}, "finish_reason": None}]})}\n\n'
        
        yield f'data: {json.dumps({"id": req_id, "object": "chat.completion.chunk", "created": int(time.time()), "model": model, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})}\n\n'
    except Exception as e:
        yield f'data: {json.dumps({"error": str(e)})}\n\n'
    
    yield "data: [DONE]\n\n"

# ── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8085"))
    print(f"[+] Hoplite Gateway starting on :{port}")
    print(f"[+] Project: {HOPLITE_PROJECT_ID}")
    print(f"[+] API key: {GATEWAY_API_KEY}")
    print(f"[+] Models: {list(MODEL_MAP.keys())}")
    uvicorn.run(app, host="0.0.0.0", port=port)