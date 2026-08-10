#!/usr/bin/env bash
set -euo pipefail

# Read-only reachability/latency check to run after BOTH Jetson and RTX are
# authenticated into the same tailnet.
#
# Usage:
#   bash tools/tailscale/verify_peer.sh <peer-tailscale-ip-or-name>

PEER="${1:-}"
[ -n "$PEER" ] || {
    echo "Usage: $0 <peer-tailscale-ip-or-name>" >&2
    exit 2
}

echo "===== LOCAL TAILSCALE ====="
tailscale status
echo
echo "Local IPv4: $(tailscale ip -4 | head -1)"

echo
echo "===== PEER: $PEER ====="
echo "--- tailscale ping ---"
tailscale ping -c 5 "$PEER" || true

echo
echo "--- system ping ---"
ping -c 10 -i 0.2 "$PEER" || true

echo
echo "NOTE: ping/RTT is only the network baseline."
echo "It is NOT the camera-to-model-to-returned-command latency."
