#!/usr/bin/env bash
# Run the same checks as CI (Python, firmware host tests, docs) locally.
set -uo pipefail
source "$(dirname "$0")/scripts/launch_common.sh"

usage() { cat <<'H'
Usage: ./check.sh [--quick]

  (default)   environment, lint, full pytest (incl. golden outputs),
              benchmark cost smoke run, firmware host tests (if g++), doc links
  --quick     environment + pytest only

Exit code: 0 if every step passed, 1 otherwise (each step is reported).
H
}
QUICK=0
case "${1:-}" in --quick) QUICK=1 ;; -h|--help) usage; exit 0 ;; "") ;; *) usage >&2; exit 2 ;; esac

find_python
cd "$PS_ROOT"
FAILED=()
step() {  # step NAME CMD...
    local name="$1"; shift
    info "▶ $name"
    if "$@"; then ok "$name"; else FAILED+=("$name"); warn "$name FAILED"; fi
}

step "environment" "$PY" -c 'import numpy, scipy, pandas, parkinsense'
if [ "$QUICK" = 0 ]; then
    if "$PY" -c 'import flake8' 2>/dev/null; then
        step "lint (errors only)" "$PY" -m flake8 parkinsense tests benchmarks --count \
            --select=E9,F63,F7,F82,F401,F811,F841 --show-source --statistics
    else warn "flake8 not installed — lint skipped (./setup.sh installs it)"; fi
fi
step "pytest (unit, integration, golden regression)" "$PY" -m pytest -q
if [ "$QUICK" = 0 ]; then
    step "benchmark cost smoke run" "$PY" -m benchmarks.run_benchmarks --impl current --only cost \
        --out "$PS_RUN/bench_cost.json"
    if command -v g++ >/dev/null; then
        step "firmware host tests" bash -c 'g++ -std=c++17 -Wall -Wextra -Werror -I firmware/parkinsense_wearable \
            firmware/tests/test_packet.cpp -o "$0/fw_test" && "$0/fw_test"' "$PS_RUN"
    else warn "g++ not found — firmware host tests skipped"; fi
    step "documentation links" "$PY" scripts/check_doc_links.py
fi

echo
if [ ${#FAILED[@]} -eq 0 ]; then ok "all checks passed"; exit 0; fi
printf '%s\n' "${C_R}failed:${C_0} ${FAILED[*]}"; exit 1
