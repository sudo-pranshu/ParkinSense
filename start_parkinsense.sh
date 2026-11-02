#!/usr/bin/env bash
# One command: runtime + dashboard, health-checked, with a clean Ctrl+C shutdown.
set -euo pipefail
source "$(dirname "$0")/scripts/launch_common.sh"

usage() { cat <<'H'
Usage: ./start_parkinsense.sh [--simulate | --replay CAPTURE.csv] [options] [-- RUNTIME_ARGS...]

Starts the runtime and the dashboard, waits until both answer, prints the URLs
and streams both logs. Ctrl+C stops both: the runtime first (session finalised,
metadata COMPLETE), then the dashboard.

  (no source flag)       wearable over BLE
  --simulate             synthetic signals, no hardware needed
  --replay FILE          stream a recorded capture.csv at real time
  --api-port N           runtime API port (default 8000)
  --dashboard-port N     dashboard port (default 8050)
  --quiet                do not stream logs (they are always in ./logs/)
  -- ARGS                extra runtime arguments (e.g. -- --speed 4 --loop)

Exit codes: 0 ok, 1 environment, 2 usage, 3 already running / port in use,
4 a component failed to start.
H
}

API_PORT=8000; DASH_PORT=8050; SRC=(); QUIET=0
while [ $# -gt 0 ]; do
    case "$1" in
        --simulate) SRC=(--simulate); shift ;;
        --replay) [ -f "${2:-}" ] || die 2 "--replay needs an existing capture file"; SRC=(--replay "$2"); shift 2 ;;
        --api-port) API_PORT="${2:?}"; shift 2 ;;
        --dashboard-port) DASH_PORT="${2:?}"; shift 2 ;;
        --quiet) QUIET=1; shift ;;
        -h|--help) usage; exit 0 ;;
        --) shift; break ;;
        *) usage >&2; exit 2 ;;
    esac
done
EXTRA=("$@")

find_python
need=(numpy scipy pandas fastapi uvicorn dash plotly)
[ ${#SRC[@]} -eq 0 ] && need+=(bleak)
require_modules "runtime + dashboard" "${need[@]}"
check_single runtime
check_single dashboard
port_in_use 127.0.0.1 "$API_PORT" && die 3 "API port $API_PORT is in use. Use --api-port N."
port_in_use 127.0.0.1 "$DASH_PORT" && die 3 "dashboard port $DASH_PORT is in use. Use --dashboard-port N."

cd "$PS_ROOT"
STAMP="$(date +%Y%m%d_%H%M%S)"
RLOG="$PS_LOGS/runtime_$STAMP.log"; DLOG="$PS_LOGS/dashboard_$STAMP.log"
RPID=; DPID=; TPID=

shutdown() {
    trap - INT TERM
    echo
    info "stopping…"
    if [ -n "$RPID" ] && kill -0 "$RPID" 2>/dev/null; then
        kill -INT "$RPID" 2>/dev/null || true
        for _ in $(seq 1 60); do kill -0 "$RPID" 2>/dev/null || break; sleep 0.25; done
        kill -0 "$RPID" 2>/dev/null && { warn "runtime did not stop in 15 s; terminating"; kill -TERM "$RPID" 2>/dev/null || true; }
    fi
    [ -n "$DPID" ] && kill -TERM "$DPID" 2>/dev/null || true
    wait 2>/dev/null || true
    [ -n "$TPID" ] && kill "$TPID" 2>/dev/null || true
    rm -f "$PS_RUN/runtime.pid" "$PS_RUN/dashboard.pid"
    ok "stopped. Logs: ${RLOG#$PS_ROOT/}, ${DLOG#$PS_ROOT/}"
}
trap 'shutdown; exit 0' INT TERM

"$PY" -u -m parkinsense.runtime.app ${SRC[@]+"${SRC[@]}"} --host 127.0.0.1 --port "$API_PORT" \
    ${EXTRA[@]+"${EXTRA[@]}"} >"$RLOG" 2>&1 &
RPID=$!; echo "$RPID" > "$PS_RUN/runtime.pid"
if ! wait_http "http://127.0.0.1:$API_PORT/health" 20 "$RPID"; then
    tail -n 20 "$RLOG" >&2
    shutdown; die 4 "runtime failed to start (log: ${RLOG#$PS_ROOT/})"
fi
ok "runtime     http://127.0.0.1:$API_PORT  (${SRC[*]:-BLE})"

"$PY" -u -m parkinsense.visualization.dashboard --host 127.0.0.1 --port "$DASH_PORT" \
    --api "http://127.0.0.1:$API_PORT" >"$DLOG" 2>&1 &
DPID=$!; echo "$DPID" > "$PS_RUN/dashboard.pid"
if ! wait_http "http://127.0.0.1:$DASH_PORT/" 30 "$DPID"; then
    tail -n 20 "$DLOG" >&2
    shutdown; die 4 "dashboard failed to start (log: ${DLOG#$PS_ROOT/})"
fi
ok "dashboard   ${C_B}http://127.0.0.1:$DASH_PORT${C_0}"
info "logs in ./logs/ — Ctrl+C to stop both"

if [ "$QUIET" = 0 ]; then
    tail -n 0 -F "$RLOG" "$DLOG" 2>/dev/null &
    TPID=$!
fi

# exit when either component dies on its own
while kill -0 "$RPID" 2>/dev/null && kill -0 "$DPID" 2>/dev/null; do sleep 1; done
warn "a component exited unexpectedly"
kill -0 "$RPID" 2>/dev/null || tail -n 15 "$RLOG" >&2
kill -0 "$DPID" 2>/dev/null || tail -n 15 "$DLOG" >&2
shutdown
exit 4
