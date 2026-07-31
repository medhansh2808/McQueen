#!/usr/bin/env python3
from pathlib import Path
import json

cfg_path = Path.home() / "mcqueen_reverse_calibration.json"
if not cfg_path.exists():
    raise SystemExit(f"Missing {cfg_path}; run capture_phone.py first.")

cfg = json.loads(cfg_path.read_text())
t = cfg.get("throttle_index")
s = cfg.get("steer_index")

if t is None:
    raise SystemExit("Calibration says Android reverse is not valid. Fix Android first.")
if s is None:
    print("Warning: steering index was not uniquely identified; using 1.")
    s = 1

out = Path(__file__).resolve().parent / "main" / "app_config.h"
out.write_text(
    "#pragma once\n"
    f"#define APP_STEER_FIELD_INDEX {int(s)}\n"
    f"#define APP_THROTTLE_FIELD_INDEX {int(t)}\n"
)
print("Wrote", out)
print("Steer index:", s)
print("Throttle index:", t)
