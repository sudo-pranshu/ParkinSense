#!/usr/bin/env bash
# Start the ParkinSense runtime (acquisition + analysis + recording + live API).
set -euo pipefail
source "$(dirname "$0")/scripts/launch_common.sh"

usage() { cat <<'H'
Usage: ./start_runtime.sh [--simulate | --replay CAPTURE.csv] [--port N] [--host H] [-- RUNTIME_ARGS...]

Runs in the foreground. Ctrl+C stops it cleanly: the session is finalised and
metadata.json is marked COMPLETE.

  (no source flag)      connect to the wearable over BLE
  --simulate            synthetic signals, no hardware (clearly labelled SIMULATED)
  --replay FILE         stream a recorded capture.csv at real time (labelled REPLAY)
  --port N              API port (default 8000)
  --host H              API bind address (default 127.0.0.1; use 0.0.0.0 to expose on the LAN)
  -- ARGS               passed to python -m parkinsense.runtime.app
                        (e.g. --speed 4, --loop, --start-stopped, --notes "...")

Recordings go to ./recordings/<session>/. Exit codes: 0 ok, 1 environment,
2 usage, 3 already running / port in use.
H
}

PORT=8000; HOST=127.0.0.1; SRC=()
while [ $# -gt 0 ]; do
    case "$1" in
        --simulate) SRC=(--simulate); shift ;;
        --replay) [ -f "${2:-}" ] || die 2 "--replay needs an existing capture file"; SRC=(--replay "$2"); shift 2 ;;
        --port) PORT="${2:?}"; shift 2 ;;
        --host) HOST="${2:?}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        --) shift; break ;;
        *) usage >&2; exit 2 ;;
    esac
done

find_python
need=(numpy scipy pandas fastapi uvicorn)
[ ${#SRC[@]} -eq 0 ] && need+=(bleak)
require_modules "the runtime" "${need[@]}"
check_single runtime
port_in_use "$HOST" "$PORT" && die 3 "port $PORT is already in use (another runtime?). Use --port N."

cd "$PS_ROOT"
echo $$ > "$PS_RUN/runtime.pid"
info "runtime → API http://$HOST:$PORT  (Ctrl+C to stop)"
exec "$PY" -m parkinsense.runtime.app ${SRC[@]+"${SRC[@]}"} --host "$HOST" --port "$PORT" "$@"
