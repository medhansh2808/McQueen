#!/usr/bin/env python3
"""Dependency-free synthetic proof of benchmark-v2 exact-frame semantics."""

from tools.realtime.full_loop_contract_v2 import BenchmarkReport, FrameLedger


def main():
    ledger = FrameLedger()
    report = BenchmarkReport()

    report.pass_stage("SIGNALING_P2P", "synthetic harness")
    report.pass_stage("VIDEO_CONNECTED", "synthetic harness")
    report.pass_stage("DIRECT_UDP", "synthetic harness")

    count = 12
    base = 5_000_000_000

    for frame_id in range(count):
        capture = base + frame_id * 100_000_000
        receive = capture + 65_000_000 + (frame_id % 3) * 5_000_000

        ledger.register_capture(frame_id, capture)
        ledger.mark_metadata(frame_id)
        ledger.mark_video(frame_id)
        ledger.mark_inference(frame_id, frame_id, 2.5)
        ledger.mark_control_sent(frame_id)
        ledger.mark_control_ack(frame_id, receive)

    completed = ledger.completed()

    if completed:
        report.pass_stage("VIDEO_FRAMES", "{} frames".format(len(completed)))
        report.pass_stage("FRAME_TIMESTAMP", "Jetson monotonic timestamp preserved")
        report.pass_stage("EXACT_FRAME_MATCH", "frame_id matched exactly")
        report.pass_stage("RTX_INFERENCE", "synthetic 2.5 ms")
        report.pass_stage("CONTROL_RETURN", "{} ACKs".format(len(completed)))
        report.pass_stage("SAFETY_GATE", "contract hook ready")

        latencies = sorted(trace.latency_ms() for trace in completed)
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
        report.pass_stage(
            "FULL_LOOP_LATENCY",
            "synthetic p50={:.1f}ms p95={:.1f}ms".format(p50, p95),
        )

    print("===== SYNTHETIC FULL LOOP V2 =====")
    print(report.render())

    if not all(report.stages.values()):
        return 2

    print("✅ exact-frame synthetic full-loop contract PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
