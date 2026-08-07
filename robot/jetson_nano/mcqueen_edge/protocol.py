"""Phone <-> McQueen Jetson UDP protocol.

Kept compatible with the existing Android controller.
"""

TOKEN = "rc-car"

PACKET_HELLO = "H"
PACKET_COMMAND = "C"
PACKET_EMERGENCY = "E"

MAX_STEERING = 1000
MAX_THROTTLE = 1000


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def parse_phone_packet(payload):
    """Parse one Android UDP packet.

    Returns a dictionary on success, or None for an invalid packet.
    """
    try:
        if isinstance(payload, bytes):
            text = payload.decode("ascii", errors="replace").strip()
        else:
            text = str(payload).strip()

        fields = [field.strip() for field in text.split(",")]

        if len(fields) < 5:
            return None

        packet_type = fields[0]

        if packet_type not in (
            PACKET_HELLO,
            PACKET_COMMAND,
            PACKET_EMERGENCY,
        ):
            return None

        if fields[1] != TOKEN:
            return None

        packet = {
            "type": packet_type,
            "session": fields[2],
            "sequence": int(fields[3]),
            "timestamp_ms": int(fields[4]),
        }

        if packet_type == PACKET_COMMAND:
            if len(fields) != 8:
                return None

            packet["steering"] = clamp(
                int(fields[5]), -MAX_STEERING, MAX_STEERING
            )
            packet["throttle"] = clamp(
                int(fields[6]), -MAX_THROTTLE, MAX_THROTTLE
            )
            packet["motor_enabled"] = int(fields[7]) != 0

        return packet

    except (ValueError, IndexError, TypeError):
        return None


def make_status(
    session,
    sequence,
    echo_timestamp_ms,
    commanded_steering,
    actual_servo_angle,
    commanded_throttle,
    actual_throttle,
    failsafe,
    source="JETSON",
    rssi=-1,
):
    """Generate the exact 11-field status packet Android expects."""
    return (
        "S,{},{},{},{},{},{},{},{},{},{}\n".format(
            session,
            int(sequence),
            int(echo_timestamp_ms),
            int(commanded_steering),
            int(actual_servo_angle),
            int(commanded_throttle),
            int(actual_throttle),
            1 if failsafe else 0,
            source,
            int(rssi),
        )
    )
