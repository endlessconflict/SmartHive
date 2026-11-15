"""A small apiary of simulated nodes for the live demo.

Every node runs the real Raspberry Pi node code (`pi_node`): the outbox, the MQTT uplink with mutual TLS, the
device-token request, the retention filter, threat events and the image upload. Only the hardware is replaced:

* sensors  -> temperature, humidity and weight generated around values the presenter can shift,
* camera   -> frames from `corpus/` (photographs from the BeeAlarmed BeeDataset, see build_corpus.py),
* vision   -> the project's detector (YOLO11n v2, Pest_Threats_Detection) run on every frame: no detection is
              written by hand.

The presenter changes a node's situation with `demo-ctl` or the control panel (port 8090); both write
`/control/state.json`, which this process reads every two seconds.
"""

import json
import logging
import os
import random
import threading
import time
import uuid
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np
from detector import PestDetector

from pi_node import main as node
from pi_node import payload
from pi_node.dht11 import Measurement
from pi_node.hx711 import Weight
from pi_node.outbox import Outbox
from pi_node.retention import RetentionRule

log = logging.getLogger("sim")
CONTROL = Path(os.environ.get("CONTROL_DIR", "/control")) / "state.json"
DATA = Path(os.environ.get("DATA_DIR", "/data"))
PKI = Path(os.environ.get("PKI_DIR", "/pki"))
CORPUS = Path(os.environ.get("CORPUS_DIR", "/corpus"))
MODEL = Path(os.environ.get("MODEL", "/app/model/yolo11n_v2.onnx"))
API = os.environ.get("API_URL", "http://caddy")
BROKER = os.environ.get("MQTT_HOST", "mosquitto")
SAMPLE_S = float(os.environ.get("SAMPLE_S", "10"))
WEIGHT_S = float(os.environ.get("WEIGHT_S", "30"))
FRAME_S = float(os.environ.get("FRAME_S", "5"))
MITE_CONF = 0.60  # the node counts a Varroa box only at or above this, the same threshold its filter uses
SUMMARY_S = float(os.environ.get("SUMMARY_S", "60"))  # ten minutes on a real node; the demo cannot wait
# node -> (baseline weight in kg, weight change in kg per hour while nothing else is set)
FLEET = {
    "sim-0001": (41.0, 0.12),
    "sim-0002": (38.5, 0.05),
    "sim-0003": (44.2, 0.08),
    "sim-0004": (36.8, 0.03),
    "sim-0005": (39.9, 0.10),
}
# what the camera shows while a scenario runs: scene folder, and the share of frames that show it
MODES = {"hornet": ("hornet", 0.75), "varroa": ("varroa", 0.80)}


# the hive of the anomaly in the history: its humidity stays low until the presenter resets the node
STARTS_DRY = "sim-0003"


def default_state() -> dict:
    return {
        n: {"mode": "normal", "until": None, "temp": 0.0, "rh": -14.0 if n == STARTS_DRY else 0.0, "power": True,
            "weight_rate": None}
        for n in FLEET
    }


def load_state() -> dict:
    try:
        raw = json.loads(CONTROL.read_text())
    except (OSError, ValueError):
        raw = {}
    state = default_state()
    for n, s in raw.items():
        if n in state:
            state[n].update(s)
    now = time.time()
    for n, s in state.items():  # a scenario ends by itself, and the node goes back to how it started
        if s["until"] and s["until"] < now:
            s.update(default_state()[n])
    return state


class Shared:
    """The state file, read at most once a second by every node thread."""

    def __init__(self) -> None:
        self.state = load_state()
        self.read_at = 0.0
        self.lock = threading.Lock()

    def get(self, node_id: str) -> dict:
        with self.lock:
            if time.monotonic() - self.read_at > 1:
                self.state, self.read_at = load_state(), time.monotonic()
            return self.state[node_id]


class Sensors:
    def __init__(self, node_id: str, shared: Shared, kg: float) -> None:
        self.id, self.shared, self.kg = node_id, shared, kg
        self.rng = random.Random()
        self.started = time.monotonic()
        self.last = self.started

    def temp_rh(self) -> Measurement:
        s = self.shared.get(self.id)
        return Measurement(round(self.rng.gauss(35 + s["temp"], 0.35), 1), round(self.rng.gauss(58 + s["rh"], 1.5), 1))

    def weight(self) -> Weight:
        s = self.shared.get(self.id)
        rate = s["weight_rate"] if s["weight_rate"] is not None else FLEET[self.id][1]
        now = time.monotonic()
        self.kg += rate * (now - self.last) / 3600
        self.last = now
        return Weight(self.rng.gauss(self.kg, 0.02), "ok")


class Dht11Sim:
    def __init__(self, s: Sensors) -> None:
        self.s = s

    def read(self) -> Measurement:
        return self.s.temp_rh()


class ScaleSim:
    def __init__(self, s: Sensors) -> None:
        self.s = s

    def read(self) -> Weight:
        return self.s.weight()


class Camera:
    """Picks a corpus frame for the scenario, runs the real detector on it, leaves it as visiond would."""

    def __init__(self, node_id: str, shared: Shared, detector: PestDetector, lock: threading.Lock, frames_dir: Path) -> None:
        self.id, self.shared, self.det, self.lock, self.dir = node_id, shared, detector, lock, frames_dir
        self.rng = random.Random()
        self.boot_id = str(uuid.uuid4())
        self.pool = {d.name: sorted(d.glob("*.jpg")) for d in CORPUS.iterdir() if d.is_dir()}
        frames_dir.mkdir(parents=True, exist_ok=True)
        self.acc = {"frames": 0, "counts": {}, "classified": 0, "positive": 0}
        self.acc_lock = threading.Lock()
        self.window_start = datetime.now(UTC)

    def take_summary(self) -> bytes:
        """The vision summary of the window since the last call (docs/05-backend/04-messaging-contract.md)."""
        with self.acc_lock:
            acc, self.acc = self.acc, {"frames": 0, "counts": {}, "classified": 0, "positive": 0}
        start, self.window_start = self.window_start, datetime.now(UTC)
        doc = {
            "schema": "smarthive.summary/1.0", "msg_id": payload.uuid7(), "node_id": self.id, "boot_id": self.boot_id,
            "sent_at": payload.iso(self.window_start),
            "window": {"start": payload.iso(start), "end": payload.iso(self.window_start), "clock_synced": True},
            "frames_analyzed": acc["frames"], "counts": acc["counts"],
            "varroa": {"bees_classified": acc["classified"], "positive": acc["positive"]},
        }
        return json.dumps(doc, separators=(",", ":")).encode()

    def folder(self) -> str:
        mode = self.shared.get(self.id)["mode"]
        if mode in MODES:
            name, share = MODES[mode]
            if self.rng.random() < share:
                return name
        return "calm"

    def shoot(self) -> str:
        kind = self.folder()
        path = self.rng.choice(self.pool[kind])
        data = path.read_bytes()
        frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        with self.lock:  # one detector for the whole fleet
            found = self.det(frame)
        # the detector's `wasp` class (wasps and hornets) is the contract's `hornet` threat
        objects = [{"cls": "hornet" if o["cls"] == "wasp" else o["cls"], "conf": o["conf"], "box": o["box"]} for o in found]
        bees = sum(o["cls"] == "bee" for o in objects)
        mites = sum(o["cls"] == "varroa" and o["conf"] >= MITE_CONF for o in objects)  # as the node reports them
        with self.acc_lock:
            self.acc["frames"] += 1
            for o in objects:
                self.acc["counts"][o["cls"]] = self.acc["counts"].get(o["cls"], 0) + 1
            # the Varroa index of a window is mites found per bee seen; a mite is never counted without a bee
            self.acc["classified"] += max(bees, mites)
            self.acc["positive"] += mites
        frame_id = payload.uuid7()
        (self.dir / f"{frame_id}.jpg").write_bytes(data)
        info = {"captured_at": payload.iso(datetime.now(UTC)), "clock_synced": True, "width": frame.shape[1],
                "height": frame.shape[0], "objects": objects}
        tmp = self.dir / f"{frame_id}.json.tmp"
        tmp.write_text(json.dumps(info))
        os.replace(tmp, self.dir / f"{frame_id}.json")
        return kind


class SimNode:
    """One node: the real `node.run` in a thread, stopped and started again to cut and restore its power."""

    def __init__(self, node_id: str, shared: Shared, detector: PestDetector, lock: threading.Lock) -> None:
        self.id, self.shared = node_id, shared
        base = DATA / node_id
        base.mkdir(parents=True, exist_ok=True)
        self.outbox_path = base / "outbox.db"
        self.frames = base / "frames"  # tmpfs on a real node: wiped at every start
        for old in self.frames.glob("*") if self.frames.exists() else []:
            old.unlink(missing_ok=True)
        self.cfg = node.Config(
            node_id, SAMPLE_S, BROKER, 8883, True, str(PKI / "ca.crt"), str(PKI / f"{node_id}.crt"),
            str(PKI / f"{node_id}.key"), node.ScaleConfig(0, 0, 0, 1.0, WEIGHT_S, ""), self.outbox_path,
            images=node.ImagesConfig(
                api_url=API, device_token_file=base / "token.txt", frames_dir=self.frames,
                image_dir=base / "images",
                rule=RetentionRule(sample_rate=0.12, periodic_every_s=20 * 60), raise_events=True,
            ),
        )
        self.sensors = Sensors(node_id, shared, FLEET[node_id][0])
        self.camera = Camera(node_id, shared, detector, lock, self.frames)
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None

    def powered(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def power_on(self) -> None:
        self.stop = threading.Event()

        def run() -> None:
            outbox = Outbox(self.outbox_path)  # sqlite connections stay in the thread that made them
            try:
                node.run(self.cfg, Dht11Sim(self.sensors), ScaleSim(self.sensors), outbox, self.stop)
            finally:
                outbox.close()

        self.thread = threading.Thread(target=run, name=self.id, daemon=True)
        self.thread.start()
        log.info("%s powered on", self.id)

    def power_off(self) -> None:
        self.stop.set()  # a clean stop publishes "offline" before the thread ends
        if self.thread:
            self.thread.join(timeout=15)
        log.info("%s powered off", self.id)

    def loop(self) -> None:
        last_shot = last_summary = 0.0
        outbox = None  # the loop thread's own connection: sqlite objects stay in the thread that made them
        while True:
            want = self.shared.get(self.id)["power"]
            if want and not self.powered():
                self.power_on()
            elif not want and self.powered():
                self.power_off()
            if self.powered() and time.monotonic() - last_shot >= FRAME_S:
                last_shot = time.monotonic()
                try:
                    self.camera.shoot()
                except Exception:  # a bad frame must not stop the node
                    log.exception("%s: frame failed", self.id)
            if self.powered() and time.monotonic() - last_summary >= SUMMARY_S:
                last_summary = time.monotonic()
                outbox = outbox or Outbox(self.outbox_path)
                outbox.add(payload.topic(self.id, "summary"), self.camera.take_summary(), datetime.now(UTC), True)
            time.sleep(0.5)


PANEL = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>SmartHive demo control</title>
<style>
:root{color-scheme:light dark;--bg:#fffaf0;--fg:#2b2113;--card:#fff;--line:#e6d9bf;--acc:#c47f00;--bad:#b3261e}
@media(prefers-color-scheme:dark){:root{--bg:#17130c;--fg:#f3e9d2;--card:#221c11;--line:#3a3020;--acc:#f2b13a;--bad:#ff8a80}}
body{font:16px/1.4 system-ui,sans-serif;margin:0;padding:16px;background:var(--bg);color:var(--fg)}
h1{font-size:20px;margin:0 0 4px}p{margin:0 0 16px;opacity:.75}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.card h2{font-size:16px;margin:0 0 2px}.st{font-size:13px;opacity:.75;margin-bottom:10px;min-height:18px}
button{font:inherit;margin:3px 3px 3px 0;padding:8px 10px;border-radius:8px;border:1px solid var(--line);background:transparent;color:inherit;cursor:pointer}
button:hover{border-color:var(--acc)}button.bad{color:var(--bad)}
</style>
<h1>SmartHive demo control</h1><p>Each button changes what one simulated node does. Scenarios end by themselves after 3 minutes.</p>
<div class=grid id=g></div>
<script>
const names={};
async function act(n,a){await fetch('/act',{method:'POST',body:JSON.stringify({node:n,action:a})});load()}
async function load(){
 const s=await (await fetch('/state')).json();
 g.innerHTML=Object.entries(s).map(([n,v])=>`<div class=card><h2>${n}</h2>
 <div class=st>${v.power?'':'power off · '}${v.mode!=='normal'?v.mode+' scenario · ':''}${v.temp?'temp '+(v.temp>0?'+':'')+v.temp+' °C · ':''}${v.power&&v.mode==='normal'&&!v.temp?'normal':''}</div>
 <button onclick="act('${n}','hornet')">Hornet attack</button>
 <button onclick="act('${n}','varroa')">Varroa outbreak</button><button onclick="act('${n}','heat')">Overheating</button>
 <button onclick="act('${n}','swarm')">Honey flow</button><button class=bad onclick="act('${n}','${v.power?'off':'on'}')">${v.power?'Cut power':'Restore power'}</button>
 <button onclick="act('${n}','reset')">Reset</button></div>`).join('')}
load();setInterval(load,3000)
</script>"""


def apply(state: dict, node_id: str, action: str) -> None:
    s = state[node_id]
    until = time.time() + 180
    if action in MODES:
        s.update(mode=action, until=until)
    elif action == "heat":
        s.update(temp=5.5, rh=-12.0, until=time.time() + 300)
    elif action == "swarm":
        s.update(weight_rate=8.0, until=until)
    elif action == "off":
        s["power"] = False
    elif action == "on":
        s["power"] = True
    elif action == "reset":
        state[node_id] = default_state()[node_id]
    else:
        raise ValueError(action)


def update(node_id: str, action: str) -> None:
    """Shared by the panel and demo-ctl: read, change one node, write back atomically."""
    state = load_state()
    apply(state, node_id, action)
    CONTROL.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONTROL.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    os.replace(tmp, CONTROL)


class Panel(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        pass

    def reply(self, body: bytes, kind: str) -> None:
        self.send_response(200)
        self.send_header("content-type", kind)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/state":
            self.reply(json.dumps(load_state()).encode(), "application/json")
        else:
            self.reply(PANEL.encode(), "text/html; charset=utf-8")

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
        try:
            update(body["node"], body["action"])
        except (KeyError, ValueError):
            self.send_error(400)
            return
        self.reply(b"{}", "application/json")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    node.clock_synced = lambda: True  # the container shares the host clock; there is no timedatectl in it
    threading.Thread(target=ThreadingHTTPServer(("0.0.0.0", 8090), Panel).serve_forever, daemon=True).start()
    detector = PestDetector(MODEL)
    lock = threading.Lock()
    shared = Shared()
    nodes = [SimNode(n, shared, detector, lock) for n in FLEET]
    threads = [threading.Thread(target=n.loop, name=f"loop-{n.id}", daemon=True) for n in nodes]
    for t in threads:
        t.start()
        time.sleep(1.5)  # stagger the MQTT connects
    log.info("fleet running: %s", ", ".join(FLEET))
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
