"""tub_to_sessions.py — convert a donkeycar catalog tub into McQueen session dirs.

Reads a donkeycar v5 catalog tub (catalog_*.catalog JSON-lines + images/) and writes
McQueen-format session directories consumable by train_frozen_action.py / eval:
    <out_root>/session_XXX/
        controls.csv                          (columns: steering, throttle; one row per record)
        rgb_raw_upright/frame_000000.jpg ...  (original-size JPEGs, zero-padded names)

Split: contiguous 80/20 by record order (time) — no temporal leakage between train
and val. Records are chunked into sub-sessions of --chunk frames so the temporal
trainer's features_buffer resets on real time boundaries.

Torch-free (DECISION 024): standard-library only, runs on any python3.

Usage:
    python tools/donkey/tub_to_sessions.py \
        --tub ~/donkey_datasets/circuit_launch_ed_1 \
        --out ~/mcqueen/run/donkey_sessions \
        --val-frac 0.2 --chunk 500
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

ANGLE_KEY = "user/angle"
THROTTLE_KEY = "user/throttle"
IMAGE_KEY = "cam/image_array"

FRAME_DIR = "rgb_raw_upright"
FRAME_PREFIX = "frame_"
FRAME_EXT = ".jpg"


def iter_records(tub: Path):
    """Yield (record, image_path) for every catalog record in tub order."""
    catalogs = sorted(tub.glob("catalog_*.catalog"), key=lambda p: int(p.stem.split("_")[1]))
    if not catalogs:
        raise RuntimeError(f"no catalog_*.catalog files in {tub}")
    images_dir = tub / "images"
    if not images_dir.is_dir():
        raise RuntimeError(f"no images/ dir in {tub}")
    n = 0
    for cat in catalogs:
        with open(cat, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                img_name = rec.get(IMAGE_KEY)
                if not img_name:
                    continue
                img_path = images_dir / img_name
                if not img_path.is_file():
                    raise RuntimeError(f"missing image for record: {img_path}")
                yield rec, img_path
                n += 1
    print(f"read {n} records from {len(catalogs)} catalogs", file=sys.stderr)


def write_session(session_dir: Path, records: list[tuple[dict, Path]]) -> None:
    """Write one McQueen session dir from (record, image_path) pairs."""
    frame_dir = session_dir / FRAME_DIR
    frame_dir.mkdir(parents=True, exist_ok=False)
    width = max(6, len(str(len(records) - 1)))
    with open(session_dir / "controls.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["steering", "throttle"])
        for i, (rec, img_path) in enumerate(records):
            writer.writerow([rec.get(ANGLE_KEY, 0.0), rec.get(THROTTLE_KEY, 0.0)])
            dst = frame_dir / f"{FRAME_PREFIX}{i:0{width}d}{FRAME_EXT}"
            shutil.copyfile(img_path, dst)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tub", required=True, help="donkeycar catalog tub directory")
    ap.add_argument("--out", required=True, help="output root (train/ + val/ subdirs created)")
    ap.add_argument("--val-frac", type=float, default=0.2, help="contiguous fraction for val (0..1)")
    ap.add_argument("--chunk", type=int, default=500, help="records per session")
    args = ap.parse_args()

    tub = Path(args.tub)
    out = Path(args.out)
    if not tub.is_dir():
        sys.exit(f"tub not found: {tub}")
    if args.val_frac <= 0.0 or args.val_frac >= 1.0:
        sys.exit("--val-frac must be in (0, 1)")

    records = list(iter_records(tub))
    if not records:
        sys.exit("no records found")
    total = len(records)
    n_val = int(round(total * args.val_frac))
    n_val = min(max(n_val, 1), total - 1)
    n_train = total - n_val
    print(f"total records: {total}  ->  train {n_train} / val {n_val} (contiguous tail)")

    splits = {
        "train": records[:n_train],
        "val": records[n_train:],
    }
    counts = {}
    for name, recs in splits.items():
        root = out / name
        if root.exists():
            sys.exit(f"refusing to overwrite existing root: {root}")
        root.mkdir(parents=True)
        n_sessions = 0
        for i in range(0, len(recs), args.chunk):
            chunk = recs[i : i + args.chunk]
            if len(chunk) < 2:
                continue
            session_dir = root / f"session_{n_sessions:03d}"
            write_session(session_dir, chunk)
            n_sessions += 1
        counts[name] = (len(recs), n_sessions)
        print(f"{name}: {counts[name][0]} records -> {counts[name][1]} sessions")

    with open(out / "split.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "tub": str(tub),
                "total_records": total,
                "val_frac": args.val_frac,
                "chunk": args.chunk,
                "counts": counts,
                "columns": ["steering", "throttle"],
                "frame_format": "jpg",
            },
            f,
            indent=2,
        )
    print(f"done -> {out}")


if __name__ == "__main__":
    main()
