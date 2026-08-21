"""test_tub_to_sessions.py — converter unit test (pure python, no torch).

Builds a fake catalog tub in a temp dir, converts it, and asserts:
  - train/val split ratio and contiguity
  - session dir layout (controls.csv + rgb_raw_upright/frame_*.jpg)
  - label values round-trip exactly
  - split.json metadata
"""

import csv
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "tub_to_sessions.py"


def make_fake_tub(root: Path, n: int, jpg_bytes: bytes) -> Path:
    tub = root / "tub"
    images = tub / "images"
    images.mkdir(parents=True)
    catalogs = []
    split = (n + 1) // 2
    for start, stop in ((0, split), (split, n)):
        cat = tub / f"catalog_{len(catalogs)}.catalog"
        with open(cat, "w") as f:
            for i in range(start, stop):
                img = images / f"{i}_cam_image_array_.jpg"
                img.write_bytes(jpg_bytes)
                rec = {
                    "_index": i,
                    "_session_id": "fake_0",
                    "_timestamp_ms": 1620000000000 + i,
                    "cam/image_array": img.name,
                    "user/angle": round(-1.0 + 2.0 * i / max(n - 1, 1), 6),
                    "user/mode": "user",
                    "user/throttle": round(0.5 + 0.1 * i, 6),
                }
                f.write(json.dumps(rec) + "\n")
        catalogs.append(cat)
    return tub


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # 1x1 valid JPEG (PIL-generated equivalent constant bytes)
        jpg = (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\x09\x09\x08"
            b"\x0a\x0c\x14\x0d\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d"
            b"\x1a\x1c\x1c  $ \x80&\x1b'()9-*:7F:788\xff\xc0\x00\x0b\x08\x00\x01\x00\x01"
            b"\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01"
            b"\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff"
            b"\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00"
            b"\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07\"q\x142\x81\x91"
            b"\xa8\xb4\xd1\xd2\xe1#B\xb0\xc1R\x15\x16\x92r$\xb2\x81\x93\xa2\xc2\xa3"
            b"\xb3\xe3\xf4\xf5\xff\xc4\x00\x1f\x01\x00\x03\x01\x01\x01\x01\x01\x01\x01"
            b"\x01\x01\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
            b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xf0\xf5\xa4J\xff\xd9"
        )
        n = 101  # 81 train / 20 val at 0.2
        tub = make_fake_tub(root, n, jpg)
        out = root / "sessions"

        r = subprocess.run(
            [sys.executable, str(SCRIPT), "--tub", str(tub), "--out", str(out),
             "--val-frac", "0.2", "--chunk", "30"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, f"converter failed:\n{r.stdout}\n{r.stderr}"

        meta = json.loads((out / "split.json").read_text())
        assert meta["total_records"] == n
        assert meta["counts"]["train"][0] == 81, meta["counts"]
        assert meta["counts"]["val"][0] == 20, meta["counts"]
        assert meta["frame_format"] == "jpg"

        # session layout: chunk=30 -> train 3 sessions (30/30/21), val 1 session (20)
        assert meta["counts"]["train"][1] == 3, meta["counts"]
        assert meta["counts"]["val"][1] == 1, meta["counts"]

        # spot-check labels round-trip: last train record = index 80
        t3 = out / "train" / "session_002"
        with open(t3 / "controls.csv") as f:
            rows = list(csv.reader(f))
        assert rows[0] == ["steering", "throttle"]
        assert len(rows) - 1 == 21
        last = rows[-1]
        assert abs(float(last[0]) - round(-1.0 + 2.0 * 80 / 100, 6)) < 1e-9
        frames = sorted((t3 / "rgb_raw_upright").glob("frame_*.jpg"))
        assert len(frames) == 21
        assert frames[0].name == "frame_000000.jpg"
        assert frames[-1].name == "frame_000020.jpg"

        # val = contiguous tail: records 81..100
        v0 = out / "val" / "session_000"
        with open(v0 / "controls.csv") as f:
            vrows = list(csv.reader(f))[1:]
        assert len(vrows) == 20
        assert abs(float(vrows[0][0]) - round(-1.0 + 2.0 * 81 / 100, 6)) < 1e-9

        # no overwrite: rerun must fail
        r2 = subprocess.run(
            [sys.executable, str(SCRIPT), "--tub", str(tub), "--out", str(out)],
            capture_output=True, text=True,
        )
        assert r2.returncode != 0, "rerun should refuse to overwrite"

    print("test_tub_to_sessions: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
