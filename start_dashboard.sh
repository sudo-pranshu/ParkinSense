#!/usr/bin/env bash
# Start the ParkinSense dashboard. Independent of the runtime: start, stop or
# restart it at any time; without a runtime it shows recorded sessions and an
# explicit "runtime offline" state.
set -euo pipefail
source "$(dirname "$0")/scripts/launch_common.sh"

usage() { cat <<'H'
Usage: ./start_dashboard.sh [--port N] [--host H] [--api URL]

  --port N    dashboard port (default 8050)
  --host H    bind address (default 127.0.0.1)
  --api URL   runtime API (default http://127.0.0.1:8000, or $PARKINSENSE_API)

Open http://127.0.0.1:8050. Ctrl+C stops it. Exit codes: 0 ok, 1 environment,
2 usage, 3 already running / port in use.
H
}

PORT=8050; HOST=127.0.0.1; API="${PARKINSENSE_API:-http://127.0.0.1:8000}"
while [ $# -gt 0 ]; do
    case "$1" in
        --port) PORT="${2:?}"; shift 2 ;;
        --host) HOST="${2:?}"; shift 2 ;;
        --api) API="${2:?}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

find_python
require_modules "the dashboard" numpy pandas dash plotly
check_single dashboard
port_in_use "$HOST" "$PORT" && die 3 "port $PORT is already in use. Use --port N."

cd "$PS_ROOT"
echo $$ > "$PS_RUN/dashboard.pid"
info "dashboard → http://$HOST:$PORT  (runtime API $API; Ctrl+C to stop)"
exec "$PY" -m parkinsense.visualization.dashboard --host "$HOST" --port "$PORT" --api "$API"
