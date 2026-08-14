#!/usr/bin/env bash
# capture_evidence.sh — file milestone evidence into docs/evidence/<date>/<milestone>/
#
# Usage: capture_evidence.sh <milestone_name> <file...>
#
#   capture_evidence.sh rtp-wan-green ~/run_out.log docs/evidence/2026-08-13-lab-pull/jetson/*.log
#
# After a verified milestone (see MILESTONE_TEMPLATE.md), copy the log artifacts
# onto the laptop, then run this. It fails loudly (exit 2) if any source file is
# missing or empty — no silent gaps in the evidence trail.
#
# On success it prints the explicit, unmissable confirmation line. Repo rule
# (DECISION 013): evidence is only committed together with the next
# hardware-verified commit.
set -u

if [ "$#" -lt 2 ]; then
    echo "ERROR: usage: capture_evidence.sh <milestone_name> <file...>" >&2
    exit 2
fi

MILESTONE="$1"
shift

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATE_DIR="$REPO_ROOT/docs/evidence/$(date +%Y-%m-%d)"
DEST_DIR="$DATE_DIR/$MILESTONE"

mkdir -p "$DEST_DIR" || { echo "ERROR: cannot create $DEST_DIR" >&2; exit 2; }

COPIED=0
for src in "$@"; do
    if [ ! -f "$src" ]; then
        echo "ERROR: missing source file: $src" >&2
        exit 2
    fi
    if [ ! -s "$src" ]; then
        echo "ERROR: empty source file: $src" >&2
        exit 2
    fi
    cp -v "$src" "$DEST_DIR/" >&2 || { echo "ERROR: copy failed: $src" >&2; exit 2; }
    COPIED=$((COPIED + 1))
done

printf '%s\n' \
"================================================================" \
"LOGS FILED -> docs/evidence/$(basename "$DATE_DIR")/$MILESTONE/  ($COPIED files)" \
"================================================================"
ls -la "$DEST_DIR" >&2