# McQueen realtime inference architecture (v1)

## Vehicle side

Jetson:
1. capture camera frame;
2. assign exact `frame_id`;
3. stamp Jetson monotonic capture time;
4. hardware-encode H.264;
5. send video via WebRTC;
6. receive returned prediction via direct UDP;
7. enforce authority/freshness/range/speed safety;
8. actuate only if allowed.

## RTX side

RTX:
1. receive/decode newest useful video;
2. associate inference with exact frame identity;
3. preprocess temporal observation history;
4. run PyTorch policy;
5. return action carrying the same frame identity and capture timestamp.

## Transport

- video: WebRTC
- signaling/rendezvous: WebSocket/WSS broker when required
- action return: direct UDP

## Proven pieces

Real direct-WAN action-return path:
- 60/60 ACKs
- p50 RTT 43.1 ms
- p95 RTT 70.4 ms
- Jetson dry-run / zero GPIO

Real camera-compute path:
- Lenovo camera
- Jetson hardware H.264 encode
- WebRTC
- RTX decode/appsink
- CUDA/PyTorch dummy action

The successful camera-compute proof used a local lab route.

## Authoritative full-loop measurement

Returned prediction must echo the exact Jetson `frame_id` and capture monotonic timestamp.
Jetson then computes capture -> returned-command age on one clock.

Benchmark-v2 must report independent stages:

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

A run with zero completed samples must not be labeled as a specific transport failure unless that
stage was independently observed to fail.

## Current safety target

- steering range 45..115 deg, center 90
- forward cap +100 PWM
- reverse cap magnitude 70 PWM
- prediction timeout 250 ms
- stale prediction -> zero PWM, center steering, cancel AUTO

## Not yet measured

There is not yet an authoritative final separate-WAN camera-capture -> RTX inference -> returned
command full-loop latency result.
