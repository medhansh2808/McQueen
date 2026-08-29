# Edge runtime (`edge/`)

The edge runtime runs on the **Jetson Nano in the car**. It owns the actuators and is the only component that can move the servo and motor.

## Components

| File | Role |
|---|---|
| `app.py` | entrypoint; wires server, drive backend, recorder, encoder |
| `server.py` | UDP teleop server (phone commands) |
| `drive.py` | drive backend abstraction + mock backend |
| `jetson_gpio.py` | real GPIO/PWM backend (TB6612 + MG995) |
| `encoder_source.py` | wheel encoder reading (null/synthetic/real) |
| `gpio_encoder_source.py` | GPIO-polling encoder source |
| `recorder.py` | raw frame + drive state spooling to `data/spool` |
| `record_row.py` | CSV row builder (see `docs/architecture.md` for schema) |
| `http_server.py` | local status/debug HTTP endpoints |
| `protocol.py` | UDP packet protocol definitions |

## Running

```bash
python3 edge/app.py --jetson \
  --servo-left-us 1750 --servo-center-us 1500 --servo-right-us 1275
```

Jetson mode refuses to start without measured servo calibration values.

## Safety gate

- **AUTO requires explicit authorization** from the phone. The remote model never grants itself authority.
- Predictions are rejected when: not authorized, stale (`prediction_timeout_ms = 250`), or out of range (servo 45–115°, forward PWM ≤ 100, reverse PWM ≤ 70).
- Any failure triggers `safe_stop`: center servo (90°) and motor PWM 0.
- The edge also safe-stops if no control packets arrive within its failsafe timeout — teleop (UDP `:5007`) still works.

## Recorder

While recording, each frame row is spooled under `data/spool/` as CSV with the schema in `mcqueen_ml/dataset/schema_v2.py`; frames are referenced by relative path. Sessions are later converted to training datasets.