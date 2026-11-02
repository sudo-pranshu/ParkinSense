#!/usr/bin/env bash
# Deterministic offline replay of a recording through the current pipeline.
set -euo pipefail
source "$(dirname "$0")/scripts/launch_common.sh"

usage() { cat <<'H'
Usage: ./replay.sh SESSION|CAPTURE.csv [--out DIR] [--resample]
       ./replay.sh --compare RUN_A RUN_B
       ./replay.sh --list

  SESSION        a folder name under ./recordings/ (or a path to capture.csv)
  --out DIR      output folder (default ./replays/<session>_<time>/; never overwrites)
  --resample     resample to the nominal rate before analysis
  --compare A B  compare two replay outputs
  --list         list recorded sessions

The original recording is only read. To watch a recording live in the
dashboard instead, use ./start_parkinsense.sh --replay CAPTURE.csv.
H
}

[ $# -gt 0 ] || { usage >&2; exit 2; }
find_python
cd "$PS_ROOT"
case "$1" in
    -h|--help) usage; exit 0 ;;
    --list) ls -1t recordings 2>/dev/null || info "no recordings yet"; exit 0 ;;
    --compare) shift; exec "$PY" -m parkinsense.replay.replay --compare "$@" ;;
esac

SRC="$1"; shift
if [ -d "recordings/$SRC" ]; then CAP="recordings/$SRC/capture.csv"; NAME="$SRC"
elif [ -f "$SRC" ]; then CAP="$SRC"; NAME="$(basename "$(dirname "$SRC")")"
else die 2 "no recording '$SRC' (try ./replay.sh --list)"; fi

OUT=; ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --out) OUT="${2:?}"; shift 2 ;;
        --resample) ARGS+=(--resample); shift ;;
        *) usage >&2; exit 2 ;;
    esac
done
OUT="${OUT:-replays/${NAME}_$(date +%Y%m%d_%H%M%S)}"
[ -e "$OUT" ] && die 2 "$OUT already exists (replays never overwrite)"
info "replaying $CAP → $OUT"
exec "$PY" -m parkinsense.replay.replay "$CAP" --out "$OUT" ${ARGS[@]+"${ARGS[@]}"}
