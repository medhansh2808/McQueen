"""Analyze encoder sweep CSV -> summary table + deadband + convention.

Runs on the LAPTOP (no Jetson.GPIO needed). Pure stdlib.

Usage:
  python3 tools/encoder/analyze_sweep.py --csv encoder_sweep.csv \
      --ticks-per-rev 100 --out summary.csv

Outputs:
  - summary CSV: duty, fwd_rpm, rev_rpm, fwd_ticks_s, rev_ticks_s
  - stdout: deadband, direction-convention check, linear-fit slope
    (RPM per duty), symmetry ratio (|rev|/fwd at matched duties)

Python 3.6 compatible.
"""

import argparse
import csv
import sys


def _read_csv(path):
    rows = []
    with open(path, "r", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append({
                "direction": row["direction"],
                "duty": float(row["duty"]),
                "ticks_per_s": float(row["ticks_per_s"]),
                "rpm": float(row["rpm"]),
            })
    return rows


def _linear_slope(xs, ys):
    n = len(xs)
    if n < 2:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)
    return num / den if den > 0 else 0.0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, help="sweep CSV from the Jetson")
    parser.add_argument("--ticks-per-rev", type=float, required=True)
    parser.add_argument("--out", default="encoder_summary.csv")
    args = parser.parse_args()

    rows = _read_csv(args.csv)
    if not rows:
        print("FATAL: empty CSV")
        sys.exit(1)

    by_dir = {}
    for row in rows:
        by_dir.setdefault(row["direction"], []).append(row)

    fwd = by_dir.get("FWD", [])
    rev = by_dir.get("REV", [])
    if not fwd and not rev:
        print("FATAL: no FWD/REV rows found")
        sys.exit(1)

    moving = [r for r in fwd + rev if abs(r["ticks_per_s"]) > 1.0]
    if moving:
        deadband = min(moving, key=lambda r: r["duty"])
        print("DEADBAND: first duty with movement = %.2f (dir %s)"
              % (deadband["duty"], deadband["direction"]))
    else:
        print("DEADBAND: NONE detected (no movement in any step)")

    fwd_moving = [r for r in fwd if r["rpm"] > 0]
    rev_moving = [r for r in rev if r["rpm"] < 0]
    fwd_slope = _linear_slope([r["duty"] for r in fwd_moving],
                              [r["rpm"] for r in fwd_moving])
    rev_slope = _linear_slope([r["duty"] for r in rev_moving],
                              [abs(r["rpm"]) for r in rev_moving])
    print("FWD slope: %.1f RPM per duty (linear fit over %d points)"
          % (fwd_slope, len(fwd_moving)))
    print("REV slope: %.1f RPM per duty (linear fit over %d points)"
          % (rev_slope, len(rev_moving)))
    if fwd and fwd[0]["rpm"] > 0:
        print("CONVENTION: FWD direction counts POSITIVE -> keep default")
    elif fwd and fwd[0]["rpm"] < 0:
        print("CONVENTION: FWD direction counts NEGATIVE -> use --invert-dir")
    else:
        print("CONVENTION: check first FWD row manually")

    matched = []
    by_duty = {}
    for r in fwd:
        by_duty.setdefault(r["duty"], {})["fwd"] = r["rpm"]
    for r in rev:
        by_duty.setdefault(r["duty"], {})["rev"] = abs(r["rpm"])
    for duty, pair in sorted(by_duty.items()):
        if "fwd" in pair and "rev" in pair and pair["fwd"] > 0:
            matched.append((duty, pair["fwd"], pair["rev"]))
    if matched:
        ratios = [r / f for _, f, r in matched if f > 0]
        print("SYMMETRY: mean |rev|/fwd over %d matched duties = %.2f"
              % (len(matched), sum(ratios) / len(ratios)))

    with open(args.out, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["duty", "fwd_rpm", "rev_rpm",
                         "fwd_ticks_per_s", "rev_ticks_per_s"])
        duties = sorted(set(r["duty"] for r in rows))
        fwd_map = {r["duty"]: r for r in fwd}
        rev_map = {r["duty"]: r for r in rev}
        for duty in duties:
            f = fwd_map.get(duty)
            r = rev_map.get(duty)
            writer.writerow([
                duty,
                f["rpm"] if f else "",
                r["rpm"] if r else "",
                f["ticks_per_s"] if f else "",
                r["ticks_per_s"] if r else "",
            ])
    print("summary CSV written: %s (ticks_per_rev=%.2f)"
          % (args.out, args.ticks_per_rev))


if __name__ == "__main__":
    main()