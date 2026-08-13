"""Dependency-free temporal indexing rules for McQueen training."""

NEUTRAL_ACTION = (90.0, 0.0)


def build_temporal_positions(target_position, history):
    """Return source frame positions and previous-action positions.

    Frame positions are left-padded with episode frame 0.
    Previous-action position is None whenever the requested observation is at
    or before episode start; None means use the neutral action.
    """
    target_position = int(target_position)
    history = int(history)

    if target_position < 0:
        raise ValueError("target_position must be >= 0")
    if history < 2:
        raise ValueError("history must be >= 2")

    start = target_position - history + 1
    frame_positions = []
    previous_action_positions = []

    for requested_position in range(start, target_position + 1):
        frame_positions.append(max(0, requested_position))
        if requested_position <= 0:
            previous_action_positions.append(None)
        else:
            previous_action_positions.append(requested_position - 1)

    return frame_positions, previous_action_positions
