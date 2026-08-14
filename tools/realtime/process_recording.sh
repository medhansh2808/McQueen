#!/usr/bin/env bash
# process_recording.sh — recording pipeline: validate -> convert -> file evidence
#
# Usage: process_recording.sh <spool_dir> <output_dir> <repo_id> [milestone_name]
#
#   process_recording.sh data/lab_pull_20260813/jetson_spool data/lerobot mq-20260813-batch1
#
# Runs on the LAPTOP after recordings are pulled off the Jetson. Steps:
#   1. validate_spool.py  (raw spool health; failures BLOCK conversion)
#   2. convert_spool.py   (spool -> LeRobot, reuse of existing converter)
#   3. file the validation+conversion logs as evidence (needs a milestone name)
#
# Pipeline rule: a spool that fails validation is NEVER converted. A batch is
# only "usable for training" after this script reports all PASSED.
set -u

if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
    echo "ERROR: usage: process_recording.sh <spool_dir> <output_dir> <repo_id> [milestone_name]" >&2
    exit 2
fi

SPOOL_DIR="$1"
OUTPUT_DIR="$2"
REPO_ID="$3"
MILESTONE="${4:-}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="$REPO_ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
    PY=/home/kartik/miniforge3/envs/mcqueen-laptop/bin/python
fi

echo "[RECORDING PIPELINE] validate: $SPOOL_DIR"
"$PY" "$REPO_ROOT/mcqueen_ml/dataset/validate_spool.py" --input "$SPOOL_DIR" | tee /tmp/mcqueen_validate_out.log
VALIDATE_RC=${PIPESTATUS[0]}

if [ "$VALIDATE_RC" -ne 0 ]; then
    echo "[RECORDING PIPELINE] BLOCKED: spool FAILED validation — NOT converted. Fix recording first." >&2
    exit 1
fi

echo "[RECORDING PIPELINE] convert: $SPOOL_DIR -> $OUTPUT_DIR (repo-id: $REPO_ID)"
"$PY" "$REPO_ROOT/mcqueen_ml/dataset/convert_spool.py" \
    --input "$SPOOL_DIR" --output "$OUTPUT_DIR" --repo-id "$REPO_ID" | tee /tmp/mcqueen_convert_out.log
CONVERT_RC=${PIPESTATUS[0]}

if [ "$CONVERT_RC" -ne 0 ]; then
    echo "[RECORDING PIPELINE] BLOCKED: conversion FAILED (rc=$CONVERT_RC)." >&2
    exit 1
fi

echo "[RECORDING PIPELINE] PASSED: validation OK, conversion OK."
echo "  usable dataset: $OUTPUT_DIR"

if [ -n "$MILESTONE" ]; then
    "$REPO_ROOT/tools/realtime/capture_evidence.sh" "$MILESTONE" \
        /tmp/mcqueen_validate_out.log /tmp/mcqueen_convert_out.log
fi