from robot.jetson_nano.mcqueen_edge.protocol import parse_phone_packet, make_status

hello = parse_phone_packet(b"H,rc-car,abcd1234,1,123456789\n")
command = parse_phone_packet(b"C,rc-car,abcd1234,2,123456790,-250,700,1\n")
emergency = parse_phone_packet(b"E,rc-car,abcd1234,3,123456791\n")
resume = parse_phone_packet(b"R,rc-car,abcd1234,4,123456792\n")

status = make_status(
    session="abcd1234",
    sequence=2,
    echo_timestamp_ms=123456790,
    commanded_steering=-250,
    actual_servo_angle=89,
    commanded_throttle=700,
    actual_throttle=700,
    failsafe=False,
)

assert hello["type"] == "H"
assert command["steering"] == -250
assert command["throttle"] == 700
assert command["motor_enabled"] is True
assert emergency["type"] == "E"
assert resume["type"] == "R"
assert resume["sequence"] == 4
assert status == "S,abcd1234,2,123456790,-250,89,700,700,0,JETSON,-1\n"
assert parse_phone_packet(b"C,wrong-token,x,1,1,0,0,0\n") is None
assert parse_phone_packet(b"R,wrong-token,x,1,1\n") is None
assert parse_phone_packet(b"R,rc-car,x,1,1,0,0,0\n") is not None

print("HELLO     :", hello)
print("COMMAND   :", command)
print("EMERGENCY :", emergency)
print("STATUS    :", status.strip())
print("SELF-TEST : PASS")
