# CORRIDOR RUNBOOK — McQueen recording session checklist (2026-08-19)

Checklist-driven. Do the boxes IN ORDER. Anything fails → STOP, use the
troubleshooting table, never bypass safety.

Wiring truth: `docs/CAR_WIRING.md`. Code truth: `jetson_gpio.py`
(29=AIN1, 31=AIN2, 32=PWMA, 33=servo, encoder 11/13).

---

## PHASE 0 — WIRING VERIFICATION (power OFF)

- [ ] Motor driver is a KNOWN-GOOD TB6612 (not the fried chip) [Q31]
- [ ] Motor wires white+red → driver A01/A02 (swap direction if FWD = backward) [Q30]
- [ ] Driver AIN1 ← Jetson pin 29 — **continuity check** (reverse-only symptom = this line) [Q29]
- [ ] Driver AIN2 ← Jetson pin 31, PWMA ← Jetson pin 32
- [ ] Driver VCC ← Jetson pin 17 (3.3V), STBY tied HIGH
- [ ] Driver VM ← UBEC-1 output set to **7.4–8.4V** (NOT 12V — 3S has no headroom) [Q33]
- [ ] Servo red ← UBEC-2 5V, servo black → common GND, signal → pin 33
- [ ] Encoder: blue→pin 1 (3.3V), black→pin 6, green→11, yellow→13
- [ ] **Common ground**: Jetson pin 6 = UBEC-1 GND = UBEC-2 GND = driver GND = servo GND
- [ ] No wire touches anything while power is on

## PHASE 1 — POWER ON + JETSON BOOT

- [ ] Jetson boots first (wall/USB power), wait for it to settle
- [ ] Battery 11.1V 3S connected LAST — check both UBEC LEDs on
- [ ] Verify `wlan0` exists: `ip link` (wedged twice on 2026-08-19) [Q32]
- [ ] `systemctl is-active mcqueen-edge` → `active`
- [ ] If WiFi radio missing → reboot Jetson; if it recurs, note it and use USB link

## PHASE 2 — DEPLOY FIXED EDGE CODE (laptop → Jetson over USB)

- [ ] `ssh sravjti@192.168.55.1` (USB gadget, key auth)
- [ ] scp the repo files (drive.py first — failsafe auto-recover fix) to the
      deployed clone dir on the Jetson (no deploy script yet — manual scp)
- [ ] `sudo systemctl restart mcqueen-edge`
- [ ] Verify in journal: service up, recorder idle, no exceptions

## PHASE 3 — SERVO + MOTOR SMOKE TEST (wheels OFF the ground)

- [ ] Servo: `python3 -c "import ..."` direct GPIO 50 Hz / 1500 us on pin 33 → servo centers
- [ ] Servo sweeps 1250/1500/1639 us without stutter [Q29]
- [ ] Motor FWD: direct GPIO AIN1=HIGH AIN2=LOW, PWMA 30% for 1 s → wheels FORWARD
- [ ] Motor REV: reverse pins, wheels backward [Q30]
- [ ] If FWD drives backward → swap A01/A02 wires, retest — DONE once FWD=forward
- [ ] Encoder: `gpio_encoder_source` debug / edge log shows `encoder_valid=True` with hand-spin

## PHASE 4 — KACHOW TELEOP (phone hotspot)

- [ ] Phone hotspot ON: SSID `Nothing`, 2.4 GHz (Jetson radio cannot see 5 GHz)
- [ ] KACHOW → IP `10.147.40.55`, port 5007 → connect
- [ ] App shows LIVE (status replies arriving), no FAILSAFE banner
- [ ] FAILSAFE behavior (optional but good): kill app → car stops within ~0.3 s →
      relaunch → auto-neutral clears gate → joystick works WITHOUT RESUME
- [ ] Drive a few meters forward + turn. Car must behave: FWD throttle = forward,
      steering left/right responsive

## PHASE 5 — RECORDING (20 laps target)

- [ ] **Rule: NEVER record while FAILSAFE** (frames get labeled 0/0 = garbage)
- [ ] Rule: STOP recording BEFORE any phone disconnect / app kill
- [ ] Start: phone browser → `http://10.147.40.55:8080/api/log/start`
- [ ] Record 5 laps → stop → start → record 5 laps → … (4 chunks of 5)
- [ ] Stop: browser → `http://10.147.40.55:8080/api/log/stop`
- [ ] Check spool: `ls -la data/spool` — frames growing, ~90 KB/frame, 3.2 GB/hour

## PHASE 6 — SHUTDOWN + PULL

- [ ] Stop recording (browser), verify spool final state
- [ ] Battery OFF first, then Jetson
- [ ] Jetson stays at corridor (HOME = laptop + phone ONLY)
- [ ] Back home: USB pull → `mcqueen_ml/dataset/validate_spool.py` →
      `tools/spool_to_sessions.py` → prepack → split → RTX training
      (booking per DECISION 034)

---

## TROUBLESHOOTING

| Symptom | Cause | Fix |
|---|---|---|
| Motor reverse-only | AIN1 line dead / A01-A02 swapped | continuity 29→AIN1; swap A01/A02 |
| Motor no motion at all | VM unpowered / UBEC too low | UBEC 7.4–8.4V on VM, common GND |
| Servo dead | no common GND / signal not pin 33 / UBEC-2 off | check 5V at connector, GND rail, pin 33 |
| FAILSAFE stuck | pre-fix drive.py | deploy 3t fix (neutral auto-clears) |
| wlan0 missing | radio wedge (recurring) | reboot; permanent fix = Q32 |
| Recorder garbage frames | recorded during FAILSAFE/disconnect | re-record; stop before disconnect |
| Encoder invalid | polarity/wiring | blue=3.3V, black=GND, green/yellow A/B on 11/13 |

## FILES

- Wiring: `docs/CAR_WIRING.md` · Bench history: `docs/ENCODER_BENCH.md`
- Edge app: `robot/jetson_nano/mcqueen_edge/` (drive.py, app.py, http_server.py)
- Pull/convert: `mcqueen_ml/dataset/validate_spool.py`, `tools/spool_to_sessions.py`