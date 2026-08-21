"""patch_onnx_batch.py — make supercombo subgraph reshapes batch-agnostic (copy).

The comma 2026-master driving_supercombo export hard-codes batch=1 in four
Reshape shape initializers ([1,1024], [1,1,512], [1,9,3,8,64], [1,9,512]).
At batch>1 onnx2pytorch's Reshape raises (element-count mismatch). Rewriting
the leading 1 -> -1 makes them infer batch (torch.reshape semantics): outputs
are numerically identical at batch 1 and correct at any batch N.

Writes a NEW file (original artifact untouched). Validates with onnx.checker.

Usage (RTX, mcqueen-openpilot env):
    PYTHONPATH=~/mcqueen/models python tools/donkey/patch_onnx_batch.py \
        --onnx ~/mcqueen/models/driving_supercombo_master.onnx \
        --out ~/mcqueen/models/driving_supercombo_master_batch.onnx
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import onnx
from onnx import numpy_helper

TARGET_SHAPES = {
    (1, 1024): (-1, 1024),
    (1, 1, 512): (-1, 1, 512),
    (1, 9, 3, 8, 64): (-1, 9, 3, 8, 64),
    (1, 9, 512): (-1, 9, 512),
    (1, -1): (-1, 200),  # p_view: desire-path flatten; keeps batch as first dim
}

# Expand shape initializers with a hard-coded batch dim of 1
EXPAND_SHAPES = {(1, 512): (-1, 512)}

# p_pad: constant [[0,0]] appended to graph output (last 2 cols). Nothing reads
# the tail (action_adapter slices only up to 2566 of 2576), so dropping it keeps
# all slices identical while removing the only batch-1 concat operand.
PAD_INPUT_NAME = "p_pad"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--onnx", required=True)
    ap.add_argument("--out", default="driving_supercombo_master_batch.onnx")
    args = ap.parse_args()

    model = onnx.load(args.onnx)
    patched = []
    for init in model.graph.initializer:
        arr = numpy_helper.to_array(init)
        if arr.dtype != np.int64 or arr.ndim != 1:
            continue
        shape = tuple(arr.tolist())
        if shape in TARGET_SHAPES:
            new_shape = TARGET_SHAPES[shape]
            old = list(shape)
            arr = np.array(list(new_shape), dtype=np.int64)  # writable copy
            init.CopyFrom(numpy_helper.from_array(arr, init.name))
            patched.append((init.name, old, arr.tolist()))
        elif shape in EXPAND_SHAPES:
            new_shape = EXPAND_SHAPES[shape]
            old = list(shape)
            arr = np.array(list(new_shape), dtype=np.int64)  # writable copy
            init.CopyFrom(numpy_helper.from_array(arr, init.name))
            patched.append((init.name, old, arr.tolist()))

    dropped_pad = False
    for node in model.graph.node:
        if node.op_type == "Concat" and PAD_INPUT_NAME in node.input:
            node.input.remove(PAD_INPUT_NAME)
            dropped_pad = True
            patched.append((PAD_INPUT_NAME, ["const"], ["removed-from-concat"]))
        for attr in node.attribute:
            if attr.type == 4:  # GRAPH: subgraphs (Identity nodes hold no tensors; kept for safety)
                pass

    if not patched:
        sys.exit("no target reshape initializers found — refusing to write unchanged copy")

    onnx.checker.check_model(model)
    onnx.save(model, args.out)

    print(f"patched {len(patched)} reshape initializers in a copy:")
    for name, old, new in patched:
        print(f"  {name}: {old} -> {new}")
    print(f"saved -> {args.out} (original untouched)")


if __name__ == "__main__":
    main()