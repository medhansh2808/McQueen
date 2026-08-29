"""camera_arbiter.py — automatic camera handoff on the Jetson.

Desired mode comes from a flag file: /tmp/mcqueen_mode  ("ai" or "human").
  ai    -> mcqueen-edge stopped; gst sender runs (owns camera); CTRL->edge relay feeds
           C-packets to edge :5007 which is RESTARTED CAMERA-LESS (gate + failsafe live)
  human -> sender stopped; mcqueen-edge restarted WITH camera (KACHOW teleop + RECORD)

Usage (Jetson):  python3 camera_arbiter.py --sender-script /home/sravjti/start_sender.sh
Writes its own state to /tmp/mcqueen_arbiter_state.
"""
import argparse
import os
import subprocess
import time

FLAG = "/tmp/mcqueen_mode"
STATE = "/tmp/mcqueen_arbiter_state"
EDGE = "mcqueen-edge.service"


def run(cmd, check=False):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, check=check)


def desired():
    try:
        with open(FLAG) as f:
            return f.read().strip().lower()
    except OSError:
        return "human"


def sender_running():
    return run("pgrep -f gst_jetson_rtp_wan.py").returncode == 0


def edge_active():
    return run("systemctl is-active {}".format(EDGE)).stdout.strip() == "active"


def set_mode(mode):
    if mode == "ai":
        # sender owns camera; edge restarts camera-less (gate stays up)
        if not sender_running():
            run(args.sender_script)
        run("sudo -n systemctl stop {} 2>/dev/null || true".format(EDGE))
        time.sleep(1)
        run("sudo -n systemctl start {} || true".format(EDGE))
    else:
        if sender_running():
            run("pkill -f 'gst_jetson_rtp_wa[n].py'")
            time.sleep(1)
        run("sudo -n systemctl restart {}".format(EDGE))


def main():
    global args
    ap = argparse.ArgumentParser()
    ap.add_argument("--sender-script", required=True,
                    help="script that launches gst_jetson_rtp_wan.py in AI mode")
    ap.add_argument("--interval", type=float, default=2.0)
    args = ap.parse_args()

    print("[arbiter] watching {} (default human)".format(FLAG), flush=True)
    last = None
    while True:
        want = desired()
        running_state = "ai" if sender_running() else "human"
        if want != last:
            print("[arbiter] desired={} -> converging".format(want), flush=True)
            set_mode(want if want in ("ai", "human") else "human")
            last = want
            with open(STATE, "w") as f:
                f.write("{}\n".format(running_state))
        elif want != running_state and want == "ai":
            # sender died mid-ai -> re-launch it
            set_mode("ai")
        elif want == "human" and not edge_active():
            run("sudo -n systemctl restart {}".format(EDGE))
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
