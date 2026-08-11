#!/usr/bin/env python3
"""Dependency-free McQueen held-out episode replay viewer.

The 4090 writes prediction JSONL with mcqueen_ml.training.evaluate_driver.
This laptop-side tool combines those predictions with the original raw episode
and serves a local browser UI at 10 FPS. It deliberately has no torch/LeRobot
requirement.
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import unquote, urlparse
import webbrowser


HTML = r'''<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>McQueen Prediction Replay</title>
<style>
:root{font-family:system-ui,-apple-system,Segoe UI,sans-serif;color-scheme:dark;background:#0b0d10;color:#e8edf2}
body{margin:0;padding:18px;background:#0b0d10}.wrap{max-width:1450px;margin:auto}.top{display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin-bottom:12px}.title{font-size:24px;font-weight:700}.pill{background:#171b20;border:1px solid #2a3139;border-radius:999px;padding:7px 11px;color:#bcc7d2}.grid{display:grid;grid-template-columns:minmax(0,2fr) minmax(320px,1fr);gap:14px}@media(max-width:950px){.grid{grid-template-columns:1fr}}.card{background:#11151a;border:1px solid #252c34;border-radius:14px;padding:12px;box-shadow:0 8px 30px #0005}.frame{width:100%;aspect-ratio:16/9;object-fit:contain;background:#050607;border-radius:10px}.stats{display:grid;grid-template-columns:1fr 1fr;gap:10px}.stat{background:#0d1014;border-radius:10px;padding:11px}.stat h3{font-size:13px;color:#97a5b3;margin:0 0 8px}.big{font-size:24px;font-variant-numeric:tabular-nums}.human{color:#73d0ff}.model{color:#9fe870}.err{color:#ffb86b}.bar{height:8px;background:#232a32;border-radius:8px;overflow:hidden;margin-top:8px}.fill{height:100%;background:currentColor;width:50%}.controls{display:flex;gap:8px;align-items:center;margin-top:10px;flex-wrap:wrap}button,select,input{background:#171c22;color:#e8edf2;border:1px solid #313a44;border-radius:8px;padding:8px 11px}input[type=range]{padding:0;flex:1;min-width:220px}.charts{margin-top:14px;display:grid;gap:12px}canvas{width:100%;height:180px;background:#0c0f13;border-radius:10px}.legend{font-size:12px;color:#9ca9b6;margin:4px 0 0}.legend b:first-child{color:#73d0ff}.legend b:last-child{color:#9fe870}.footer{color:#7f8b97;font-size:12px;margin-top:10px}
</style>
</head>
<body><div class="wrap">
<div class="top"><div class="title">McQueen — human vs model</div><div class="pill" id="episode"></div><div class="pill" id="clock"></div></div>
<div class="grid">
  <div class="card">
    <img id="frame" class="frame" alt="McQueen frame">
    <div class="controls">
      <button id="play">Pause</button>
      <button id="prev">◀</button><button id="next">▶</button>
      <select id="speed"><option value="0.25">0.25×</option><option value="0.5">0.5×</option><option value="1" selected>1× (10 FPS)</option><option value="2">2×</option></select>
      <input id="seek" type="range" min="0" max="0" value="0">
      <span id="idx"></span>
    </div>
  </div>
  <div class="card">
    <div class="stats">
      <div class="stat"><h3>Human steering</h3><div class="big human" id="hs"></div><div class="bar"><div class="fill human" id="hsb"></div></div></div>
      <div class="stat"><h3>Model steering</h3><div class="big model" id="ps"></div><div class="bar"><div class="fill model" id="psb"></div></div></div>
      <div class="stat"><h3>Human motor</h3><div class="big human" id="hm"></div><div class="bar"><div class="fill human" id="hmb"></div></div></div>
      <div class="stat"><h3>Model motor</h3><div class="big model" id="pm"></div><div class="bar"><div class="fill model" id="pmb"></div></div></div>
      <div class="stat"><h3>Steering error</h3><div class="big err" id="se"></div></div>
      <div class="stat"><h3>Motor error</h3><div class="big err" id="me"></div></div>
    </div>
  </div>
</div>
<div class="charts">
  <div class="card"><canvas id="steer"></canvas><div class="legend"><b>Human</b> vs <b>Model</b> steering across the whole episode</div></div>
  <div class="card"><canvas id="motor"></canvas><div class="legend"><b>Human</b> vs <b>Model</b> signed motor PWM across the whole episode</div></div>
</div>
<div class="footer">Offline replay only. Model predictions shown here never control McQueen.</div>
</div>
<script>
let data=[], i=0, playing=true, timer=null, speed=1;
const $=id=>document.getElementById(id);
function clamp(v,a,b){return Math.max(a,Math.min(b,v))}
function bar(el,v,min,max){el.style.width=(100*clamp((v-min)/(max-min),0,1))+"%"}
function lineChart(canvas,hkey,pkey,minY,maxY){
 const dpr=devicePixelRatio||1,w=canvas.clientWidth,h=canvas.clientHeight;canvas.width=w*dpr;canvas.height=h*dpr;const c=canvas.getContext('2d');c.scale(dpr,dpr);c.clearRect(0,0,w,h);
 c.strokeStyle='#27303a';c.lineWidth=1;for(let y=0;y<=4;y++){let yy=10+(h-20)*y/4;c.beginPath();c.moveTo(8,yy);c.lineTo(w-8,yy);c.stroke()}
 const draw=(key,color)=>{c.strokeStyle=color;c.lineWidth=2;c.beginPath();data.forEach((r,n)=>{let x=8+(w-16)*(data.length<=1?0:n/(data.length-1));let y=10+(h-20)*(1-clamp((r[key]-minY)/(maxY-minY),0,1));n?c.lineTo(x,y):c.moveTo(x,y)});c.stroke()};draw(hkey,'#73d0ff');draw(pkey,'#9fe870');
 let x=8+(w-16)*(data.length<=1?0:i/(data.length-1));c.strokeStyle='#ffb86b';c.lineWidth=1;c.beginPath();c.moveTo(x,6);c.lineTo(x,h-6);c.stroke();
}
function render(){if(!data.length)return;let r=data[i];$('frame').src=r.image_url;$('idx').textContent=`${i+1} / ${data.length}`;$('seek').value=i;$('clock').textContent=`t = ${(i/10).toFixed(1)} s`;
 $('hs').textContent=r.human_servo_angle_deg.toFixed(1)+'°';$('ps').textContent=r.pred_servo_angle_deg.toFixed(1)+'°';$('hm').textContent=r.human_motor_pwm.toFixed(1);$('pm').textContent=r.pred_motor_pwm.toFixed(1);$('se').textContent=(r.pred_servo_angle_deg-r.human_servo_angle_deg).toFixed(1)+'°';$('me').textContent=(r.pred_motor_pwm-r.human_motor_pwm).toFixed(1);
 bar($('hsb'),r.human_servo_angle_deg,45,115);bar($('psb'),r.pred_servo_angle_deg,45,115);bar($('hmb'),r.human_motor_pwm,-255,255);bar($('pmb'),r.pred_motor_pwm,-255,255);
 lineChart($('steer'),'human_servo_angle_deg','pred_servo_angle_deg',40,120);lineChart($('motor'),'human_motor_pwm','pred_motor_pwm',-255,255);
}
function schedule(){clearInterval(timer);if(playing)timer=setInterval(()=>{i=(i+1)%data.length;render()},100/(speed||1))}
$('play').onclick=()=>{playing=!playing;$('play').textContent=playing?'Pause':'Play';schedule()};$('prev').onclick=()=>{i=(i-1+data.length)%data.length;render()};$('next').onclick=()=>{i=(i+1)%data.length;render()};$('seek').oninput=e=>{i=+e.target.value;render()};$('speed').onchange=e=>{speed=+e.target.value;schedule()};
addEventListener('resize',render);
fetch('/api/data').then(r=>r.json()).then(x=>{data=x.frames;$('episode').textContent=x.episode;$('seek').max=Math.max(0,data.length-1);render();schedule()}).catch(e=>document.body.innerHTML='<pre>'+e+'</pre>');
</script></body></html>'''


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def raw_action(row: dict) -> tuple[float, float]:
    if "action.servo_angle" in row:
        return float(row["action.servo_angle"]), float(row["action.motor_pwm"])
    action = row.get("action")
    if isinstance(action, dict):
        servo = action.get("servo_angle", action.get("servo_angle_deg"))
        motor = action.get("motor_pwm")
        if servo is not None and motor is not None:
            return float(servo), float(motor)
    raise KeyError("Could not find servo/motor action fields in frames.jsonl")


def image_path(row: dict) -> str:
    value = row.get("observation.images.front_rgb")
    if value is None:
        observation = row.get("observation", {})
        value = observation.get("images", {}).get("front_rgb") if isinstance(observation, dict) else None
    if not value:
        raise KeyError("Could not find observation.images.front_rgb in frames.jsonl")
    return str(value)


def combine(episode: Path, predictions: Path, episode_index: int | None) -> list[dict]:
    raw = load_jsonl(episode / "frames.jsonl")
    pred = load_jsonl(predictions)
    if episode_index is not None:
        pred = [r for r in pred if int(r.get("episode_index", -1)) == episode_index]
    if not pred:
        raise ValueError("No prediction rows matched this episode")

    by_position = {
        int(r["episode_frame_index"]): r
        for r in pred
        if "episode_frame_index" in r
    }
    if by_position and len(by_position) != len(pred):
        raise ValueError("Some prediction rows have episode_frame_index and some do not")

    frames = []
    for pos, raw_row in enumerate(raw):
        p = by_position.get(pos) if by_position else (pred[pos] if pos < len(pred) else None)
        if p is None:
            continue
        hs, hm = raw_action(raw_row)
        # Evaluation output is the source of truth for human action when present.
        hs = float(p.get("human_servo_angle_deg", hs))
        hm = float(p.get("human_motor_pwm", hm))
        rel = image_path(raw_row)
        frames.append({
            "episode_frame_index": pos,
            "image_url": "/frame/" + str(pos),
            "image_rel": rel,
            "human_servo_angle_deg": hs,
            "human_motor_pwm": hm,
            "pred_servo_angle_deg": float(p["pred_servo_angle_deg"]),
            "pred_motor_pwm": float(p["pred_motor_pwm"]),
        })
    if not frames:
        raise ValueError("No frames could be combined")
    return frames


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode", type=Path, required=True, help="raw episode_XXXXXX directory")
    parser.add_argument("--predictions", type=Path, required=True, help="evaluate_driver JSONL")
    parser.add_argument("--episode-index", type=int, default=None, help="filter combined prediction JSONL")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    episode = args.episode.resolve()
    frames = combine(episode, args.predictions.resolve(), args.episode_index)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *values):
            return

        def send_bytes(self, body: bytes, content_type: str, status: int = 200):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            route = urlparse(self.path).path
            if route == "/":
                return self.send_bytes(HTML.encode(), "text/html; charset=utf-8")
            if route == "/api/data":
                payload = json.dumps({"episode": episode.name, "frames": frames}).encode()
                return self.send_bytes(payload, "application/json")
            if route.startswith("/frame/"):
                try:
                    pos = int(unquote(route.split("/")[-1]))
                    rel = Path(frames[pos]["image_rel"])
                    # Raw rows may store rgb/foo.jpg or just filename.
                    candidates = [episode / rel, episode / "rgb" / rel.name]
                    image = next((p for p in candidates if p.is_file()), None)
                    if image is None:
                        raise FileNotFoundError(rel)
                    return self.send_bytes(image.read_bytes(), "image/jpeg")
                except Exception as exc:
                    return self.send_bytes(str(exc).encode(), "text/plain", 404)
            return self.send_bytes(b"not found", "text/plain", 404)

    url = f"http://{args.host}:{args.port}/"
    print(f"Episode      : {episode}")
    print(f"Frames       : {len(frames)}")
    print(f"Replay viewer: {url}")
    if not args.no_browser:
        webbrowser.open(url)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nReplay viewer stopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
