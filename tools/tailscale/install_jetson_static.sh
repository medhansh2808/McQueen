#!/usr/bin/env bash
set -euo pipefail

# Reproducible static Tailscale installer for the McQueen Jetson Nano.
#
# Usage:
#   sudo bash tools/tailscale/install_jetson_static.sh \
#     /path/to/tailscale_1.98.10_arm64.tgz \
#     /path/to/tailscale_1.98.10_arm64.tgz.sha256
#
# This script deliberately DOES NOT run `tailscale up`.
# Authentication/joining the tailnet remains an explicit next step.

die() {
    echo "ERROR: $*" >&2
    exit 1
}

if [ "$(id -u)" -ne 0 ]; then
    die "run this installer with sudo/root"
fi

TARBALL="${1:-}"
SHA_FILE="${2:-}"

[ -n "$TARBALL" ] || die "missing tarball argument"
[ -f "$TARBALL" ] || die "tarball not found: $TARBALL"
[ -n "$SHA_FILE" ] || die "missing sha256 file argument"
[ -f "$SHA_FILE" ] || die "sha256 file not found: $SHA_FILE"

ARCH="$(uname -m)"
case "$ARCH" in
    aarch64|arm64) ;;
    *) die "expected ARM64 Jetson, got architecture: $ARCH" ;;
esac

echo "===== MCQUEEN TAILSCALE STATIC INSTALL ====="
echo "Architecture : $ARCH"
echo "Tarball      : $TARBALL"
echo "Checksum     : $SHA_FILE"

echo
echo "===== VERIFY CHECKSUM ====="
EXPECTED="$(tr -d '[:space:]' < "$SHA_FILE")"
ACTUAL="$(sha256sum "$TARBALL" | awk '{print $1}')"
echo "Expected: $EXPECTED"
echo "Actual  : $ACTUAL"
[ "${#EXPECTED}" -eq 64 ] || die "checksum file is not a 64-character SHA256 digest"
[ "$EXPECTED" = "$ACTUAL" ] || die "checksum mismatch"
echo "Checksum: PASS"

echo
echo "===== CHECK TUN ====="
if [ ! -e /dev/net/tun ]; then
    echo "/dev/net/tun missing; attempting modprobe tun"
    modprobe tun || die "could not load tun kernel module"
fi
[ -e /dev/net/tun ] || die "/dev/net/tun still missing"
echo "TUN: PASS"

TMPDIR="$(mktemp -d /tmp/mcqueen-tailscale-install.XXXXXX)"
trap 'rm -rf "$TMPDIR"' EXIT

tar -xzf "$TARBALL" -C "$TMPDIR"
TOP="$(find "$TMPDIR" -mindepth 1 -maxdepth 1 -type d -name 'tailscale_*_arm64' | head -1)"
[ -n "$TOP" ] || die "expected tailscale_*_arm64 directory not found in archive"

TS="$TOP/tailscale"
TSD="$TOP/tailscaled"
UNIT="$TOP/systemd/tailscaled.service"
DEFAULTS="$TOP/systemd/tailscaled.defaults"

[ -x "$TS" ] || die "tailscale binary missing/not executable"
[ -x "$TSD" ] || die "tailscaled binary missing/not executable"
[ -f "$UNIT" ] || die "official tailscaled.service missing"
[ -f "$DEFAULTS" ] || die "official tailscaled.defaults missing"

echo
echo "===== ARCHIVE VERSION ====="
"$TS" version
"$TSD" --version

# We install to the conventional paths used by the official Linux systemd unit.
grep -q '/usr/sbin/tailscaled' "$UNIT" \
    || die "official unit does not reference /usr/sbin/tailscaled; inspect archive before installing"

BACKUP="/var/backups/mcqueen-tailscale-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP"

backup_if_present() {
    local p="$1"
    if [ -e "$p" ] || [ -L "$p" ]; then
        cp -a "$p" "$BACKUP/"
        echo "Backed up: $p"
    fi
}

echo
echo "===== BACKUP EXISTING FILES IF ANY ====="
backup_if_present /usr/bin/tailscale
backup_if_present /usr/sbin/tailscaled
backup_if_present /etc/systemd/system/tailscaled.service
backup_if_present /lib/systemd/system/tailscaled.service
backup_if_present /etc/default/tailscaled

echo
echo "===== INSTALL OFFICIAL STATIC FILES ====="
install -m 0755 "$TS" /usr/bin/tailscale
install -m 0755 "$TSD" /usr/sbin/tailscaled

# Put the unit in /etc so this manual/static installation is explicit and easy
# to find/replace. Use the defaults shipped in the same official archive.
install -m 0644 "$UNIT" /etc/systemd/system/tailscaled.service
if [ ! -f /etc/default/tailscaled ]; then
    install -m 0644 "$DEFAULTS" /etc/default/tailscaled
else
    echo "Keeping existing /etc/default/tailscaled (backup is in $BACKUP)"
fi

mkdir -p /var/lib/tailscale /run/tailscale

systemctl daemon-reload
systemctl enable tailscaled.service
systemctl restart tailscaled.service

echo
echo "===== VERIFY SERVICE ====="
systemctl --no-pager --full status tailscaled.service | sed -n '1,24p'
systemctl is-active --quiet tailscaled.service \
    || die "tailscaled service is not active"

echo
echo "===== VERIFY CLI ====="
/usr/bin/tailscale version

echo
echo "TAILSCALE STATIC INSTALL: PASS"
echo "Backup directory: $BACKUP"
echo
echo "NOT authenticated yet."
echo "Next explicit step after inspection:"
echo "  sudo tailscale up"
