from robot.jetson_nano.mcqueen_edge.protocol import parse_phone_packet
from robot.jetson_nano.mcqueen_edge.drive import DriveController, MockDriveBackend


def pkt(raw):
    return parse_phone_packet(raw.encode("ascii"))


backend = MockDriveBackend()
drive = DriveController(backend, failsafe_seconds=0.300)

# New session immediately forces a safe stop.
assert drive.handle_packet(pkt("H,rc-car,session1,1,1000\n"), now=10.0) == "hello"
assert backend.calls[-1] == ("estop",)

# Motion before a neutral command is refused.
result = drive.handle_packet(
    pkt("C,rc-car,session1,2,1001,300,500,1\n"),
    now=10.01,
)
assert result == "awaiting-neutral"
assert drive.motor_enabled is False

# Neutral command arms the session.
result = drive.handle_packet(
    pkt("C,rc-car,session1,3,1002,0,0,0\n"),
    now=10.02,
)
assert result == "applied"
assert drive.session_armed is True
assert backend.calls[-1] == ("apply", 0, 0, False)

# Normal drive command is applied.
result = drive.handle_packet(
    pkt("C,rc-car,session1,4,1003,-250,700,1\n"),
    now=10.03,
)
assert result == "applied"
assert backend.calls[-1] == ("apply", -250, 700, True)
assert drive.steering == -250
assert drive.throttle == 700
assert drive.motor_enabled is True
assert drive.failsafe is False

# Duplicate/out-of-order packets are ignored.
result = drive.handle_packet(
    pkt("C,rc-car,session1,4,1004,900,900,1\n"),
    now=10.04,
)
assert result == "stale"
assert backend.calls[-1] == ("apply", -250, 700, True)

# Missing commands trigger the independent controller failsafe.
assert drive.enforce_failsafe(now=10.40) is True
assert backend.calls[-1] == ("estop",)
assert drive.throttle == 0
assert drive.motor_enabled is False
assert drive.failsafe is True
assert drive.failsafe_reason == "command timeout"

# New session requires neutral again.
result = drive.handle_packet(
    pkt("C,rc-car,session2,1,2000,0,600,1\n"),
    now=11.0,
)
assert result == "awaiting-neutral"
assert drive.session_armed is False

# Phone emergency packet always stops and disarms.
drive.handle_packet(pkt("C,rc-car,session2,2,2001,0,0,0\n"), now=11.01)
drive.handle_packet(pkt("C,rc-car,session2,3,2002,100,400,1\n"), now=11.02)
assert drive.motor_enabled is True

result = drive.handle_packet(
    pkt("E,rc-car,session2,4,2003\n"),
    now=11.03,
)
assert result == "estop"
assert backend.calls[-1] == ("estop",)
assert drive.session_armed is False
assert drive.motor_enabled is False

print("FINAL STATE:", drive.snapshot())
print("BACKEND CALLS:", backend.calls)
print("DRIVE SAFETY SELF-TEST : PASS")
