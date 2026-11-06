"""Reads the DHT11 every `sample_interval_s`, and the scale if there is one, and publishes over MQTT.

    python -m pi_node.main --config config.toml

One telemetry message per sample, QoS 1. While the broker is unreachable paho keeps them queued in
memory (up to `max_pending`) and sends them when the connection is back. The network itself (Wi-Fi or Ethernet) is the operating system's job, see README.md.
"""

import argparse
import logging
import signal
import subprocess
import threading
import time
import tomllib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import paho.mqtt.client as mqtt

from pi_node import payload
from pi_node.dht11 import Dht11
from pi_node.hx711 import GpiodPins, Hx711, Weight

log = logging.getLogger("pi_node")


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
class Config:
    node_id: str
    sample_interval_s: float
    max_pending: int
    host: str
    port: int
    tls: bool
    ca: str | None
    cert: str | None
    key: str | None
    scale: ScaleConfig | None = None

    @classmethod
    def load(cls, path: Path) -> "Config":
        raw = tomllib.loads(path.read_text())
        m = raw.get("mqtt", {})
        return cls(
            node_id=raw["node_id"],
            sample_interval_s=float(raw.get("sample_interval_s", 60)),
            max_pending=int(raw.get("max_pending", 1440)),
            host=m.get("host", "gateway.local"),
            port=int(m.get("port", 8883)),
            tls=bool(m.get("tls", True)),
            ca=m.get("ca"),
            cert=m.get("cert"),
            key=m.get("key"),
            scale=ScaleConfig.load(raw["scale"]) if "scale" in raw else None,
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
    client.max_queued_messages_set(cfg.max_pending)
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


def run(cfg: Config, sensor: Dht11, scale: Hx711 | None, stop: threading.Event) -> None:
    boot_id = str(uuid.uuid4())
    log.info("node %s, boot %s", cfg.node_id, boot_id)
    client = make_client(cfg, boot_id)

    next_at = next_weight_at = time.monotonic()
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
        info = client.publish(payload.topic(cfg.node_id, "telemetry"),
                              payload.telemetry(cfg.node_id, boot_id, [sample]), qos=1)
        if info.rc == mqtt.MQTT_ERR_QUEUE_SIZE:
            log.warning("send queue full (%d), reading dropped", cfg.max_pending)
        next_at += cfg.sample_interval_s
        stop.wait(max(0.0, next_at - time.monotonic()))

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
    run(cfg, Dht11(), scale, stop)


if __name__ == "__main__":
    main()
