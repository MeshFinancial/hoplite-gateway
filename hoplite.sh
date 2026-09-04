#!/usr/bin/env bash
# =========================================================================
# Hoplite.sh LiteLLM Gateway & Auto-Registration Manager
# =========================================================================
# Usage:
#   ./hoplite.sh start [port]              Start OpenAI-compatible proxy gateway
#   ./hoplite.sh stop                      Stop background gateway process
#   ./hoplite.sh status                    Show key pool and gateway status
#   ./hoplite.sh autoreg [--count N]       Run auto-reg + Stripe card pipeline
#   ./hoplite.sh add-key <hop_...>         Ingest an existing Hoplite API key
#   ./hoplite.sh test [model]              Run test chat completion
# =========================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()   { echo -e "${RED}[ERR]${NC} $*" >&2; }

check_python() {
    if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
        err "Python 3 is required."
        exit 1
    fi
}

PY="python3"
if ! command -v python3 &>/dev/null; then
    PY="python"
fi

case "${1:-help}" in
    start)
        shift
        PORT="${1:-8085}"
        check_python
        echo -e "${GREEN}${BOLD}════════════════════════════════════════════════════════════${NC}"
        echo -e "${GREEN}${BOLD}  Hoplite LiteLLM Gateway v2                                ${NC}"
        echo -e "${GREEN}${BOLD}  Proxy:      http://localhost:$PORT/v1/chat/completions     ${NC}"
        echo -e "${GREEN}${BOLD}  Models:     http://localhost:$PORT/v1/models               ${NC}"
        echo -e "${GREEN}${BOLD}  Health:     http://localhost:$PORT/health                  ${NC}"
        echo -e "${GREEN}${BOLD}  Auth Key:   sk-hoplite-gateway                            ${NC}"
        echo -e "${GREEN}${BOLD}════════════════════════════════════════════════════════════${NC}"
        PORT="$PORT" $PY server.py
        ;;

    stop)
        check_python
        info "Stopping running gateway on port 8085..."
        $PY -c "
import os, psutil
for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        cmd = ' '.join(p.info['cmdline'] or [])
        if 'server.py' in cmd or 'hoplite_gateway.py' in cmd:
            print(f'Killing PID {p.info[\"pid\"]}')
            p.kill()
    except Exception:
        pass
" 2>/dev/null || true
        ok "Stopped."
        ;;

    status)
        check_python
        $PY autoreg_pipeline.py --status
        ;;

    add-key)
        shift
        if [ -z "${1:-}" ]; then
            err "Usage: ./hoplite.sh add-key <hop_...> [--project-id <id>] [--label <name>]"
            exit 1
        fi
        KEY="$1"; shift
        PROJECT_ID=""
        LABEL="manual"
        while [ $# -gt 0 ]; do
            case "$1" in
                --project-id) PROJECT_ID="$2"; shift 2 ;;
                --label) LABEL="$2"; shift 2 ;;
                *) shift ;;
            esac
        done
        check_python
        info "Adding key: ${KEY:0:16}..."
        $PY autoreg_pipeline.py --add-key "$KEY" ${PROJECT_ID:+--project-id "$PROJECT_ID"} --label "$LABEL"
        ok "Key ingested into store.json and .env"
        ;;

    autoreg)
        shift
        check_python
        info "Running automated registration pipeline..."
        $PY autoreg_pipeline.py "$@"
        ;;

    test)
        shift
        MODEL="${1:-deepseek/deepseek-v4-flash-0731}"
        check_python
        info "Testing chat completion via gateway (model: $MODEL)..."
        $PY -c "
import requests, json
url = 'http://localhost:8085/v1/chat/completions'
headers = {'Authorization': 'Bearer sk-hoplite-gateway', 'Content-Type': 'application/json'}
payload = {
    'model': '$MODEL',
    'messages': [{'role': 'user', 'content': 'Respond with: HOPLITE_PROXY_ONLINE'}]
}
try:
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    print('Status:', r.status_code)
    if r.status_code == 200:
        data = r.json()
        print('Response:', data['choices'][0]['message']['content'])
    else:
        print('Error:', r.text)
except Exception as e:
    print('Connection error (is gateway running? ./hoplite.sh start):', e)
"
        ;;

    help|--help|-h)
        echo "Hoplite.sh LiteLLM Gateway & Auto-Registration CLI"
        echo ""
        echo "Commands:"
        echo "  ./hoplite.sh start [port]        Start gateway server (default :8085)"
        echo "  ./hoplite.sh stop                Stop running gateway"
        echo "  ./hoplite.sh status              Show key pool, live count, project IDs"
        echo "  ./hoplite.sh autoreg [--count N] Run auto-registration with card payment"
        echo "  ./hoplite.sh add-key <hop_...>   Add existing key to pool"
        echo "  ./hoplite.sh test [model]        Test gateway with OpenAI chat completion"
        echo ""
        echo "Gateway endpoints (OpenAI / LiteLLM format):"
        echo "  POST http://localhost:8085/v1/chat/completions"
        echo "  GET  http://localhost:8085/v1/models"
        echo "  GET  http://localhost:8085/health"
        echo "  Auth: Bearer sk-hoplite-gateway"
        ;;

    *)
        err "Unknown command: $1"
        echo "Usage: ./hoplite.sh {start|stop|status|autoreg|add-key|test|help}"
        exit 1
        ;;
esac
