#!/usr/bin/env bash
set -u

REPO="$HOME/McQueen"

echo "===== McQueen Jetson inspection (READ-ONLY except git fetch) ====="

if [ ! -d "$REPO/.git" ]; then
  echo "[FAIL] Repo missing: $REPO"
  exit 1
fi

cd "$REPO" || exit 1

echo
echo "===== STATUS ====="
git status --short --branch

echo
echo "===== CURRENT BRANCH ====="
git branch --show-current

echo
echo "===== LOCAL HEAD ====="
git log -5 --oneline --decorate

echo
echo "===== FETCH ORIGIN ====="
git fetch origin

echo
echo "===== ORIGIN jetson-nano ====="
git log -5 --oneline --decorate origin/jetson-nano

echo
echo "===== DIVERGENCE ====="
git rev-list --left-right --count HEAD...origin/jetson-nano

echo
echo "===== EDGE SERVICE ====="
systemctl is-enabled mcqueen-edge.service 2>/dev/null || true
systemctl is-active mcqueen-edge.service 2>/dev/null || true
systemctl status mcqueen-edge.service --no-pager -l 2>/dev/null | tail -20 || true

echo
echo "===== INSTALLED SERVICE FILE ====="
systemctl cat mcqueen-edge.service 2>/dev/null || true

echo
echo "===== IMPORTANT ====="
echo "This script does NOT pull, reset, merge, or modify the Jetson checkout."
echo "Send this output before syncing the Jetson."
