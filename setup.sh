#!/usr/bin/env bash
# One-time environment setup for ParkinSense.
set -euo pipefail
source "$(dirname "$0")/scripts/launch_common.sh"

usage() { cat <<'H'
Usage: ./setup.sh [--extras LIST] [--python PATH] [--recreate]

Creates ./.venv (if no project environment exists yet) and installs ParkinSense
in editable mode with the runtime, dashboard and developer extras.

An existing environment (active venv, ./.venv or ./venv) is reused and never
deleted unless you pass --recreate.

  --extras LIST   comma-separated extras (default: live,dashboard,dev)
                  live = BLE runtime + API, dashboard = Dash UI, dev = pytest/flake8
  --python PATH   interpreter used to create the venv (default: python3, needs ≥ 3.10)
  --recreate      delete ./.venv and create it again
  -h, --help      this help

Exit codes: 0 ok, 1 environment problem, 2 usage error.
H
}

EXTRAS="live,dashboard,dev"; BASE_PY="${PYTHON:-python3}"; RECREATE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --extras) EXTRAS="${2:?--extras needs a value}"; shift 2 ;;
        --python) BASE_PY="${2:?--python needs a value}"; shift 2 ;;
        --recreate) RECREATE=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

cd "$PS_ROOT"
if [ "$RECREATE" = 1 ] && [ -d .venv ]; then
    info "removing ./.venv (--recreate)"
    rm -rf .venv
fi

if [ -n "${VIRTUAL_ENV:-}" ] || [ -x .venv/bin/python ] || [ -x venv/bin/python ]; then
    find_python
    info "using existing environment: $PY"
else
    command -v "$BASE_PY" >/dev/null || die 1 "$BASE_PY not found. Install Python ≥ 3.10 or pass --python."
    "$BASE_PY" -c 'import sys; sys.exit(sys.version_info < (3, 10))' || die 1 "$BASE_PY is older than 3.10."
    info "creating ./.venv with $("$BASE_PY" --version)"
    "$BASE_PY" -m venv .venv || die 1 "venv creation failed (Debian/Ubuntu: apt install python3-venv)."
    PY="$PS_ROOT/.venv/bin/python"
fi

info "installing parkinsense[$EXTRAS] (editable)"
"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q -e ".[${EXTRAS}]" || die 1 "pip install failed (see output above)."

"$PY" -c 'import parkinsense, numpy, scipy, pandas; print("parkinsense", parkinsense.__version__ if hasattr(parkinsense, "__version__") else "")' >/dev/null \
    || die 1 "import check failed."
ok "environment ready: $PY"
cat <<'N'

Next:
  ./start_parkinsense.sh --simulate   # runtime + dashboard, no hardware needed
  ./start_parkinsense.sh              # with the wearable over BLE
  ./check.sh                          # tests, lint, golden outputs
N
