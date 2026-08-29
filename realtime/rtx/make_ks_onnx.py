#!/usr/bin/env python3
"""Generate the ORT-convertible variant of the driving-supercombo ONNX.

2026-08-22: onnx2pytorch 0.5.3 fails on the stock export (44 Conv nodes ship no
kernel_shape; stash_type unsupported) and ORT-CPU rejects runtime shapes that
differ from stale declared dims. The fix that verified at 346 ms/frame:

  1. bake kernel_shape into Conv/ConvTranspose/MaxPool/AvgPool from weight dims
  2. make every graph input fully dynamic (rank kept, dims -> "?")
  3. strip value_info and declared output shapes (stale annotations caused
     "Can't merge shape info" inside the receiver)

Usage:
    python3 make_ks_onnx.py [SRC] [DST]
Defaults match the RTX deployment layout.
"""
import os
import sys

import onnx
from onnx import helper

SRC_DEFAULT = os.environ.get("MCQUEEN_ONNX", "")
DST_SUFFIX = "_ks.onnx"

CONV_LIKE = ("Conv", "ConvTranspose", "MaxPool", "AvgPool")
INPUT_RANKS = {
    "img": 4,
    "big_img": 4,
    "desire_pulse": 3,
    "traffic_convention": 2,
    "action_t": 2,
    "features_buffer": 3,
}


def main() -> int:
    src = sys.argv[1] if len(sys.argv) > 1 else SRC_DEFAULT
    dst = sys.argv[2] if len(sys.argv) > 2 else src.replace(".onnx", DST_SUFFIX)

    model = onnx.load(src)
    graph = model.graph
    inits = {i.name: i for i in graph.initializer}

    baked = 0
    for node in graph.node:
        if node.op_type in CONV_LIKE and not any(
            a.name == "kernel_shape" for a in node.attribute
        ):
            weight = inits.get(node.input[1]) if len(node.input) > 1 else None
            if weight is not None and len(weight.dims) >= 4:
                kdims = list(weight.dims[2:])
            else:
                kdims = [3, 3]
            node.attribute.append(helper.make_attribute("kernel_shape", kdims))
            baked += 1

    dyn = 0
    for gi in graph.input:
        if gi.name in INPUT_RANKS:
            shape = gi.type.tensor_type.shape
            del shape.dim[:]
            for _ in range(INPUT_RANKS[gi.name]):
                shape.dim.add().dim_param = "?"
            dyn += 1

    del graph.value_info[:]
    for out in graph.output:
        if len(out.type.tensor_type.shape.dim):
            del out.type.tensor_type.shape.dim[:]

    onnx.save(model, dst)
    print(
        "make_ks_onnx: baked kernel_shape on {} nodes, made {} inputs dynamic, "
        "stripped stale shape info -> {}".format(baked, dyn, dst)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
