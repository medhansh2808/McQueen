"""dump_onnx_io.py — print ONNX graph I/O signature (inputs, outputs, opset, IR).

Dependency-free (onnx only). Used to map the chestnut big model contract before
adapter surgery.

Usage:
    python dump_onnx_io.py big_driving_supercombo.onnx
"""

import sys

import onnx


def fmt_shape(dim):
    parts = []
    for d in dim:
        if d.HasField("dim_value"):
            parts.append(str(d.dim_value))
        elif d.HasField("dim_param"):
            parts.append(d.dim_param)
        else:
            parts.append("?")
    return "(" + "x".join(parts) + ")"


def main(path: str) -> int:
    model = onnx.load(path, load_external_data=False)
    g = model.graph
    print(f"file: {path}")
    print(f"ir_version: {model.ir_version}")
    print(f"opset: " + ", ".join(f"{o.domain or 'ai.onnx'}={o.version}" for o in model.opset_import))
    print(f"nodes: {len(g.node)}")
    print("\nINPUTS:")
    for i in g.input:
        print(f"  {i.name}: {fmt_shape(i.type.tensor_type.shape.dim)} {onnx.TensorProto.DataType.Name(i.type.tensor_type.elem_type)}")
    print("\nOUTPUTS:")
    for o in g.output:
        print(f"  {o.name}: {fmt_shape(o.type.tensor_type.shape.dim)} {onnx.TensorProto.DataType.Name(o.type.tensor_type.elem_type)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))