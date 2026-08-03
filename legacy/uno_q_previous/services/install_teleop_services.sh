#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

sudo cp "$SCRIPT_DIR/mcqueen-mcu.service" /etc/systemd/system/
sudo cp "$SCRIPT_DIR/mcqueen-teleop.service" /etc/systemd/system/
sudo cp "$SCRIPT_DIR/mcqueen-goal2.service" /etc/systemd/system/

sudo mkdir -p /etc/systemd/system/mcqueen-teleop.service.d
sudo cp "$SCRIPT_DIR/mcu-order.conf" \
  /etc/systemd/system/mcqueen-teleop.service.d/mcu-order.conf

sudo systemctl daemon-reload
sudo systemctl enable mcqueen-mcu.service mcqueen-teleop.service
sudo systemctl restart mcqueen-mcu.service
sleep 8
sudo systemctl restart mcqueen-teleop.service
sleep 2

sudo systemctl --no-pager --full status mcqueen-mcu.service || true
sudo systemctl --no-pager --full status mcqueen-teleop.service || true

echo
echo "teleop services installed"
echo "goal2 service was copied but not enabled"
