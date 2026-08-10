#!/usr/bin/env python3
from pathlib import Path
import ast
import sys

root = Path(__file__).resolve().parents[2]
path = root / "mcqueen_ml" / "dataset" / "convert_spool.py"
source = path.read_text(encoding="utf-8")
tree = ast.parse(source)

errors = []

defs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
for old in ("normalize_steering", "normalize_throttle"):
    if old in defs:
        errors.append(f"old normalization function still exists: {old}")

if 'robot_type="mcqueen_jetson_nano"' not in source.replace(" ", ""):
    # Tolerate normal formatting by checking AST string literals too.
    strings = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    if "mcqueen_jetson_nano" not in strings:
        errors.append("robot_type mcqueen_jetson_nano not found")

if "servo_angle_deg" not in source:
    errors.append("action name servo_angle_deg not found")
if "motor_pwm" not in source:
    errors.append("motor_pwm not found")
if "mcqueen.raw_actuator" in source:
    errors.append("redundant mcqueen.raw_actuator still present")

if "mcqueen.source_timestamp_s" in source:
    errors.append("lossy float32 source timestamp still present")

if "mcqueen.source_timestamp_ms" not in source:
    errors.append("int64 source timestamp_ms feature not found")

if errors:
    print("CONVERTER CONTRACT: FAILED")
    for e in errors:
        print(" -", e)
    sys.exit(1)

print("CONVERTER CONTRACT: PASSED")
print(" - robot_type = mcqueen_jetson_nano")
print(" - action names include servo_angle_deg, motor_pwm")
print(" - no normalize_steering / normalize_throttle")
print(" - no mcqueen.raw_actuator feature")
