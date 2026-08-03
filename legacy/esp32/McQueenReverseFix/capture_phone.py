#!/usr/bin/env python3
from __future__ import annotations

import json
import socket
import statistics
import time
from collections import Counter
from pathlib import Path

PORT = 5008
OUT = Path.home() / "mcqueen_reverse_calibration.json"
PHASE_SECONDS = 2.0

def parse_packet(data: bytes):
    text = data.decode("utf-8", errors="replace").strip()
    fields = [x.strip() for x in text.split(",")]
    nums = []
    for x in fields:
        try:
            nums.append(int(float(x)))
        except ValueError:
            nums.append(None)
    return text, fields, nums

def capture_phase(sock, name, instruction):
    input(f"\n{name}: {instruction}\nPress ENTER, then do it immediately...")
    end = time.monotonic() + PHASE_SECONDS
    rows = []
    while time.monotonic() < end:
        try:
            data, addr = sock.recvfrom(2048)
        except socket.timeout:
            continue
        text, fields, nums = parse_packet(data)
        rows.append({"text": text, "fields": fields, "nums": nums, "addr": list(addr)})
    if not rows:
        raise SystemExit(
            f"No packets received during {name}. "
            "Set Kachow CAR IP to this laptop's 192.168.4.x address and keep the phone armed."
        )
    counts = Counter(r["text"] for r in rows)
    representative = counts.most_common(1)[0][0]
    rep = next(r for r in reversed(rows) if r["text"] == representative)
    print(f"Captured {len(rows)} packets")
    print("Representative:", rep["text"])
    return rows, rep

def median_vector(rows, n):
    out = []
    for i in range(n):
        vals = [r["nums"][i] for r in rows if len(r["nums"]) == n and r["nums"][i] is not None]
        out.append(statistics.median(vals) if vals else None)
    return out

def changed(a, b, threshold=80):
    return a is not None and b is not None and abs(a - b) >= threshold

def main():
    ip_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ip_sock.connect(("192.168.4.1", 9))
    laptop_ip = ip_sock.getsockname()[0]
    ip_sock.close()

    print("=" * 72)
    print("MCQUEEN PHONE PACKET CALIBRATION")
    print("Laptop IP:", laptop_ip)
    print("On the phone:")
    print("  1. Connect to KACHOW-CAR")
    print(f"  2. Set CAR IP to {laptop_ip}")
    print("  3. Camera can stay OFF")
    print("  4. ARM the controller")
    print("  5. Keep driven wheels lifted")
    print("=" * 72)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", PORT))
    sock.settimeout(0.2)

    phases = {}
    reps = {}
    specs = [
        ("neutral", "leave steering and throttle exactly neutral"),
        ("forward", "hold throttle FORWARD, steering neutral"),
        ("reverse", "hold throttle fully in REVERSE, steering neutral"),
        ("left", "hold steering LEFT, throttle neutral"),
        ("right", "hold steering RIGHT, throttle neutral"),
    ]
    for key, instruction in specs:
        phases[key], reps[key] = capture_phase(sock, key.upper(), instruction)

    lengths = [len(r["fields"]) for p in phases.values() for r in p]
    token_count = Counter(lengths).most_common(1)[0][0]
    med = {k: median_vector(v, token_count) for k, v in phases.items()}

    print("\nMedian numeric fields")
    print("index | neutral | forward | reverse | left | right")
    for i in range(token_count):
        print(
            f"{i:5d} | {str(med['neutral'][i]):>7} | {str(med['forward'][i]):>7} | "
            f"{str(med['reverse'][i]):>7} | {str(med['left'][i]):>7} | {str(med['right'][i]):>7}"
        )

    throttle_candidates = []
    suspect_throttle = []
    steer_candidates = []

    for i in range(token_count):
        n, f, r = med["neutral"][i], med["forward"][i], med["reverse"][i]
        l, rr = med["left"][i], med["right"][i]

        if all(v is not None for v in (n, f, r)):
            if f > n + 80 and r < n - 80:
                throttle_candidates.append(i)
            elif changed(n, f) or changed(n, r):
                suspect_throttle.append(i)

        if all(v is not None for v in (n, l, rr)):
            if (l < n - 80 and rr > n + 80) or (l > n + 80 and rr < n - 80):
                steer_candidates.append(i)

    throttle_index = throttle_candidates[0] if len(throttle_candidates) == 1 else None
    steer_index = steer_candidates[0] if len(steer_candidates) == 1 else None

    result = {
        "laptop_ip": laptop_ip,
        "token_count": token_count,
        "throttle_index": throttle_index,
        "steer_index": steer_index,
        "throttle_candidates": throttle_candidates,
        "suspect_throttle_indices": suspect_throttle,
        "steer_candidates": steer_candidates,
        "android_reverse_valid": throttle_index is not None,
        "representative_packets": {k: v["text"] for k, v in reps.items()},
        "median_numeric_fields": med,
    }
    OUT.write_text(json.dumps(result, indent=2))

    print("\n" + "=" * 72)
    print("Saved:", OUT)

    if throttle_index is None:
        print("RESULT: Android did NOT provide one clear signed reverse throttle field.")
        print("Suspect throttle fields:", suspect_throttle)
        print("Do NOT flash new firmware yet. Patch/rebuild the Android app first.")
        return

    print("RESULT: Android sends valid signed reverse throttle.")
    print("Throttle field index:", throttle_index)
    print("Steering field index:", steer_index)
    print("=" * 72)

    answer = input(
        "\nType SEND to transmit the exact captured reverse packet directly "
        "to ESP32 192.168.4.1 for 1 second: "
    ).strip()
    if answer != "SEND":
        print("Direct reverse test skipped.")
        return

    reverse_packet = reps["reverse"]["text"].encode("utf-8")
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    end = time.monotonic() + 1.0
    while time.monotonic() < end:
        tx.sendto(reverse_packet, ("192.168.4.1", 5007))
        time.sleep(1 / 30)
    # Send exact neutral packet afterwards.
    neutral_packet = reps["neutral"]["text"].encode("utf-8")
    for _ in range(12):
        tx.sendto(neutral_packet, ("192.168.4.1", 5007))
        time.sleep(1 / 30)
    print("Reverse packet test finished; neutral packet sent.")

if __name__ == "__main__":
    main()
