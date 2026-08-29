#!/bin/bash
# Ensure broker + policy worker + receiver are alive; relaunch the stack if not.
# Intended for cron/timer:  */2 * * * * /path/to/repo/realtime/rtx/stack_watchdog.sh
set -u
REPO="${MCQUEEN_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
CONF="$REPO/realtime/config.env"
[ -f "$CONF" ] || { echo "FATAL: $CONF missing" >&2; exit 2; }
# shellcheck disable=SC1090
. "$CONF"

RT="${MCQUEEN_RUNTIME_DIR:?}"
LOG="$RT/watchdog.log"
OK=1
ss -ltn | grep -q ":${MCQUEEN_BROKER_PORT:-8765} " || OK=0
ss -ltn | grep -q ":${MCQUEEN_POLICY_PORT:-9801} " || OK=0
pgrep -f gst_rtx_rtp_receiver.py >/dev/null || OK=0

if [ $OK -eq 0 ]; then
    echo "$(date -u +%FT%TZ) stack down -> relaunch" >> "$LOG"
    bash "$REPO/realtime/rtx/start_stack.sh" >> "$LOG" 2>&1
else
    echo "$(date -u +%FT%TZ) healthy" >> "$LOG"
fi
