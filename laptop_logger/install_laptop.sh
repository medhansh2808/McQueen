#!/usr/bin/env bash
set -euo pipefail

USER_NAME="$(id -un)"
GROUP_NAME="$(id -gn)"
HOME_DIR="$HOME"
PYTHON_BIN="$(command -v python3)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$HOME_DIR/McQueenLiveLogger" "$HOME_DIR/KachowDatasets"
cp "$SCRIPT_DIR/phone_logger_server.py" \
  "$HOME_DIR/McQueenLiveLogger/phone_logger_server.py"
chmod +x "$HOME_DIR/McQueenLiveLogger/phone_logger_server.py"
"$PYTHON_BIN" -m py_compile \
  "$HOME_DIR/McQueenLiveLogger/phone_logger_server.py"

sudo tee /etc/systemd/system/mcqueen-live-logger.service >/dev/null <<UNIT
[Unit]
Description=McQueen phone-controlled RGB depth YOLO dataset logger
After=network.target

[Service]
Type=simple
User=${USER_NAME}
Group=${GROUP_NAME}
WorkingDirectory=${HOME_DIR}/McQueenLiveLogger
Environment=PYTHONUNBUFFERED=1
ExecStart=${PYTHON_BIN} ${HOME_DIR}/McQueenLiveLogger/phone_logger_server.py
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable mcqueen-live-logger.service
sudo systemctl restart mcqueen-live-logger.service
sudo ufw allow 8080/tcp >/dev/null 2>&1 || true
sleep 2
sudo systemctl --no-pager --full status mcqueen-live-logger.service
