"""dump_chestnut_slices.py — extract openpilot 'output_slices' from ONNX metadata.

The model embeds a base64 pickle under metadata_props key 'output_slices'.
Prints every named slice with its start:stop (offset/width) so the adapter can
slice the flattened 2580 output.

Usage:
    python dump_chestnut_slices.py big_driving_supercombo.onnx
"""

import base64
import codecs
import pickle
import sys

import onnx


def main(path: str) -> int:
    model = onnx.load(path, load_external_data=False)
    props = {p.key: p.value for p in model.metadata_props}
    print("metadata keys:", sorted(props.keys()))
    ckpt = props.get("model_checkpoint")
    if ckpt:
        print(f"model_checkpoint: {ckpt}")
    raw = props.get("output_slices")
    if raw is None:
        print("NO output_slices key")
        return 1
    slices = pickle.loads(codecs.decode(raw.encode(), "base64"))
    print(f"\noutput_slices ({len(slices)}):")
    for name in sorted(slices, key=lambda k: slices[k].start):
        s = slices[name]
        print(f"  {name:28s} [{s.start:5d}:{s.stop:5d})  width={s.stop-s.start}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))