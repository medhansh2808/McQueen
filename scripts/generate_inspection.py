#!/usr/bin/env python3
import html
import json
import sys
from pathlib import Path

def timestamp(row):
    for key in ("timestamp_s", "timestamp", "source_timestamp_s", "source_timestamp"):
        if key in row:
            return float(row[key])
    raise KeyError("No timestamp field found")

def make_viewer(ep: Path):
    rows = [
        json.loads(line)
        for line in (ep / "frames.jsonl").read_text().splitlines()
        if line.strip()
    ]
    if not rows:
        raise RuntimeError("No frames found")

    required = {
        "observation.images.front_rgb",
        "action.servo_angle",
        "action.motor_pwm",
    }
    for i, row in enumerate(rows):
        missing = required - row.keys()
        if missing:
            raise RuntimeError(f"frame {i} missing {sorted(missing)}")

    times = [timestamp(r) for r in rows]
    servo = [int(r["action.servo_angle"]) for r in rows]
    pwm = [int(r["action.motor_pwm"]) for r in rows]
    duration = times[-1] - times[0] if len(times) > 1 else 0.0
    fps = (len(rows) - 1) / duration if duration > 0 else 0.0
    playback_ms = round(1000 / fps) if fps > 0 else 100

    rows_json = json.dumps(rows, separators=(",", ":")).replace("</", "<\\/")
    name = html.escape(ep.name)

    page = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>McQueen — {name}</title>
<style>
body{{font-family:sans-serif;max-width:1100px;margin:20px auto;background:#111;color:#eee}}
img{{width:100%;max-height:680px;object-fit:contain;background:#000}}
.controls{{display:flex;gap:10px;align-items:center;margin:14px 0}}
button{{padding:9px 16px;font-size:16px}}
input[type=range]{{flex:1}}
.data{{font-size:20px;line-height:1.7}}
.summary{{background:#222;padding:12px;line-height:1.6}}
</style>
</head>
<body>
<h1>McQueen RGB Dataset Inspector</h1>
<div class="summary">
Episode: <strong>{name}</strong><br>
Frames: <strong>{len(rows)}</strong><br>
Duration: <strong>{duration:.2f} seconds</strong><br>
Rate: <strong>{fps:.2f} FPS</strong><br>
Servo range: <strong>{min(servo)} to {max(servo)}</strong><br>
Motor PWM range: <strong>{min(pwm)} to {max(pwm)}</strong><br>
Non-zero PWM frames: <strong>{sum(v != 0 for v in pwm)} / {len(pwm)}</strong>
</div>
<img id="frame">
<div class="controls">
<button onclick="move(-1)">Previous</button>
<input id="slider" type="range" min="0" max="{len(rows)-1}" value="0">
<button onclick="move(1)">Next</button>
<button id="play" onclick="toggle()">Play</button>
</div>
<div class="data">
Frame: <strong id="num"></strong><br>
Timestamp: <strong id="ts"></strong><br>
Servo angle sent: <strong id="servo"></strong>°<br>
Motor PWM sent: <strong id="pwm"></strong><br>
Normalized steering: <strong id="steer"></strong><br>
Normalized throttle: <strong id="throttle"></strong>
</div>
<script>
const rows={rows_json};
let i=0,timer=null;
const img=document.getElementById("frame");
const slider=document.getElementById("slider");
const play=document.getElementById("play");
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
function ts(r){{return r.timestamp_s??r.timestamp??r.source_timestamp_s??r.source_timestamp??"unknown"}}
function show(n){{
  i=clamp(n,0,rows.length-1);
  const r=rows[i], s=Number(r["action.servo_angle"]), p=Number(r["action.motor_pwm"]);
  img.src=r["observation.images.front_rgb"];
  slider.value=i;
  document.getElementById("num").textContent=(i+1)+" / "+rows.length;
  document.getElementById("ts").textContent=ts(r);
  document.getElementById("servo").textContent=s;
  document.getElementById("pwm").textContent=p;
  document.getElementById("steer").textContent=clamp((s-80)/35,-1,1).toFixed(3);
  document.getElementById("throttle").textContent=clamp(p/255,-1,1).toFixed(3);
}}
function move(n){{show(i+n)}}
function toggle(){{
  if(timer){{clearInterval(timer);timer=null;play.textContent="Play";return}}
  play.textContent="Pause";
  timer=setInterval(()=>{{
    if(i>=rows.length-1){{clearInterval(timer);timer=null;play.textContent="Play"}}
    else show(i+1);
  }},{playback_ms});
}}
slider.oninput=e=>show(Number(e.target.value));
document.onkeydown=e=>{{
  if(e.key==="ArrowLeft")move(-1);
  if(e.key==="ArrowRight")move(1);
  if(e.code==="Space"){{e.preventDefault();toggle()}}
}};
show(0);
</script>
</body>
</html>"""

    out = ep / "inspection.html"
    out.write_text(page)
    print(f"CREATED: {out}")

def main():
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "~/McQueenData/spool").expanduser()
    episodes = [target] if (target / "frames.jsonl").is_file() else sorted(target.glob("episode_*"))
    made = 0
    for ep in episodes:
        if not (ep / "frames.jsonl").is_file() or not (ep / "rgb").is_dir():
            continue
        try:
            make_viewer(ep)
            made += 1
        except Exception as exc:
            print(f"SKIPPED: {ep} — {exc}")
    if made == 0:
        raise SystemExit("ERROR: no valid episodes found")
    print(f"Inspection files created: {made}")

if __name__ == "__main__":
    main()
