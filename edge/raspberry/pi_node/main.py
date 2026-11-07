"""Reads the DHT11 every `sample_interval_s`, and the scale if there is one, and publishes over MQTT.

    python -m pi_node.main --config config.toml

One telemetry message per sample, QoS 1. Each one is first written to the outbox on disk, and leaves from there,
oldest first, whenever the broker is reachable. The network itself (Wi-Fi or Ethernet) is the operating system's job, see README.md.
"""

import argparse
import logging
import signal
import sqlite3
import subprocess
import threading
import time
import tomllib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import paho.mqtt.client as mqtt

from pi_node import payload
from pi_node.dht11 import Dht11
from pi_node.frames import FrameFilter
from pi_node.hx711 import GpiodPins, Hx711, Weight
from pi_node.image_upload import ImageUploader, read_token
from pi_node.outbox import Outbox
from pi_node.retention import Retention, RetentionRule
from pi_node.uplink import Uplink

log = logging.getLogger("pi_node")

PURGE_INTERVAL_S = 3600


@dataclass(frozen=True)
class ScaleConfig:
    dout_gpio: int
    sck_gpio: int
    offset: int
    counts_per_kg: float
    interval_s: float
    chip: str

    @classmethod
    def load(cls, raw: dict) -> "ScaleConfig":
        if not raw["counts_per_kg"]:
            raise ValueError("scale.counts_per_kg must not be zero; see the calibration in README.md")
        return cls(
            dout_gpio=int(raw["dout_gpio"]),
            sck_gpio=int(raw["sck_gpio"]),
            offset=int(raw["offset"]),
            counts_per_kg=float(raw["counts_per_kg"]),
            interval_s=float(raw.get("interval_s", 300)),
            chip=raw.get("chip", "/dev/gpiochip0"),
        )


@dataclass(frozen=True)
class ImagesConfig:
    api_url: str
    device_token_file: Path
    frames_dir: Path = Path("/run/smarthive/frames")
    image_dir: Path = Path("/var/lib/smarthive/images")
    ca: str | None = None
    retention_days: float = 3
    rule: RetentionRule = field(default_factory=RetentionRule)

    @classmethod
    def load(cls, raw: dict) -> "ImagesConfig":
        default = RetentionRule()
        return cls(
            api_url=raw["api_url"],
            device_token_file=Path(raw["device_token_file"]),
            frames_dir=Path(raw.get("frames_dir", "/run/smarthive/frames")),
            image_dir=Path(raw.get("image_dir", "/var/lib/smarthive/images")),
            ca=raw.get("ca"),
            retention_days=float(raw.get("retention_days", 3)),
            rule=RetentionRule(
                thresholds={**default.thresholds, **{k: float(v) for k, v in raw.get("thresholds", {}).items()}},
                sample_rate=float(raw.get("sample_rate", default.sample_rate)),
                max_samples_per_day=int(raw.get("max_samples_per_day", default.max_samples_per_day)),
            ),
        )


@dataclass(frozen=True)
class Config:
    node_id: str
    sample_interval_s: float
    host: str
    port: int
    tls: bool
    ca: str | None
    cert: str | None
    key: str | None
    scale: ScaleConfig | None = None
    outbox_path: Path = Path("/var/lib/smarthive/outbox.db")
    outbox_retention_days: float = 7
    images: ImagesConfig | None = None

    @classmethod
    def load(cls, path: Path) -> "Config":
        raw = tomllib.loads(path.read_text())
        m = raw.get("mqtt", {})
        return cls(
            node_id=raw["node_id"],
            sample_interval_s=float(raw.get("sample_interval_s", 60)),
            host=m.get("host", "gateway.local"),
            port=int(m.get("port", 8883)),
            tls=bool(m.get("tls", True)),
            ca=m.get("ca"),
            cert=m.get("cert"),
            key=m.get("key"),
            scale=ScaleConfig.load(raw["scale"]) if "scale" in raw else None,
            outbox_path=Path(raw.get("outbox_path", "/var/lib/smarthive/outbox.db")),
            outbox_retention_days=float(raw.get("outbox_retention_days", 7)),
            images=ImagesConfig.load(raw["images"]) if "images" in raw else None,
        )


def clock_synced() -> bool:
    """No RTC on the Pi: timestamps are trustworthy only after chrony/timesyncd has synced."""
    try:
        out = subprocess.run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() == "yes"
    except (OSError, subprocess.SubprocessError):
        return False


def make_client(cfg: Config, boot_id: str) -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cfg.node_id)
    if cfg.tls:
        # mutual TLS: the broker takes the MQTT user from the certificate CN, which must be the node id
        client.tls_set(ca_certs=cfg.ca, certfile=cfg.cert, keyfile=cfg.key)
    status_topic = payload.topic(cfg.node_id, "status")
    client.will_set(status_topic, payload.status("offline"), qos=1, retain=True)

    def on_connect(c, _userdata, _flags, reason_code, _props):
        if reason_code.is_failure:
            log.error("broker refused the connection: %s", reason_code)
            return
        log.info("connected to %s:%d", cfg.host, cfg.port)
        c.publish(status_topic, payload.status("online", boot_id), qos=1, retain=True)

    def on_disconnect(_c, _userdata, _flags, reason_code, _props):
        log.warning("disconnected: %s", reason_code)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.reconnect_delay_set(min_delay=1, max_delay=60)
    client.connect_async(cfg.host, cfg.port, keepalive=60)
    client.loop_start()  # background thread; retries until the network and broker are reachable
    return client


def read_scale(scale: Hx711) -> Weight:
    w = scale.read()
    if w.quality == "ok":
        log.info("weight %.2f kg", w.kg)
    else:
        log.warning("hx711 %s", w.quality)
    return w


def run(cfg: Config, sensor: Dht11, scale: Hx711 | None, outbox: Outbox, stop: threading.Event) -> None:
    boot_id = str(uuid.uuid4())
    log.info("node %s, boot %s", cfg.node_id, boot_id)
    client = make_client(cfg, boot_id)
    uplink = Uplink(client, outbox)
    frames, uploader = None, None
    if cfg.images is not None:
        im = cfg.images
        frames = FrameFilter(cfg.node_id, im.frames_dir, im.image_dir, outbox, Retention(im.rule))
        uploader = ImageUploader(im.api_url, read_token(im.device_token_file), outbox, im.ca)

    next_at = next_weight_at = time.monotonic()
    next_purge_at = next_at + PURGE_INTERVAL_S
    while not stop.is_set():
        m = sensor.read()
        if m is None:
            log.warning("dht11 read failed")
        else:
            log.info("temp %.1f C, rh %.1f %%", m.temp_c, m.rh_pct)
        weight = None
        # half a tick of margin: float rounding must not push a due reading to the next tick
        if scale is not None and cfg.scale is not None and next_at + cfg.sample_interval_s / 2 >= next_weight_at:
            weight = read_scale(scale)
            next_weight_at += cfg.scale.interval_s
        sample = payload.Sample(datetime.now(UTC), time.monotonic_ns() // 1_000_000, clock_synced(), m, weight)
        topic = payload.topic(cfg.node_id, "telemetry")
        body = payload.telemetry(cfg.node_id, boot_id, [sample])
        try:
            outbox.add(topic, body, sample.ts, sample.clock_synced)
        except sqlite3.Error:  
            log.exception("outbox write failed")
            if client.is_connected():
                client.publish(topic, body, qos=1)
        next_at += cfg.sample_interval_s
        while not stop.is_set() and time.monotonic() < next_at:  # checks often, so a reconnect is noticed at once
            try:
                sent = uplink.drain(stop, next_at)
                if sent:
                    log.info("sent %d from the outbox", sent)
                if frames is not None and uploader is not None:
                    try:
                        frames.process()
                        uploaded = uploader.drain(stop, next_at)  # after the MQTT messages: events still go first
                        if uploaded:
                            log.info("uploaded %d images", uploaded)
                    except (OSError, ValueError):  # an image problem must not stop the sensors
                        log.exception("image handling failed")
                if time.monotonic() >= next_purge_at:
                    next_purge_at += PURGE_INTERVAL_S
                    outbox.purge(datetime.now(UTC) - timedelta(days=cfg.outbox_retention_days))
                    if frames is not None and cfg.images is not None:
                        frames.purge(datetime.now(UTC) - timedelta(days=cfg.images.retention_days))
            except sqlite3.Error:
                log.exception("outbox read failed")
            stop.wait(max(0.0, min(1.0, next_at - time.monotonic())))

    log.info("shutting down")
    if client.is_connected():
        info = client.publish(payload.topic(cfg.node_id, "status"),
                              payload.status("offline", reason="shutdown"), qos=1, retain=True)
        info.wait_for_publish(timeout=5)
    client.disconnect()
    client.loop_stop()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=Path("/etc/smarthive/node.toml"))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    cfg = Config.load(args.config)
    scale = None
    if cfg.scale is not None:
        pins = GpiodPins(cfg.scale.chip, cfg.scale.dout_gpio, cfg.scale.sck_gpio)
        scale = Hx711(pins, cfg.scale.offset, cfg.scale.counts_per_kg)
    outbox = Outbox(cfg.outbox_path)
    try:
        run(cfg, Dht11(), scale, outbox, stop)
    finally:
        outbox.close()


if __name__ == "__main__":
    main()
