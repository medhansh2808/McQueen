#!/usr/bin/env bash
set -u

echo "===== MCQUEEN TAILSCALE PREFLIGHT ====="
echo "Host : $(hostname)"
echo "User : $(id -un)"
echo "Arch : $(uname -m)"
echo "OS   : $(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-unknown}")"

echo
echo "===== TUN ====="
if [ -e /dev/net/tun ]; then
    echo "[PASS] /dev/net/tun exists"
else
    echo "[WARN] /dev/net/tun missing"
fi

echo
echo "===== BINARIES ====="
if command -v tailscale >/dev/null 2>&1; then
    command -v tailscale
    tailscale version 2>/dev/null || true
else
    echo "[INFO] tailscale CLI not installed"
fi

if command -v tailscaled >/dev/null 2>&1; then
    command -v tailscaled
else
    echo "[INFO] tailscaled daemon not installed"
fi

echo
echo "===== SYSTEMD ====="
systemctl is-enabled tailscaled.service 2>/dev/null || true
systemctl is-active tailscaled.service 2>/dev/null || true
systemctl --no-pager --full status tailscaled.service 2>/dev/null | sed -n '1,18p' || true

echo
echo "===== TAILNET STATE ====="
if command -v tailscale >/dev/null 2>&1; then
    tailscale status 2>&1 || true
    echo
    echo "Tailscale IPv4:"
    tailscale ip -4 2>/dev/null || echo "(none)"
fi

echo
echo "===== NETWORK ====="
ip -brief addr 2>/dev/null || true
echo
ip route 2>/dev/null | head -20 || true

echo
echo "===== DONE ====="
