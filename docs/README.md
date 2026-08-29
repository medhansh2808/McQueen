# Documentation

Guides for the McQueen autonomous RC car project.

| Guide | Covers |
|---|---|
| [Architecture](architecture.md) | End-to-end system: edge runtime, RTP transport, RTX policy worker, broker |
| [Hardware](hardware.md) | Wiring, BOM and servo/ESC actuation |
| [Installation](installation.md) | Setup for the Jetson, RTX workstation and phone controller |
| [Edge](edge.md) | Jetson edge runtime: teleop server, recorder, safety gate |
| [Realtime](realtime.md) | Realtime inference stack: RTP sender, receiver, policy worker, broker |

For a quick overview see the [repository README](../README.md). The runtime entry points live in [edge](../edge) and [realtime](../realtime).