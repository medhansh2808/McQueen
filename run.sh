#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
source .venv/bin/activate

export DEPTHAI_PROTOCOL=usb
export DEPTHAI_SEARCH_TIMEOUT=60000
export DEPTHAI_CONNECT_TIMEOUT=60000
export DEPTHAI_BOOTUP_TIMEOUT=60000
export DEPTHAI_RECONNECT_TIMEOUT=60000
export DEPTHAI_WATCHDOG_INITIAL_DELAY=60000
export DEPTHAI_CRASHDUMP=0

exec python3 mcqueen_yolo_depth_server.py "$@"
