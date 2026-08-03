#!/usr/bin/env bash
set -euo pipefail

CONNECTION="KACHOW-CAR"
SSID="KACHOW-CAR"
PASSWORD="kachow123"

echo "This will disconnect wlan0 from the current Wi-Fi network."
echo "ADB over USB will remain available."
read -r -p "Type HOTSPOT to continue: " answer

if [[ "${answer}" != "HOTSPOT" ]]; then
  echo "Cancelled."
  exit 1
fi

sudo nmcli connection delete "${CONNECTION}" 2>/dev/null || true

sudo nmcli connection add \
  type wifi \
  ifname wlan0 \
  con-name "${CONNECTION}" \
  autoconnect yes \
  ssid "${SSID}"

sudo nmcli connection modify "${CONNECTION}" \
  802-11-wireless.mode ap \
  802-11-wireless.band bg \
  wifi-sec.key-mgmt wpa-psk \
  wifi-sec.psk "${PASSWORD}" \
  ipv4.method shared \
  ipv4.addresses 192.168.4.1/24 \
  ipv6.method disabled \
  connection.autoconnect-priority 100

sudo nmcli connection up "${CONNECTION}"

echo
echo "=== Hotspot status ==="
nmcli device status
ip -4 address show wlan0
echo
echo "SSID: ${SSID}"
echo "Password: ${PASSWORD}"
echo "UNO Q IP: 192.168.4.1"
