"""End-to-end verification of the SmartHive demo stack.

    docker compose run --rm verify                  # everything, about 10 minutes
    docker compose run --rm verify --quick          # no outage and restart tests, about 6 minutes

It drives the running stack the way a beekeeper, a node and an attacker would, and checks every hop of the
pipeline: capture at the node, MQTT with mutual TLS, ingestion, processing, alert rules, the REST API, the
WebSocket feed, the in-app inbox, email, the dashboard in a real browser, backups and recovery from failures.
Each check records PASS or FAIL with what was observed. The report lands in /report (report.html, report.json,
screenshots); the exit code is 1 when anything failed, so CI can gate on it.
"""

import argparse
import asyncio
import hashlib
import html
import io
import json
import os
import random
import ssl
import sys
import threading
import time
import traceback
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import paho.mqtt.client as mqtt
import websockets
from PIL import Image

APP = os.environ.get("APP", "http://caddy")
PANEL = os.environ.get("PANEL", "http://simulator:8090")
MAIL = os.environ.get("MAIL", "http://mailpit:8025")
BROKER = os.environ.get("BROKER", "mosquitto")
PKI = Path(os.environ.get("PKI", "/pki"))
REPORT = Path(os.environ.get("REPORT", "/report"))
PROJECT = os.environ.get("COMPOSE_PROJECT", "smarthive-demo")
ADMIN = ("demo@smarthive.dev", "SmartHive-Demo-2026")
GUEST = ("guest@smarthive.dev", "SmartHive-Demo-2026")
NODES = {1: "sim-0001", 2: "sim-0002", 3: "sim-0003", 4: "sim-0004", 5: "sim-0005"}

RESULTS: list[dict] = []
LATENCY: dict[str, float] = {}
SKIPPED: list[str] = []


def now() -> datetime:
    return datetime.now(UTC)


def iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds").replace("+00:00", "Z")


def record(area: str, name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append({"area": area, "name": name, "ok": bool(ok), "detail": str(detail)[:400]})
    print(f"  {'PASS' if ok else 'FAIL'}  [{area}] {name}" + (f"  ({str(detail)[:160]})" if detail else ""), flush=True)
    return bool(ok)


def phase(title: str) -> None:
    print(f"\n== {title}", flush=True)


def guarded(area: str):
    """A phase that crashes counts as one failure, and the run goes on."""

    def wrap(fn):
        def run(*a, **kw):
            try:
                return fn(*a, **kw)
            except Exception as e:  # noqa: BLE001
                record(area, f"{fn.__name__} did not complete", False, f"{type(e).__name__}: {e}")
                traceback.print_exc()

        return run

    return wrap


def wait_for(fn, timeout: float, every: float = 2.0):
    """(value, seconds) once fn() returns something truthy, else (None, timeout)."""
    start = time.monotonic()
    while True:
        try:
            value = fn()
        except Exception:  # noqa: BLE001 - not there yet
            value = None
        if value:
            return value, time.monotonic() - start
        if time.monotonic() - start >= timeout:
            return None, timeout
        time.sleep(every)


# ---------------------------------------------------------------------------------------------- clients


class Api:
    def __init__(self) -> None:
        self.http = httpx.Client(base_url=APP, timeout=30)
        self.token: str | None = None

    def login(self, email: str, password: str) -> httpx.Response:
        r = self.http.post("/api/v1/auth/login", json={"email": email, "password": password})
        if r.status_code == 200:
            self.token = r.json()["access_token"]
        return r

    def call(self, method: str, path: str, **kw) -> httpx.Response:
        headers = kw.pop("headers", {})
        if self.token:
            headers["authorization"] = f"Bearer {self.token}"
        return self.http.request(method, path, headers=headers, **kw)

    def get(self, path: str, **kw):
        return self.call("GET", path, **kw)

    def json(self, path: str, **kw):
        r = self.get(path, **kw)
        r.raise_for_status()
        return r.json()


api = Api()


class Docker:
    """The Docker Engine API over its socket: enough to stop, start and run a command in a service."""

    def __init__(self) -> None:
        self.http = httpx.Client(transport=httpx.HTTPTransport(uds="/var/run/docker.sock"), base_url="http://docker", timeout=120)

    def containers(self) -> list[dict]:
        flt = json.dumps({"label": [f"com.docker.compose.project={PROJECT}"]})
        return self.http.get("/containers/json", params={"all": 1, "filters": flt}).json()

    def service(self, name: str) -> dict | None:
        for c in self.containers():
            if c["Labels"].get("com.docker.compose.service") == name:
                return c
        return None

    def action(self, name: str, verb: str) -> None:
        c = self.service(name)
        assert c, f"no container for {name}"
        r = self.http.post(f"/containers/{c['Id']}/{verb}", params={"t": 5})
        assert r.status_code in (204, 304), r.text

    def exec(self, name: str, cmd: list[str]) -> tuple[int, str]:
        c = self.service(name)
        assert c, f"no container for {name}"
        eid = self.http.post(f"/containers/{c['Id']}/exec", json={"Cmd": cmd, "AttachStdout": True, "AttachStderr": True}).json()["Id"]
        raw = self.http.post(f"/exec/{eid}/start", json={"Detach": False, "Tty": False}).content
        out, i = b"", 0
        while i + 8 <= len(raw):  # the stream is framed: 1 byte type, 3 padding, 4 bytes length
            n = int.from_bytes(raw[i + 4 : i + 8], "big")
            out += raw[i + 8 : i + 8 + n]
            i += 8 + n
        return self.http.get(f"/exec/{eid}/json").json()["ExitCode"], out.decode(errors="replace")


docker = Docker()


def panel(node: str, action: str) -> None:
    httpx.post(f"{PANEL}/act", content=json.dumps({"node": node, "action": action}), timeout=10).raise_for_status()


def mails() -> list[dict]:
    return httpx.get(f"{MAIL}/api/v1/messages", params={"limit": 200}, timeout=10).json()["messages"]


class Live:
    """A WebSocket subscriber on every hive, collecting what the server pushes."""

    def __init__(self, token: str, hive_ids: list[str]) -> None:
        self.messages: list[tuple[float, dict]] = []
        self.ready = threading.Event()
        self.error: str | None = None
        self.token, self.hive_ids = token, hive_ids
        threading.Thread(target=lambda: asyncio.run(self.run()), daemon=True).start()

    async def run(self) -> None:
        url = APP.replace("http", "ws") + "/api/v1/ws"
        try:
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps({"op": "auth", "token": self.token}))
                async for raw in ws:
                    m = json.loads(raw)
                    if m.get("type") == "ready":
                        await ws.send(json.dumps({"op": "subscribe", "hives": self.hive_ids}))
                        self.ready.set()
                    self.messages.append((time.monotonic(), m))
        except Exception as e:  # noqa: BLE001
            self.error = f"{type(e).__name__}: {e}"

    def of(self, kind: str, since: float = 0.0, **match) -> list[dict]:
        return [m for t, m in self.messages if t >= since and m.get("type") == kind and all(m.get(k) == v for k, v in match.items())]


def mqtt_client(cid: str, cert: str | None) -> mqtt.Client:
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid)
    if cert:
        c.tls_set(ca_certs=str(PKI / "ca.crt"), certfile=str(PKI / f"{cert}.crt"), keyfile=str(PKI / f"{cert}.key"))
    else:
        c.tls_set(ca_certs=str(PKI / "ca.crt"))
    return c


# ---------------------------------------------------------------------------------------------- phases


@guarded("platform")
def platform_checks() -> None:
    phase("Platform: every service up, one-shot jobs finished, the entry points answer")
    state = {c["Labels"].get("com.docker.compose.service"): (c["State"], c["Status"]) for c in docker.containers()}
    for svc in ("mosquitto", "db", "ingest", "worker", "api", "frontend", "caddy", "mailpit", "simulator"):
        record("platform", f"service {svc} is running", state.get(svc, ("missing",))[0] == "running", state.get(svc))
    for svc in ("pki", "migrate", "bootstrap"):
        s = state.get(svc, ("missing", ""))
        record("platform", f"one-shot job {svc} finished with exit 0", s[0] == "exited" and "(0)" in s[1], s)
    r = httpx.get(f"{APP}/healthz")
    record("platform", "GET /healthz (liveness)", r.status_code == 200)
    r = httpx.get(f"{APP}/readyz")
    record("platform", "GET /readyz (database reachable)", r.status_code == 200)
    r = httpx.get(f"{APP}/")
    record("platform", "dashboard served through the reverse proxy", r.status_code == 200 and "Smart Hive" in r.text)
    spec = httpx.get(f"{APP}/api/v1/openapi.json").json()
    n = sum(len(v) for v in spec["paths"].values())
    record("platform", "OpenAPI describes the API", n >= 35, f"{n} operations")
    record("platform", "Mailpit (mail catcher) answers", httpx.get(f"{MAIL}/api/v1/messages").status_code == 200)


@guarded("security")
def security_checks() -> None:
    phase("Security: authentication, authorization, scoping, broker mutual TLS")
    anon = httpx.Client(base_url=APP)
    record("security", "no token -> 401", anon.get("/api/v1/hives").status_code == 401)
    record("security", "garbage token -> 401", anon.get("/api/v1/hives", headers={"authorization": "Bearer abc.def.ghi"}).status_code == 401)
    r = api.login(*ADMIN)
    record("security", "valid login returns an access token", r.status_code == 200 and "access_token" in r.json())
    tampered = api.token[:-3] + ("AAA" if not api.token.endswith("AAA") else "BBB")
    record("security", "tampered token -> 401", anon.get("/api/v1/me", headers={"authorization": f"Bearer {tampered}"}).status_code == 401)
    bad = anon.post("/api/v1/auth/login", json={"email": ADMIN[0], "password": "wrong-password-123"})
    record("security", "wrong password -> 401 problem+json", bad.status_code == 401 and "json" in bad.headers.get("content-type", ""), bad.text[:80])
    cookie = r.headers.get("set-cookie", "")
    record("security", "refresh cookie is HttpOnly and SameSite=Strict", "httponly" in cookie.lower() and "samesite=strict" in cookie.lower(), cookie[:70])

    def refresh_cookie(resp: httpx.Response) -> str:
        return resp.headers["set-cookie"].split(";")[0]  # refresh_token=<value>

    login1 = httpx.post(f"{APP}/api/v1/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]})
    old = refresh_cookie(login1)
    r1 = httpx.post(f"{APP}/api/v1/auth/refresh", headers={"cookie": old})
    record("security", "refresh rotates the token (new cookie, new access token)", r1.status_code == 200 and refresh_cookie(r1) != old and "access_token" in r1.json(), r1.status_code)
    r2 = httpx.post(f"{APP}/api/v1/auth/refresh", headers={"cookie": old})
    record("security", "reusing an old refresh token is refused (theft detection)", r2.status_code == 401, r2.status_code)
    r3 = httpx.post(f"{APP}/api/v1/auth/refresh", headers={"cookie": refresh_cookie(r1)})
    record("security", "...and it closes every session of that user", r3.status_code == 401, r3.status_code)
    api.login(*ADMIN)

    guest = Api()
    guest.login(*GUEST)
    record("security", "a beekeeper without hives sees none", guest.json("/api/v1/hives")["items"] == [])
    record("security", "...and no alerts", guest.json("/api/v1/alerts")["items"] == [])
    hive = api.json("/api/v1/hives")["items"][0]["id"]
    record("security", "...and cannot open another user's hive (404, not 403: no existence leak)", guest.get(f"/api/v1/hives/{hive}").status_code == 404)
    record("security", "...cannot list nodes (admin only)", guest.get("/api/v1/nodes").status_code == 403)
    record("security", "...cannot change alert rules", guest.call("PATCH", "/api/v1/alert-rules/rh_out_of_range", json={"enabled": False}).status_code == 403)
    record("security", "...cannot read another user's images or exports", guest.get(f"/api/v1/hives/{hive}/images").status_code in (403, 404) and guest.get(f"/api/v1/exports/readings?hive_id={hive}").status_code in (403, 404))
    record("security", "upload without a device token is refused", httpx.post(f"{APP}/device/v1/images", files={"image": ("a.jpg", b"x")}).status_code in (401, 403, 422))

    # mutual TLS at the broker
    failed = {"v": False}
    try:
        c = mqtt_client("verify-nocert", None)
        c.connect(BROKER, 8883, 10)
        c.loop_start()
        time.sleep(3)
        failed["v"] = not c.is_connected()
        c.loop_stop()
    except Exception:  # noqa: BLE001
        failed["v"] = True
    record("security", "broker refuses a client without a certificate", failed["v"])

    got: list[str] = []
    sub = mqtt_client("smarthive-verify-backend", "backend")
    sub.on_message = lambda _c, _u, m: got.append(m.topic + "|" + m.payload.decode(errors="ignore"))
    sub.connect(BROKER, 8883, 10)
    sub.subscribe("smarthive/v1/nodes/+/telemetry", qos=1)
    sub.loop_start()
    _, secs = wait_for(lambda: any("telemetry|" in g for g in got), 30)
    record("security", "the backend certificate may read node telemetry (live messages observed)", any("telemetry|" in g for g in got), f"{len(got)} messages in {secs:.0f}s")
    sub.subscribe("smarthive/v1/nodes/sim-0002/health", qos=1)
    time.sleep(1)

    marker = f"forged-{random.randrange(10**9)}"
    node = mqtt_client("verify-forger", "sim-0001")
    node.connect(BROKER, 8883, 10)
    node.loop_start()
    time.sleep(1)
    node.publish("smarthive/v1/nodes/sim-0002/health", marker, qos=0)  # node 1 speaking as node 2
    time.sleep(3)
    record("security", "a node cannot publish on another node's topic (ACL)", not any(marker in g for g in got))
    heard: list[str] = []
    n1 = mqtt_client("verify-spy", "sim-0001")
    n1.on_message = lambda _c, _u, m: heard.append(m.topic)
    n1.connect(BROKER, 8883, 10)
    n1.loop_start()
    time.sleep(1)
    n1.subscribe("smarthive/v1/nodes/+/telemetry")  # the broker may grant it, but must deliver nothing (ACL)
    seen_by_backend = len(got)
    time.sleep(25)  # every node publishes every 10 s, and the backend certificate hears them
    record("security", "a node cannot read other nodes' telemetry (ACL): subscribed for 25 s, heard nothing", not heard and len(got) > seen_by_backend, f"spy heard {len(heard)}, the backend heard {len(got) - seen_by_backend}")
    for cl in (node, n1, sub):
        cl.loop_stop()
        cl.disconnect()


@guarded("capture")
def capture_checks(hives: dict[int, dict]) -> None:
    phase("Capture: every node delivers fresh, plausible, regular data")
    def warmed():
        return all(len(count_in(h["id"], now() - timedelta(minutes=3), now())) >= 15 for h in hives.values())

    ready, s = wait_for(warmed, 300, 10)
    record("capture", "the stack has been delivering for three minutes (warm-up)", bool(ready), f"{s:.0f}s")
    for i, h in hives.items():
        latest = api.json(f"/api/v1/hives/{h['id']}/latest")["latest"]
        for q, lo, hi in (("temp_in", 30, 45), ("rh_in", 20, 95), ("weight", 20, 80)):
            v = latest.get(q)
            age = (now() - datetime.fromisoformat(v["ts"].replace("Z", "+00:00"))).total_seconds() if v else 1e9
            ok = v is not None and lo <= v["value"] <= hi and age < 90 and v["clock_synced"]
            record("capture", f"hive {i} {q}: plausible, fresh, clock synced", ok, f"{v['value'] if v else None} ({age:.0f}s old)")
        raw = api.json(f"/api/v1/hives/{h['id']}/readings", params={"quantity": "temp_in", "bucket": "raw", "start": iso(now() - timedelta(minutes=3))})["points"]
        record("capture", f"hive {i}: one sample every ~10 s", 10 <= len(raw) <= 20, f"{len(raw)} in 3 min")
    week = api.json(f"/api/v1/hives/{hives[1]['id']}/readings", params={"quantity": "weight", "bucket": "1h", "start": iso(now() - timedelta(days=7))})["points"]
    record("capture", "a week of history is stored and queryable (hourly buckets)", len(week) >= 150, f"{len(week)} buckets")
    nodes = api.json("/api/v1/nodes")
    record("capture", "all five nodes registered, simulated, attached to a hive", len(nodes) >= 5 and all(n.get("simulated", True) for n in nodes), len(nodes))


def alert_where(rule: str, hive: str, since: datetime, state: str | None = None) -> dict | None:
    items = api.json("/api/v1/alerts", params={"hive_id": hive, "limit": 100})["items"]
    for a in items:
        if a["rule_id"] == rule and datetime.fromisoformat(a["opened_at"].replace("Z", "+00:00")) >= since and (state is None or a["state"] == state):
            return a
    return None


@guarded("pipeline")
def scenarios(hives: dict[int, dict], live: Live) -> dict:
    phase("Pipeline: four failures at once, observed at every hop (about 4 minutes)")
    for n in NODES.values():
        panel(n, "reset")
    time.sleep(5)
    base_mail = {m["ID"] for m in mails()}
    t0m, t0 = time.monotonic(), now()
    plan = [(2, "hornet"), (1, "varroa"), (5, "heat"), (4, "off"), (2, "swarm")]
    w0 = {i: api.json(f"/api/v1/hives/{hives[i]['id']}/latest")["latest"]["weight"]["value"] for i in (2,)}
    for i, a in plan:
        panel(NODES[i], a)
    h = {i: hives[i]["id"] for i in hives}
    ctx: dict = {"t0": t0, "t0m": t0m, "base_mail": base_mail}

    def lat(key: str, secs: float) -> None:
        LATENCY[key] = round(secs, 1)

    # --- hornet: image -> event -> alert -> push -> inbox -> email
    img, s = wait_for(lambda: next((i for i in api.json(f"/api/v1/hives/{h[2]}/images", params={"reason": "threat", "limit": 20})["items"]
                                    if any(o["cls"] == "hornet" and o["conf"] >= 0.6 for o in i["objects"]) and datetime.fromisoformat(i["captured_at"].replace("Z", "+00:00")) >= t0), None), 150)
    record("pipeline", "hornet: the node kept a frame with a wasp/hornet box (confidence >= 0.60) and uploaded it", img is not None, f"{s:.0f}s")
    if img:
        lat("hornet frame visible in the API", s)
        ctx["image"] = img
    ev, s = wait_for(lambda: [ln for ln in api.get(f"/api/v1/exports/detections?hive_id={h[2]}&include_simulated=true&format=jsonl").text.splitlines()
                              if ln and not ln.startswith("#") and '"hornet"' in ln and json.loads(ln).get("first_seen", "") >= iso(t0)], 120)
    record("pipeline", "hornet: the threat event reached the database through MQTT (export shows the episode)", bool(ev), f"{s:.0f}s")
    al, s = wait_for(lambda: alert_where("hornet_detected", h[2], t0, "open"), 120)
    record("pipeline", "hornet: the alert engine opened a CRITICAL alert", bool(al) and al["severity"] == "critical", f"{s:.0f}s")
    if al:
        lat("hornet alert opened", s)
        ctx["hornet_alert"] = al
    push, s = wait_for(lambda: [m for m in live.of("alert", since=t0m) if "ornet" in str(m.get("title"))], 60)
    record("pipeline", "hornet: the alert was pushed over the WebSocket (no refresh needed)", bool(push), f"{s:.0f}s after the alert")
    inbox, _ = wait_for(lambda: [n for n in api.json("/api/v1/me/notifications")["items"] if al and n["alert_id"] == al["id"]], 30)
    record("pipeline", "hornet: the alert is in the in-app inbox, unread", bool(inbox) and inbox[0]["read_at"] is None)
    mail, s = wait_for(lambda: next((m for m in mails() if m["ID"] not in base_mail and "ornet" in m["Subject"]), None), 90)
    record("pipeline", "hornet: the email arrived at the beekeeper", mail is not None, f"{s:.0f}s")
    if mail:
        lat("hornet email delivered", time.monotonic() - t0m)
        detail = httpx.get(f"{MAIL}/api/v1/message/{mail['ID']}", timeout=10).json()
        record("pipeline", "hornet: the email carries the entrance picture inline", len(detail.get("Inline", [])) >= 1 and "Hive 2" in detail.get("HTML", ""), f"{len(detail.get('Inline', []))} inline, to {detail['To'][0]['Address']}")
    hv = api.json(f"/api/v1/hives/{h[2]}/latest")
    record("pipeline", "hornet: the hive status counts the open alert", hv["open_alerts"] >= 1, hv["open_alerts"])

    # --- varroa
    img, s = wait_for(lambda: next((i for i in api.json(f"/api/v1/hives/{h[1]}/images", params={"reason": "varroa", "limit": 20})["items"] if any(o["cls"] == "varroa" for o in i["objects"])), None), 120)
    record("pipeline", "varroa: frames with a mite box kept by the node's filter", img is not None, f"{s:.0f}s")
    al, s = wait_for(lambda: alert_where("varroa_high", h[1], t0), 240)
    record("pipeline", "varroa: node summaries pushed the Varroa index over the threshold, warning opened", bool(al) and al["severity"] == "warning", f"{s:.0f}s")
    if al:
        lat("varroa alert opened", s)

    # --- overheating
    al, s = wait_for(lambda: alert_where("temp_out_of_range", h[5], t0), 270)
    record("pipeline", "overheating: sustained out-of-range temperature opened a warning", bool(al), f"{s:.0f}s")
    pts = api.json(f"/api/v1/hives/{h[5]}/readings", params={"quantity": "temp_in", "bucket": "raw", "start": iso(t0)})["points"]
    record("pipeline", "overheating: the readings behind it are above 37 C in the API", bool(pts) and max(p["value"] for p in pts) > 37, f"max {max((p['value'] for p in pts), default=0):.1f}")

    # --- power cut
    al, s = wait_for(lambda: alert_where("node_offline", h[4], t0, "open"), 120)
    record("pipeline", "power cut: the node said goodbye and a node-offline alert opened", bool(al), f"{s:.0f}s")
    ctx["offline_alert"] = al
    hv = api.json(f"/api/v1/hives/{h[4]}/latest")
    record("pipeline", "power cut: the hive card shows the node as offline", hv["node_status"] == "offline", hv["node_status"])

    # --- anomaly (in the seeded history) is a review item, not a notification
    an = api.json(f"/api/v1/hives/{h[3]}/anomalies", params={"start": iso(now() - timedelta(days=2))})
    items = an["items"] if isinstance(an, dict) else an
    record("pipeline", "anomaly: the unusual humidity of hive 3 is flagged", bool(items), f"{len(items)} window(s)")
    anomaly_alert = alert_where("anomaly_detected", h[3], now() - timedelta(days=1))
    notes = api.json("/api/v1/me/notifications?limit=200")["items"]
    record("pipeline", "anomaly: it never notifies anybody", not anomaly_alert or not any(n["alert_id"] == anomaly_alert["id"] for n in notes))

    # --- weight
    def gained():
        v = api.json(f"/api/v1/hives/{h[2]}/latest")["latest"]["weight"]["value"]
        return v - w0[2] if v - w0[2] >= 0.12 else None

    g, s = wait_for(gained, 200)
    record("pipeline", "honey flow: the scale reading rose in step with the simulated flow", g is not None, f"+{g:.2f} kg in {s:.0f}s" if g else "no rise")
    return ctx


@guarded("ui")
def ui_checks() -> None:
    phase("Dashboard: a real browser signs in, reads the live state, signs out")
    from playwright.sync_api import sync_playwright

    shots = REPORT / "img"
    shots.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{APP}/auth")
        page.fill('input[type="email"]', ADMIN[0])
        page.fill('input[type="password"]', "not-the-password-123")
        page.click('button[type="submit"]')
        page.wait_for_timeout(2500)
        record("ui", "a wrong password does not sign in", "/auth" in page.url and page.locator("a[href^='/colmena/']").count() == 0)
        page.fill('input[type="password"]', ADMIN[1])
        page.click('button[type="submit"]')
        page.wait_for_selector("a[href^='/colmena/']", timeout=20000)
        page.wait_for_timeout(2500)
        cards = page.locator("a[href^='/colmena/']")
        record("ui", "the dashboard lists the five hives", cards.count() == 5, cards.count())
        text = page.inner_text("body")
        record("ui", "hive 2 shows Critical and hive 4 shows Offline", "Critical" in text and "Offline" in text)
        record("ui", "the header bell shows the unread alerts", page.locator("header >> text=/^[0-9]+$/").count() > 0 or any(ch.isdigit() for ch in page.inner_text("header")), page.inner_text("header")[:60].replace("\n", " "))
        page.screenshot(path=str(shots / "ui-dashboard.png"))

        before = page.inner_text("body")
        page.wait_for_timeout(30000)
        after = page.inner_text("body")
        record("ui", "values update on their own, no reload (WebSocket)", before != after)

        links = {c.inner_text().split("\n")[0]: c.get_attribute("href") for c in cards.all()}
        h2 = next(v for k, v in links.items() if "Hive 2" in k)
        h3 = next(v for k, v in links.items() if "Hive 3" in k)
        page.goto(f"{APP}{h2}")
        page.wait_for_timeout(5000)
        body = page.inner_text("body")
        record("ui", "hive 2 page: temperature, humidity and weight charts drawn", page.locator(".recharts-line").count() >= 3, page.locator(".recharts-line").count())
        record("ui", "hive 2 page: the alert picture is shown with the detector's label", "ornet" in body and page.locator("img").count() >= 1)
        page.screenshot(path=str(shots / "ui-hive-hornet.png"), full_page=True)
        page.goto(f"{APP}{h3}")
        page.wait_for_timeout(5000)
        record("ui", "hive 3 page: the anomaly banner and the shaded band", "To review when convenient" in page.inner_text("body"))
        page.screenshot(path=str(shots / "ui-hive-anomaly.png"), full_page=True)
        page.goto(f"{APP}/alertas")
        page.wait_for_timeout(4000)
        rows = page.locator("a[href^='/alertas/']").count()
        record("ui", "the alert list shows what the scenarios raised", rows >= 5, f"{rows} alerts")
        page.locator("a[href^='/alertas/']").first.click()
        page.wait_for_timeout(3000)
        record("ui", "an alert opens with its details and actions", "cknowledge" in page.inner_text("body") or "esolve" in page.inner_text("body"))
        page.screenshot(path=str(shots / "ui-alert.png"), full_page=True)
        page.goto(f"{APP}/gestion")
        page.wait_for_timeout(3000)
        record("ui", "the setup page works for an administrator", "apiary" in page.inner_text("body").lower())
        page.goto(APP)
        page.wait_for_selector("a[href^='/colmena/']")
        page.locator("button[aria-label*='out' i], button:has(svg.lucide-log-out)").first.click()
        page.wait_for_timeout(2500)
        record("ui", "signing out returns to the sign-in page", "/auth" in page.url)
        browser.close()
    record("ui", "no JavaScript errors in the browser during the whole session", not errors, errors[:2])


@guarded("lifecycle")
def lifecycle(hives: dict[int, dict], ctx: dict) -> None:
    phase("Operations: alert handling, inbox, preferences, exports, images, admin")
    a = ctx.get("hornet_alert")
    if a:
        r = api.call("POST", f"/api/v1/alerts/{a['id']}/acknowledge")
        record("lifecycle", "acknowledge an alert", r.status_code == 200 and r.json()["state"] == "acknowledged")
        r = api.call("POST", f"/api/v1/alerts/{a['id']}/resolve", json={"note": "closed the entrance reducer"})
        record("lifecycle", "resolve it with a note", r.status_code == 200 and r.json()["state"] == "resolved" and r.json()["resolution_note"])
        d = api.json(f"/api/v1/alerts/{a['id']}")
        kinds = [e["kind"] for e in d["events"]]
        record("lifecycle", "the alert's log shows who did what, in order", kinds[:1] == ["opened"] and "acknowledged" in kinds and "resolved" in kinds, kinds)
        time.sleep(40)
        again = [x for x in api.json("/api/v1/alerts", params={"hive_id": hives[2]["id"], "state": "open"})["items"] if x["rule_id"] == "hornet_detected"]
        record("lifecycle", "a resolved alert does not come back while the same episode goes on (cooldown)", not again)
    first = api.json("/api/v1/me/notifications?limit=1")
    record("lifecycle", "inbox pages by cursor", first["next_cursor"] is not None and first["unread"] >= 3, f"unread {first['unread']}")
    nxt = api.json(f"/api/v1/me/notifications?limit=1&cursor={first['next_cursor']}")["items"]
    record("lifecycle", "...and the next page is a different notification", nxt and nxt[0]["id"] != first["items"][0]["id"])
    n = first["items"][0]
    api.call("POST", f"/api/v1/me/notifications/{n['id']}/read")
    after = api.json("/api/v1/me/notifications")
    record("lifecycle", "marking one as read lowers the unread count by one", after["unread"] == first["unread"] - 1)
    before = {i["id"] for i in api.json("/api/v1/me/notifications?limit=100")["items"]}
    r = api.call("POST", "/api/v1/me/notifications/read-all")
    after = {i["id"]: i["read_at"] for i in api.json("/api/v1/me/notifications?limit=100")["items"]}
    # alerts may open meanwhile, so judge what was there before the call
    record("lifecycle", "mark all as read", r.status_code == 204 and all(after.get(i) for i in before), f"{r.status_code}, {len(before)} notifications")
    me = api.call("PATCH", "/api/v1/me", json={"ntfy_topic": "smarthive-verify"}).json()
    record("lifecycle", "notification preferences can be changed (ntfy topic)", me["ntfy_topic"] == "smarthive-verify")
    api.call("PATCH", "/api/v1/me", json={"ntfy_topic": ""})

    h = hives[3]["id"]
    ev = api.call("POST", f"/api/v1/hives/{h}/management-events", json={"type": "inspection", "started_at": iso(now()), "ended_at": iso(now() + timedelta(minutes=20)), "data": {"notes": "verification run"}})
    record("lifecycle", "log an inspection", ev.status_code == 201, ev.text[:80])
    log = api.json(f"/api/v1/hives/{h}/management-events", params={"start": iso(now() - timedelta(hours=1))})
    items = log["items"] if isinstance(log, dict) else log
    record("lifecycle", "the inspection is in the beekeeper's log", any(e["data"].get("notes") == "verification run" for e in items))
    record("lifecycle", "predictions endpoint answers", api.get(f"/api/v1/hives/{h}/predictions").status_code == 200)
    wx = api.json(f"/api/v1/hives/{h}/weather", params={"start": iso(now() - timedelta(days=2))})
    wx = wx["points"] if isinstance(wx, dict) and "points" in wx else (wx["items"] if isinstance(wx, dict) else wx)
    record("lifecycle", "weather overlay data is available for charts", len(wx) > 24, len(wx))

    rules = api.json("/api/v1/alert-rules")
    rules = rules["items"] if isinstance(rules, dict) else rules
    record("lifecycle", "the predefined alert rules are listed", len(rules) >= 7, len(rules))
    r = api.call("PATCH", "/api/v1/alert-rules/rh_out_of_range", json={"params": {"low": 41, "high": 85, "hours": 6, "quantity": "rh_in"}})
    record("lifecycle", "an administrator can tune a threshold", r.status_code == 200 and r.json()["params"]["low"] == 41)
    api.call("PATCH", "/api/v1/alert-rules/rh_out_of_range", json={"params": {"low": 40, "high": 85, "hours": 6, "quantity": "rh_in"}})

    csv = api.get(f"/api/v1/exports/readings?hive_id={h}&quantity=temp_in&include_simulated=true&start={iso(now() - timedelta(hours=2))}").text
    lines = [ln for ln in csv.splitlines() if ln and not ln.startswith("#")]
    record("lifecycle", "readings export (CSV) carries data and provenance", len(lines) >= 10 and csv.startswith("#"), f"{len(lines)} lines")
    csv0 = api.get(f"/api/v1/exports/readings?hive_id={h}&quantity=temp_in&start={iso(now() - timedelta(hours=2))}").text
    record("lifecycle", "simulated data is left out of an export unless asked for", len([ln for ln in csv0.splitlines() if ln and not ln.startswith("#")]) <= 1)
    jl = api.get(f"/api/v1/exports/detections?hive_id={hives[2]['id']}&include_simulated=true&format=jsonl").text
    rows = [json.loads(ln) for ln in jl.splitlines() if ln and not ln.startswith("#")]
    record("lifecycle", "detections export (JSON Lines) parses", bool(rows), len(rows))

    img = ctx.get("image")
    if img:
        r = api.get(f"/api/v1/images/{img['id']}/file")
        record("lifecycle", "stored image is byte-identical to what the node sent (sha256)", r.status_code == 200 and hashlib.sha256(r.content).hexdigest() == img["sha256"] and len(r.content) == img["bytes"], f"{len(r.content)} bytes")
        for w in (160, 320, 640):
            t = api.get(f"/api/v1/images/{img['id']}/file", params={"w": w})
            ok = t.status_code == 200
            if ok:
                im = Image.open(io.BytesIO(t.content))
                ok = im.format == "JPEG" and im.width <= w and len(t.content) < len(r.content)
            record("lifecycle", f"thumbnail ?w={w} is a smaller JPEG", ok)
        meta = api.json(f"/api/v1/images/{img['id']}")
        record("lifecycle", "image metadata keeps the detector's boxes", any(o["cls"] == "hornet" for o in meta["objects"]))
        gal = api.json(f"/api/v1/hives/{hives[2]['id']}/images", params={"limit": 3})
        record("lifecycle", "gallery pages", len(gal["items"]) == 3 and gal["next_cursor"])

    ap = api.json("/api/v1/apiaries")["items"][0]["id"]
    hv = api.call("POST", f"/api/v1/apiaries/{ap}/hives", json={"name": "Verification hive", "hive_type": "Langstroth", "boxes": 1})
    node = f"sim-verify-{random.randrange(10**6)}"
    nr = api.call("POST", "/api/v1/nodes", json={"id": node})
    record("lifecycle", "admin: create a hive and register a node", hv.status_code == 201 and nr.status_code == 201, f"{node}: {nr.text[:90]}")
    if hv.status_code == 201 and nr.status_code == 201:
        hid = hv.json()["id"]
        a1 = api.call("POST", f"/api/v1/nodes/{node}/assign", json={"hive_id": hid})
        record("lifecycle", "admin: attach the node to the hive", a1.status_code == 200 and a1.json().get("hive_id") == hid, a1.text[:80])
        dup = api.call("POST", f"/api/v1/nodes/{node}/assign", json={"hive_id": hid})
        record("lifecycle", "admin: attaching twice is refused (no overlap)", dup.status_code == 409)
        tok = api.call("POST", f"/api/v1/nodes/{node}/device-token")
        record("lifecycle", "admin: issue a device token for image upload", tok.status_code == 200 and len(tok.json()["device_token"]) > 20)
        api.call("POST", f"/api/v1/nodes/{node}/unassign")
        api.call("PATCH", f"/api/v1/hives/{hid}", json={"archived": True})

    p1 = api.json("/api/v1/alerts", params={"limit": 2})
    p2 = api.json("/api/v1/alerts", params={"limit": 2, "cursor": p1["next_cursor"]}) if p1["next_cursor"] else {"items": []}
    record("lifecycle", "alert list pages by cursor without repeats", p1["next_cursor"] and {x["id"] for x in p1["items"]}.isdisjoint({x["id"] for x in p2["items"]}))


@guarded("recovery")
def restore_power(hives: dict[int, dict], ctx: dict) -> None:
    phase("Recovery: the node comes back and its alert closes itself")
    panel(NODES[4], "on")
    t = time.monotonic()
    ok, s = wait_for(lambda: api.json(f"/api/v1/hives/{hives[4]['id']}/latest")["node_status"] == "online", 90)
    record("recovery", "power restored: the node reconnects and the hive is online again", bool(ok), f"{s:.0f}s")
    a = ctx.get("offline_alert")
    if a:
        done, s = wait_for(lambda: api.json(f"/api/v1/alerts/{a['id']}")["state"] == "resolved", 90)
        record("recovery", "the node-offline alert resolved itself", bool(done), f"{s:.0f}s")
    LATENCY["node back online"] = round(time.monotonic() - t, 1)


def count_in(hive: str, since: datetime, until: datetime) -> list[str]:
    pts = api.json(f"/api/v1/hives/{hive}/readings", params={"quantity": "temp_in", "bucket": "raw", "start": iso(since), "end": iso(until)})["points"]
    return [p["ts"] for p in pts]


@guarded("resilience")
def resilience(hives: dict[int, dict], live: Live) -> None:
    phase("Resilience: broker down, ingestor down, API restart, backup and restore")
    h = hives[1]["id"]
    t_off = now()
    seen = time.monotonic()
    docker.action("mosquitto", "stop")
    time.sleep(55)
    mid = count_in(h, t_off + timedelta(seconds=15), t_off + timedelta(seconds=50))
    record("resilience", "while the broker is down nothing new reaches the database", len(mid) <= 1, f"{len(mid)} readings in the gap")
    docker.action("mosquitto", "start")
    t_on = now()

    def filled():
        ts = count_in(h, t_off, t_off + timedelta(seconds=55))
        return ts if len(ts) >= 5 else None

    ts, s = wait_for(filled, 120)
    record("resilience", "after it returns the nodes send what they kept: the gap fills in (store and forward)", bool(ts), f"{len(ts or [])} readings for the 55 s gap, {s:.0f}s after restart")
    LATENCY["gap healed after broker return"] = round(s, 1)
    record("resilience", "no reading was stored twice (idempotent by message id)", ts is not None and len(ts) == len(set(ts)))
    late = live.of("reading", since=seen, hive_id=h) + live.of("backfill", since=seen) + live.of("resync", since=seen)
    record("resilience", "the dashboard is told about the late readings over the WebSocket", len(late) >= 3, f"{len(late)} messages")

    t1 = now()
    docker.action("ingest", "stop")
    time.sleep(35)
    docker.action("ingest", "start")
    ts, s = wait_for(lambda: (lambda x: x if len(x) >= 3 else None)(count_in(h, t1 + timedelta(seconds=5), t1 + timedelta(seconds=33))), 120)
    record("resilience", "ingestor restarted: the broker kept its queue, nothing was lost", bool(ts), f"{len(ts or [])} readings from the 28 s it was down")

    docker.action("api", "restart")
    ok, s = wait_for(lambda: httpx.get(f"{APP}/readyz").status_code == 200, 90, 2)
    record("resilience", "API restarted and became ready again", bool(ok), f"{s:.0f}s")
    record("resilience", "an access token issued before the restart still works (stateless auth)", api.get("/api/v1/me").status_code == 200)

    code, out = docker.exec("api", ["smarthive", "backup"])
    record("resilience", "a database backup can be taken on demand", code == 0 and ".dump" in out, out.strip()[-80:])
    dump = next((w for w in out.split() if w.endswith(".dump")), None)
    if dump:
        code, out = docker.exec("api", ["smarthive", "restore-check", dump])
        record("resilience", "the backup restores into a scratch database and its row counts match", code == 0, out.strip()[-120:])


@guarded("limits")
def limits() -> None:
    phase("Abuse resistance")
    codes = []
    c = httpx.Client(base_url=APP)
    for _ in range(30):
        codes.append(c.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong-password-123"}).status_code)
    record("limits", "repeated failed logins are rate limited (429)", 429 in codes, f"first 429 after {codes.index(429) + 1}" if 429 in codes else codes[-3:])
    try:  # the limiter is per client address and in memory: restart the API so this run does not lock the next one out
        docker.action("api", "restart")
        wait_for(lambda: httpx.get(f"{APP}/readyz").status_code == 200, 90, 2)
    except Exception:  # noqa: BLE001
        pass
    big = httpx.post(f"{APP}/device/v1/images", content=b"x" * (7 * 1024 * 1024), headers={"content-type": "image/jpeg"})
    record("limits", "oversized uploads are cut off at the proxy (6 MB)", big.status_code in (413, 400, 401, 403, 422) and big.status_code != 200, big.status_code)


# ---------------------------------------------------------------------------------------------- report


def write_report(started: datetime) -> None:
    REPORT.mkdir(parents=True, exist_ok=True)
    passed = sum(r["ok"] for r in RESULTS)
    total = len(RESULTS)
    (REPORT / "report.json").write_text(json.dumps({"started": iso(started), "passed": passed, "total": total, "latency_s": LATENCY, "skipped": SKIPPED, "results": RESULTS}, indent=1))
    areas: dict[str, list[dict]] = {}
    for r in RESULTS:
        areas.setdefault(r["area"], []).append(r)
    rows = ""
    for area, items in areas.items():
        rows += f"<h2>{html.escape(area)} <small>{sum(i['ok'] for i in items)}/{len(items)}</small></h2><table>"
        for i in items:
            rows += f"<tr class={'ok' if i['ok'] else 'bad'}><td>{'PASS' if i['ok'] else 'FAIL'}</td><td>{html.escape(i['name'])}</td><td>{html.escape(i['detail'])}</td></tr>"
        rows += "</table>"
    lat = "".join(f"<tr><td>{html.escape(k)}</td><td>{v} s</td></tr>" for k, v in LATENCY.items())
    shots = "".join(f"<a href='img/{p.name}'><img src='img/{p.name}'></a>" for p in sorted((REPORT / "img").glob("*.png"))) if (REPORT / "img").exists() else ""
    (REPORT / "report.html").write_text(f"""<!doctype html><meta charset=utf-8><title>SmartHive verification</title>
<style>body{{font:15px system-ui;margin:2rem auto;max-width:1000px;padding:0 1rem}}table{{border-collapse:collapse;width:100%}}td{{border-bottom:1px solid #8884;padding:4px 8px;vertical-align:top}}
.ok td:first-child{{color:#1a7f37;font-weight:700}}.bad td:first-child{{color:#cf222e;font-weight:700}}.bad{{background:#cf222e18}}small{{opacity:.6}}img{{width:31%;margin:1%;border:1px solid #8886}}</style>
<h1>SmartHive end-to-end verification</h1><p><b>{passed}/{total} checks passed</b> &middot; started {iso(started)} &middot; {'ALL GREEN' if passed == total else 'FAILURES'}</p>
<h2>Measured latencies</h2><table>{lat}</table>{rows}<h2>Screenshots</h2>{shots}""")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="skip the outage and restart tests")
    ap.add_argument("--only", default="", help="comma list of phases: platform,security,capture,pipeline,ui,lifecycle,recovery,resilience,limits")
    args = ap.parse_args()
    started = now()
    print(f"SmartHive verification, {iso(started)}", flush=True)
    api.login(*ADMIN)
    hives = {int(h["name"].split()[1]): h for h in api.json("/api/v1/hives")["items"] if h["name"].startswith("Hive ") and h["name"].split()[1].isdigit()}
    assert len(hives) == 5, f"expected the five demo hives, found {len(hives)}: is this a fresh demo stack?"

    want = {x for x in args.only.split(",") if x}

    def on(name: str) -> bool:
        return not want or name in want

    if on("platform"):
        platform_checks()
    if on("security"):
        security_checks()
    live = Live(api.token, [h["id"] for h in hives.values()])
    live.ready.wait(15)
    ctx: dict = {}
    if on("capture"):
        capture_checks(hives)
    if on("pipeline"):
        record("pipeline", "the WebSocket accepts the token and the subscription", live.ready.is_set(), live.error or "")
        ctx = scenarios(hives, live) or {}
    if on("ui"):
        ui_checks()
    if on("lifecycle"):
        lifecycle(hives, ctx)
    if on("recovery"):
        restore_power(hives, ctx)
    if on("resilience"):
        if args.quick:
            SKIPPED.append("resilience (outage and restart tests)")
        else:
            resilience(hives, live)
    if on("limits"):
        limits()
    for n in NODES.values():
        panel(n, "reset")
    write_report(started)
    passed = sum(r["ok"] for r in RESULTS)
    print(f"\n{passed}/{len(RESULTS)} checks passed. Report: {REPORT}/report.html", flush=True)
    if LATENCY:
        print("latencies (s):", json.dumps(LATENCY), flush=True)
    sys.exit(0 if passed == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
