# deploy — systemd units

Units for the Jetson (and RTX) hosts.

| Unit | Host | Purpose |
|---|---|---|
| [mcqueen-edge.service](systemd/mcqueen-edge.service) | Jetson | Edge runtime: teleop server, recorder, safety gate |
| [mcqueen-recorder.service](systemd/mcqueen-recorder.service) | Jetson | Recording service |
| [mcqueen-recorder.path](systemd/mcqueen-recorder.path) | Jetson | Path-triggered recording |
| [mcqueen-jetson-ssh-tunnel.service](systemd/mcqueen-jetson-ssh-tunnel.service) | Jetson | SSH tunnel to the RTX host |
| [mcqueen-jetson-url-report.service](systemd/mcqueen-jetson-url-report.service) | Jetson | Reports the Cloudflare tunnel URL |
| [mcqueen-jetson-url-report.timer](systemd/mcqueen-jetson-url-report.timer) | Jetson | Timer for the URL report |

Install steps: [docs/installation.md](../docs/installation.md).