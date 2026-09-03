#!/usr/bin/env bash
# Hoplite Unified Proxy Gateway — launch script
set -euo pipefail

cd "$(dirname "$0")"

PORT="$(python3 -c 'import json; print(json.load(open("data/store.json")).get("settings", {}).get("port", 8090))' 2>/dev/null || echo 8090)"

exec python3 -m uvicorn server:app --host 127.0.0.1 --port "${PORT}" "$@"
