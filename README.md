# Hoplite Gateway v2

OpenAI-compatible proxy for Hoplite API with streaming + tool use support.

## Setup
pip install -r requirements.txt

## Run
HOPLITE_KEY="hop_gO4kU9_J1vZzL9TcdQhWQZKGTJgHAm4iv__NOWUIWJFMXZ0BtApVRJYe0xJD3uO3" PORT=8091 python3 server.py

## API
- GET /v1/models - List models
- POST /v1/chat/completions - Chat (streaming + non-streaming)
- GET /health - Health check

## Auth
Header: Authorization: Bearer sk-hop-live
