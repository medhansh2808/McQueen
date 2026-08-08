from robot.jetson_nano.mcqueen_edge.app import build_backend, parse_args
from robot.jetson_nano.mcqueen_edge.drive import MockDriveBackend


# Default mode must remain safe and laptop-friendly.
args = parse_args([])
backend = build_backend(args)
assert isinstance(backend, MockDriveBackend)

# Real Jetson mode must refuse to start until actual servo calibration exists.
args = parse_args(["--jetson"])
try:
    build_backend(args)
except ValueError as exc:
    text = str(exc)
    assert "--servo-left-us" in text
    assert "--servo-center-us" in text
    assert "--servo-right-us" in text
else:
    raise AssertionError("Jetson mode accepted missing servo calibration")

print("DEFAULT MODE  : MOCK")
print("JETSON MODE   : requires measured servo calibration")
print("EXTRA CONFIG  : none")
print("EDGE BACKEND SELECTION SELF-TEST : PASS")
