#!/usr/bin/env bash
# agent_startup_check.sh — McQueen agent startup check (READ-ONLY)
#
# Verifies the repository + agent context system are present and healthy.
# Does NOT: install packages, connect to Jetson, SSH, modify hardware,
# modify system services/network, reset git, delete files, or push git.
#
# Usage: bash .mcqueen/agent_startup_check.sh

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0
FAIL=0
WARN=0

ok()   { echo "  PASS  $1"; PASS=$((PASS+1)); }
bad()  { echo "  FAIL  $1"; FAIL=$((FAIL+1)); }
warn() { echo "  WARN  $1"; WARN=$((WARN+1)); }

echo "McQueen agent startup check"
echo "==========================="
echo "Project root: $ROOT"
echo

# --- repository ---
[ -d "$ROOT" ] && ok "repository directory exists" || bad "repository directory missing"

# --- AGENTS.md ---
if [ -f "$ROOT/AGENTS.md" ]; then
  ok "AGENTS.md exists"
else
  bad "AGENTS.md missing"
fi

# --- .mcqueen state files ---
MCQUEEN_DIR="$ROOT/.mcqueen"
if [ -d "$MCQUEEN_DIR" ]; then
  ok ".mcqueen/ exists"
else
  bad ".mcqueen/ missing"
fi

for f in AGENT_STATE.md CURRENT_TASK.md DECISIONS.md SESSION_LOG.md \
         VERIFIED_FACTS.md OPEN_QUESTIONS.md HANDOFF.md \
         PROJECT_INDEX.md COMMAND_POLICY.md \
         agent_startup_check.sh agent_self_audit.py; do
  if [ -f "$MCQUEEN_DIR/$f" ]; then
    [ -s "$MCQUEEN_DIR/$f" ] && ok "$f exists and non-empty" || warn "$f exists but is EMPTY"
  else
    bad "$f missing"
  fi
done

# --- git repository ---
if [ -d "$ROOT/.git" ]; then
  ok "git repository exists"
  BRANCH="$(git -C "$ROOT" branch --show-current 2>/dev/null || echo UNKNOWN)"
  HEAD="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo UNKNOWN)"
  echo "  INFO  branch=$BRANCH HEAD=$HEAD"
  DIRTY="$(git -C "$ROOT" status --porcelain 2>/dev/null | wc -l)"
  echo "  INFO  worktree: $DIRTY uncommitted path(s)"
else
  bad "git repository missing"
fi

# --- important architecture docs ---
for f in README.md docs/ARCHITECTURE.md docs/PROJECT_STATUS_2026-08-12.md \
         docs/NEXT_LAB_RUNBOOK.md docs/REALTIME_INFERENCE_V1.md \
         docs/full_loop_benchmark_v2.md docs/HARDWARE_MILESTONES_2026-08-11.md \
         docs/HOME_VALIDATED_2026-08-12.md docs/dataset_schema_v2.md \
         docs/model_architecture_v1.md docs/BACKBONE_INTEGRATION_PLAN.md; do
  [ -f "$ROOT/$f" ] && ok "doc present: $f" || warn "doc missing: $f"
done

# --- important realtime files ---
for f in mcqueen_ml/deployment/safety.py mcqueen_ml/deployment/protocol.py \
         robot/jetson_nano/mcqueen_edge/app.py robot/jetson_nano/mcqueen_edge/server.py \
         tools/realtime/full_loop_contract_v2.py tools/realtime/direct_udp_peer.py \
         tools/realtime/kachow_probe.py; do
  [ -f "$ROOT/$f" ] && ok "realtime file present: $f" || warn "realtime file missing: $f"
done

# --- tests ---
TEST_COUNT="$(find "$ROOT/tests" "$ROOT/mcqueen_ml" -name 'test_*.py' -type f 2>/dev/null | wc -l)"
echo "  INFO  test files found: $TEST_COUNT"
[ "$TEST_COUNT" -gt 0 ] && ok "tests present" || warn "no test files found"

# --- python ---
if command -v python3 >/dev/null 2>&1; then
  ok "python3 available: $(python3 --version 2>&1)"
else
  warn "python3 not found on PATH"
fi

# --- freebuff config (informational, read-only) ---
FB_CFG="${XDG_CONFIG_HOME:-$HOME/.config}/manicode/settings.json"
if [ -f "$FB_CFG" ]; then
  echo "  INFO  Freebuff settings found: $FB_CFG"
else
  echo "  INFO  Freebuff settings not found (may be non-default location)"
fi

echo
echo "==========================="
echo "Result: $PASS passed, $FAIL failed, $WARN warnings"
if [ "$FAIL" -eq 0 ]; then
  echo "Startup check: OK"
else
  echo "Startup check: PROBLEMS DETECTED — see FAIL lines"
  exit 1
fi
