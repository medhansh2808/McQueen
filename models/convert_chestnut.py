"""convert_chestnut.py — test converting big_driving_supercombo.onnx to torch.

Tries onnx2pytorch first (no new deps); if it fails, tries onnx2torch (needs
pip install, pre-approved by user). Prints which backend worked + summary.

Usage:
    python convert_chestnut.py big_driving_supercombo.onnx [out_dir]
"""

import sys
import time
from pathlib import Path

ONNX_PATH = sys.argv[1] if len(sys.argv) > 1 else "big_driving_supercombo.onnx"
OUT_DIR = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")

print(f"converting: {ONNX_PATH}")

t0 = time.time()
try:
    from onnx2pytorch import ConvertModel
    import onnx

    import torch

    model = onnx.load(ONNX_PATH)
    converted = ConvertModel(model)
    torch.save({"model": converted}, OUT_DIR / "chestnut_onnx2torch_sd.pt")
    print(f"onnx2pytorch OK: {type(converted).__name__} in {time.time()-t0:.1f}s, saved module")
except Exception as e:
    print(f"onnx2pytorch FAILED: {type(e).__name__}: {e}")
    try:
        import torch
        from onnx2torch import convert

        converted = convert(ONNX_PATH)
        torch.save({"model": converted}, OUT_DIR / "chestnut_onnx2torch_sd.pt")
        print(f"onnx2torch OK: {type(converted).__name__} in {time.time()-t0:.1f}s, saved module")
    except Exception as e2:
        print(f"onnx2torch FAILED: {type(e2).__name__}: {e2}")
        sys.exit(1)