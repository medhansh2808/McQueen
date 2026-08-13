"""Exact-frame full-loop benchmark bookkeeping for McQueen.

Dependency-free. This does not create WebRTC or UDP transports by itself.
It prevents the old benchmark from reporting an ambiguous "0 controls".
"""

from dataclasses import dataclass, field


STAGE_NAMES = (
    "SIGNALING_P2P",
    "VIDEO_CONNECTED",
    "VIDEO_FRAMES",
    "FRAME_TIMESTAMP",
    "EXACT_FRAME_MATCH",
    "RTX_INFERENCE",
    "DIRECT_UDP",
    "CONTROL_RETURN",
    "SAFETY_GATE",
    "FULL_LOOP_LATENCY",
)


@dataclass
class FrameTrace:
    frame_id: int
    capture_mono_ns: int
    video_seen: bool = False
    metadata_seen: bool = False
    inference_ms: float = 0.0
    prediction_frame_id: int = -1
    control_sent: bool = False
    control_ack: bool = False
    receive_mono_ns: int = 0

    def latency_ms(self):
        if not self.control_ack or self.receive_mono_ns <= 0:
            return None
        return (self.receive_mono_ns - self.capture_mono_ns) / 1_000_000.0

    def exact_match(self):
        return self.prediction_frame_id == self.frame_id


@dataclass
class BenchmarkReport:
    stages: dict = field(default_factory=lambda: {
        name: False for name in STAGE_NAMES
    })
    details: dict = field(default_factory=dict)

    def pass_stage(self, name, detail=""):
        if name not in self.stages:
            raise KeyError(name)
        self.stages[name] = True
        if detail:
            self.details[name] = str(detail)

    def fail_stage(self, name, detail=""):
        if name not in self.stages:
            raise KeyError(name)
        self.stages[name] = False
        if detail:
            self.details[name] = str(detail)

    def render(self):
        lines = []
        for name in STAGE_NAMES:
            state = "PASS" if self.stages[name] else "FAIL"
            detail = self.details.get(name, "")
            if detail:
                lines.append("{:<20} {}  {}".format(name, state, detail))
            else:
                lines.append("{:<20} {}".format(name, state))
        return "\n".join(lines)


class FrameLedger:
    def __init__(self):
        self.frames = {}

    def register_capture(self, frame_id, capture_mono_ns):
        frame_id = int(frame_id)
        if frame_id in self.frames:
            raise ValueError("duplicate frame_id {}".format(frame_id))
        self.frames[frame_id] = FrameTrace(
            frame_id=frame_id,
            capture_mono_ns=int(capture_mono_ns),
        )

    def mark_metadata(self, frame_id):
        self.frames[int(frame_id)].metadata_seen = True

    def mark_video(self, frame_id):
        self.frames[int(frame_id)].video_seen = True

    def mark_inference(self, frame_id, prediction_frame_id, inference_ms):
        trace = self.frames[int(frame_id)]
        trace.prediction_frame_id = int(prediction_frame_id)
        trace.inference_ms = float(inference_ms)

    def mark_control_sent(self, frame_id):
        self.frames[int(frame_id)].control_sent = True

    def mark_control_ack(self, frame_id, receive_mono_ns):
        trace = self.frames[int(frame_id)]
        trace.control_ack = True
        trace.receive_mono_ns = int(receive_mono_ns)

    def completed(self):
        return [
            trace for trace in self.frames.values()
            if (
                trace.metadata_seen
                and trace.video_seen
                and trace.exact_match()
                and trace.control_sent
                and trace.control_ack
            )
        ]
