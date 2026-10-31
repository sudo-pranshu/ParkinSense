#!/usr/bin/env bash
# Remove generated files. Never touches recordings/, replays/, datasets/ or the venv.
set -euo pipefail
source "$(dirname "$0")/scripts/launch_common.sh"

usage() { cat <<'H'
Usage: ./clean.sh [--yes] [--logs]

Lists, then (with --yes) deletes: Python caches, .pytest_cache, build/,
*.egg-info, stale pid files in .run/, and the legacy realtime_metrics*.json.
--logs also deletes ./logs/.

Never deleted: recordings/, replays/, datasets/, realtime_capture*.csv,
.venv/ and venv/. Without --yes nothing is removed (dry run).
H
}
YES=0; LOGS=0
for a in "$@"; do
    case "$a" in --yes) YES=1 ;; --logs) LOGS=1 ;; -h|--help) usage; exit 0 ;; *) usage >&2; exit 2 ;; esac
done

cd "$PS_ROOT"
for c in runtime dashboard; do pid_alive "$PS_RUN/$c.pid" 2>/dev/null && die 3 "$c is running — stop it first"; done
T=()
while IFS= read -r line; do T+=("$line"); done < <(
    find . -path ./.venv -prune -o -path ./venv -prune -o -path ./.git -prune -o \
        \( -name __pycache__ -o -name .pytest_cache -o -name '*.egg-info' \) -print 2>/dev/null
    for p in build dist .run realtime_metrics.json realtime_metrics_v2.json; do [ -e "$p" ] && echo "./$p"; done
    [ "$LOGS" = 1 ] && [ -d logs ] && echo ./logs
    true
)
[ ${#T[@]} -eq 0 ] && { ok "nothing to clean"; exit 0; }
printf '  %s\n' "${T[@]}"
if [ "$YES" = 1 ]; then rm -rf "${T[@]}"; ok "removed ${#T[@]} item(s)"
else info "dry run — re-run with --yes to delete"; fi
