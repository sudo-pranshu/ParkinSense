# Shared helpers for the ParkinSense launch scripts. Sourced, not executed.
# Exit codes used by all scripts:
#   0 ok | 1 environment problem | 2 usage error | 3 port in use / already running | 4 failed to start

PS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PS_RUN="${PARKINSENSE_RUN_DIR:-$PS_ROOT/.run}"     # pid files
PS_LOGS="${PARKINSENSE_LOG_DIR:-$PS_ROOT/logs}"
mkdir -p "$PS_RUN" "$PS_LOGS"

if [ -t 1 ]; then C_B=$'\e[1m'; C_R=$'\e[31m'; C_G=$'\e[32m'; C_Y=$'\e[33m'; C_0=$'\e[0m'
else C_B=; C_R=; C_G=; C_Y=; C_0=; fi
info() { printf '%s\n' "${C_B}parkinsense${C_0} $*"; }
ok()   { printf '%s\n' "${C_G}✔${C_0} $*"; }
warn() { printf '%s\n' "${C_Y}!${C_0} $*" >&2; }
die()  { local code="$1"; shift; printf '%s\n' "${C_R}✘${C_0} $*" >&2; exit "$code"; }

# Python of the project environment: $PARKINSENSE_PYTHON, an active venv, ./.venv, ./venv.
# No manual activation is needed.
find_python() {
    if [ -n "${PARKINSENSE_PYTHON:-}" ]; then PY="$PARKINSENSE_PYTHON"
    elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then PY="$VIRTUAL_ENV/bin/python"
    elif [ -x "$PS_ROOT/.venv/bin/python" ]; then PY="$PS_ROOT/.venv/bin/python"
    elif [ -x "$PS_ROOT/venv/bin/python" ]; then PY="$PS_ROOT/venv/bin/python"
    else die 1 "No Python environment found. Run ./setup.sh first (or set PARKINSENSE_PYTHON)."
    fi
    "$PY" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null \
        || die 1 "$PY is not Python ≥ 3.10."
}

# require_modules "what for" module...
require_modules() {
    local what="$1"; shift
    local missing
    missing="$("$PY" - "$@" <<'EOF'
import importlib.util, sys
print(" ".join(m for m in sys.argv[1:] if importlib.util.find_spec(m) is None))
EOF
)"
    [ -z "$missing" ] || die 1 "Missing Python packages for $what: $missing. Run ./setup.sh."
}

port_in_use() {  # port_in_use HOST PORT
    "$PY" - "$1" "$2" <<'EOF'
import socket, sys
s = socket.socket()
s.settimeout(0.5)
sys.exit(0 if s.connect_ex((sys.argv[1] if sys.argv[1] not in ("0.0.0.0", "") else "127.0.0.1", int(sys.argv[2]))) == 0 else 1)
EOF
}

# pidfile helpers: one instance per component
pid_alive() {  # a live process that is actually ParkinSense (guards against pid reuse)
    [ -f "$1" ] || return 1
    local pid; pid="$(cat "$1")"
    kill -0 "$pid" 2>/dev/null && ps -p "$pid" -o args= 2>/dev/null | grep -q parkinsense
}
check_single() {  # check_single NAME
    local pf="$PS_RUN/$1.pid"
    if pid_alive "$pf"; then
        die 3 "$1 is already running (pid $(cat "$pf")). Stop it with Ctrl+C in its terminal, or: kill -INT $(cat "$pf")"
    fi
    rm -f "$pf"
}

wait_http() {  # wait_http URL SECONDS PID
    local url="$1" secs="$2" pid="$3"
    "$PY" - "$url" "$secs" "$pid" <<'EOF'
import os, sys, time, urllib.request
url, deadline, pid = sys.argv[1], time.time() + float(sys.argv[2]), int(sys.argv[3])
while time.time() < deadline:
    try:
        os.kill(pid, 0)
    except OSError:
        sys.exit(2)
    try:
        urllib.request.urlopen(url, timeout=1).read()
        sys.exit(0)
    except Exception:
        time.sleep(0.25)
sys.exit(1)
EOF
}
