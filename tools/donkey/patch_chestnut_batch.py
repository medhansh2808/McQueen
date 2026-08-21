"""patch_chestnut_batch.py — make chestnut reshape initializers batch-agnostic (copy).

The chestnut export hard-codes batch=1 in Reshape shape initializers (e.g.
[1, 3072]). At batch>1 onnx2pytorch's Reshape raises (element-count mismatch).
Rewriting a LEADING 1 -> -1 lets torch infer the batch dim: outputs identical
at batch 1, correct at any batch N.

Scope: only 1-D int64 initializers used as Reshape 'shape' inputs whose first
element is 1. If a batch-1 reshape's leading dim is NOT the batch dim (rare),
the element-count constraint still holds and -1 picks the only valid size.

Writes a NEW file (original untouched). Validates with onnx.checker.

Usage (RTX, mcqueen-openpilot env):
    python patch_chestnut_batch.py \
        --onnx ~/mcqueen/models/big_driving_supercombo.onnx \
        --out ~/mcqueen/models/big_driving_supercombo_batch.onnx
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import onnx
from onnx import numpy_helper


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--onnx", required=True)
    ap.add_argument("--out", default="big_driving_supercombo_batch.onnx")
    args = ap.parse_args()

    model = onnx.load(args.onnx)
    reshape_nodes = {inp: node for node in model.graph.node if node.op_type == "Reshape" for inp in node.input[1:2]}
    patched = []
    for init in model.graph.initializer:
        if init.name not in reshape_nodes:
            continue
        arr = numpy_helper.to_array(init)
        if arr.dtype != np.int64 or arr.ndim != 1 or len(arr) == 0 or arr[0] != 1:
            continue
        old = list(arr)
        new = list(arr)
        node = reshape_nodes[init.name]
        if old == [1, -1] and node.input[0] == "desire_pulse":
            new = [-1, 200]  # desire flatten: (1,25,8) = 200 -> (batch, 200)
        elif -1 not in old:
            new[0] = -1
        else:
            continue  # [-1,...] with another -1 cannot be inferred: leave untouched
        arr = np.array(new, dtype=np.int64)
        init.CopyFrom(numpy_helper.from_array(arr, init.name))
        patched.append((init.name, old, new))

    # 'pad' constant (1,2) concatenated onto the flattened output tail: batch-1
    # only, unused by every consumer (metadata 'pad' slice is dropped). Remove it
    # from the concat -> output 2580 -> 2578, all used slices (<= 2578) unchanged.
    for node in model.graph.node:
        if node.op_type == "Concat" and "pad" in node.input:
            node.input.remove("pad")
            patched.append(("pad", ["const"], ["removed-from-concat"]))

    if not patched:
        sys.exit("no leading-1 reshape initializers found — refusing to write unchanged copy")

    onnx.checker.check_model(model)
    onnx.save(model, args.out)

    print(f"patched {len(patched)} reshape initializers in a copy:")
    for name, old, new in patched:
        print(f"  {name}: {old} -> {new}")
    print(f"saved -> {args.out} (original untouched)")


if __name__ == "__main__":
    main()