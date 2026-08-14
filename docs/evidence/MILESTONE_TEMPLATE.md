# Milestone Report Template

File a copy of this as `docs/evidence/<YYYY-MM-DD>/<milestone-name>/REPORT.md`
via `tools/realtime/capture_evidence.sh` after EVERY verified milestone. A
milestone is only "green" when the report below is filled with actual
measurements. No zero-sample milestone is ever labeled as a specific transport
failure (AGENTS.md §E).

## 1. Identity

- Milestone: `e.g. rtp-wan-green`
- Date/time: `YYYY-MM-DD HH:MM (local)`
- Machine(s): `laptop / jetson / rtx` — which ran what
- Repo commit: `<git rev-parse HEAD>` + `git status` (expected: uncommitted
  changes, DECISION 013 — nothing is committed without hardware verification)
- Test performed with drivetrain: `disconnected / simulated / connected`

## 2. Stage measurements

Every benchmark-v2 stage reports `n`, `p50`, `p95` independently. A stage with
`n = 0` is written as `UNVERIFIED`, never as a pass or a transport failure.
Failed stages must identify themselves by name.

| Stage | n | p50 (ms) | p95 (ms) | Result |
|---|---|---|---|---|
| SIGNALING_P2P | | | | VERIFIED / FAILED / UNVERIFIED |
| VIDEO_CONNECTED | | | | |
| VIDEO_FRAMES | | | | |
| FRAME_TIMESTAMP | | | | |
| EXACT_FRAME_MATCH | | | | |
| RTX_INFERENCE | | | | |
| DIRECT_UDP | | | | |
| CONTROL_RETURN | | | | |
| SAFETY_GATE | | | | |
| FULL_LOOP_LATENCY | | | | |

## 3. Artifacts filed

| Artifact | Path in this folder | Source machine |
|---|---|---|
| sender log | `jetson/...` | Jetson |
| receiver log | `rtx/...` | RTX |
| run script output | `...` | laptop |
| probe output | `...` | Jetson / RTX |

## 4. Verification notes

- Frames used for latency: `frame_id` + `capture_mono_ns` exact identity —
  FIFO assumptions are never used for frame-metadata association.
- Newest-frame-wins behavior observed: `yes / no`
- Stale-command handling: `verified (log line ...)`
- Safety gate status: `open / closed` (clamp values, fail-safe trigger seen)
- Unexpected events / deviations from plan:

## 5. Verdict

- `GREEN` — all required stages verified with the numbers above
- `BLOCKED` — stage(s) identified above; what they were
- `PARTIALLY VERIFIED` — what passed, what remains

## 6. Next action

One sentence, e.g. "Deploy fixed sender (F1) and re-run; expect EXACT_FRAME_MATCH."