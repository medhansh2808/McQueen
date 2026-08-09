from robot.jetson_nano.mcqueen_edge.server import steering_to_angle


def test_steering_endpoints_and_center():
    assert steering_to_angle(-1000) == 45
    assert steering_to_angle(0) == 90
    assert steering_to_angle(1000) == 115


def test_steering_direction():
    assert steering_to_angle(-500) < 90
    assert steering_to_angle(500) > 90
