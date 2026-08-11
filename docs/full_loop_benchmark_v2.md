# McQueen full-loop benchmark v2

The old integrated benchmark could collapse multiple failures into "0 controls".
That is no longer acceptable.

The real lab benchmark must report these stages independently:

    SIGNALING_P2P
    VIDEO_CONNECTED
    VIDEO_FRAMES
    FRAME_TIMESTAMP
    EXACT_FRAME_MATCH
    RTX_INFERENCE
    DIRECT_UDP
    CONTROL_RETURN
    SAFETY_GATE
    FULL_LOOP_LATENCY

## Exact frame association

Every captured frame gets a Jetson-origin `frame_id` and
`capture_mono_ns`.

The RTX prediction must echo both values.

A prediction is only paired with the video observation when the `frame_id`
matches exactly. FIFO/deque proximity is forbidden.

## Latency clock

Jetson computes:

    receive_mono_ns - capture_mono_ns

The two timestamps are therefore from the same monotonic clock.

## Newest-frame-wins

The RTX video receiver should discard stale queued frames rather than process
an old backlog.

## Failure behavior

A failed stage must identify itself. No single generic "0 controls" conclusion
may be used to claim ICE, video, metadata, inference, or control failure.
