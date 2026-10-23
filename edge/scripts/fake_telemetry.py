"""Publishes synthetic DHT11 telemetry (temperature and humidity with Gaussian noise) to test the backend.

    # against the Compose broker (mutual TLS); certificates from infra/pki/gen_certs.sh sim-0001 sim-0002
    python edge/scripts/fake_telemetry.py --host localhost --pki infra/pki --nodes sim-0001 sim-0002

    # plain broker on 1883, or no broker at all
    python edge/scripts/fake_telemetry.py --host localhost --port 1883 --no-tls --interval 2
    python edge/scripts/fake_telemetry.py --dry-run --count 3

Each value is mean + N(0, sd). With --dht11 the values are rounded to whole units and clipped to the
DHT11 range (0-50 degC, 20-90 %RH), like the real sensor; --fail-p adds read errors (value null).
Node ids should start with `sim-` so the backend can tell synthetic data from real data.
"""

import argparse
import json
import logging
import os
import random
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

log = logging.getLogger("fake_telemetry")

DHT11_RANGE = {"temp_in": (0.0, 50.0), "rh_in": (20.0, 90.0)}
UNITS = {"temp_in": "degC", "rh_in": "pct_rh"}


def uuid7() -> str:
    b = bytearray((time.time_ns() // 1_000_000).to_bytes(6, "big") + os.urandom(10))
    b[6] = (b[6] & 0x0F) | 0x70
    b[8] = (b[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(b)))


def iso(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class Noise:
    temp_mean: float
    temp_sd: float
    rh_mean: float
    rh_sd: float
    dht11: bool
    fail_p: float


def reading(rng: random.Random, noise: Noise, quantity: str, mean: float, sd: float, common: dict) -> dict:
    r = {**common, "quantity": quantity, "unit": UNITS[quantity]}
    if rng.random() < noise.fail_p:
        return {**r, "value": None, "quality": "read_error"}
    value, quality = rng.gauss(mean, sd), "ok"
    if noise.dht11:
        lo, hi = DHT11_RANGE[quantity]
        if not lo <= value <= hi:
            value, quality = min(max(value, lo), hi), "clipped"
        value = float(round(value))
    return {**r, "value": round(value, 2), "quality": quality}


def telemetry(rng: random.Random, noise: Noise, node_id: str, boot_id: str, start_mono: float, batch: int,
              step_s: float) -> dict:
    """One message with `batch` samples, `step_s` apart and ending now (a node draining its queue)."""
    now, mono_ms = datetime.now(UTC), int((time.monotonic() - start_mono) * 1000)
    readings = []
    for k in range(batch - 1, -1, -1):
        common = {"ts": iso(now - timedelta(seconds=k * step_s)), "mono_ms": max(0, mono_ms - int(k * step_s * 1000)),
                  "clock_synced": True, "sensor": "dht11-0"}
        readings.append(reading(rng, noise, "temp_in", noise.temp_mean, noise.temp_sd, common))
        readings.append(reading(rng, noise, "rh_in", noise.rh_mean, noise.rh_sd, common))
    return {"schema": "smarthive.telemetry/1.0", "msg_id": uuid7(), "node_id": node_id, "boot_id": boot_id,
            "sent_at": iso(now), "readings": readings}


def connect(args: argparse.Namespace, node_id: str):
    import paho.mqtt.client as mqtt  # only needed when actually publishing

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{node_id}-fake")
    if not args.no_tls:
        pki = Path(args.pki)
        # the broker takes the MQTT user from the certificate CN, so each fake node needs its own certificate
        client.tls_set(ca_certs=str(pki / "ca.crt"), certfile=str(pki / f"{node_id}.crt"),
                       keyfile=str(pki / f"{node_id}.key"))
    status = f"smarthive/v1/nodes/{node_id}/status"
    client.will_set(status, json.dumps({"state": "offline"}), qos=1, retain=True)
    client.connect(args.host, args.port, keepalive=60)
    client.loop_start()
    return client


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=None, help="default 8883, or 1883 with --no-tls")
    ap.add_argument("--no-tls", action="store_true", help="plain MQTT, for a local test broker")
    ap.add_argument("--pki", default="infra/pki", help="folder with ca.crt and <node>.crt/<node>.key")
    ap.add_argument("--nodes", nargs="+", default=["sim-0001"])
    ap.add_argument("--interval", type=float, default=5.0, help="seconds between messages per node")
    ap.add_argument("--count", type=int, default=0, help="messages per node, 0 = until Ctrl+C")
    ap.add_argument("--batch", type=int, default=1, help="samples per message")
    ap.add_argument("--temp-mean", type=float, default=35.0, help="degC; brood nest is about 34-35")
    ap.add_argument("--temp-sd", type=float, default=0.8)
    ap.add_argument("--rh-mean", type=float, default=58.0, help="%%RH")
    ap.add_argument("--rh-sd", type=float, default=3.0)
    ap.add_argument("--dht11", action="store_true", help="round and clip like a real DHT11")
    ap.add_argument("--fail-p", type=float, default=0.0, help="probability of a read_error per value")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true", help="print the payloads instead of publishing")
    args = ap.parse_args()
    args.port = args.port or (1883 if args.no_tls else 8883)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    for n in args.nodes:
        if not n.startswith("sim-"):
            log.warning("%s has no sim- prefix: the backend will store it as real data", n)

    noise = Noise(args.temp_mean, args.temp_sd, args.rh_mean, args.rh_sd, args.dht11, args.fail_p)
    rng = random.Random(args.seed)
    boot_ids = {n: str(uuid.uuid4()) for n in args.nodes}
    clients = {} if args.dry_run else {n: connect(args, n) for n in args.nodes}
    for n, c in clients.items():
        c.publish(f"smarthive/v1/nodes/{n}/status", json.dumps({"state": "online", "boot_id": boot_ids[n]}),
                  qos=1, retain=True)

    start, sent = time.monotonic(), 0
    try:
        while args.count == 0 or sent < args.count:
            for n in args.nodes:
                doc = telemetry(rng, noise, n, boot_ids[n], start, args.batch, args.interval / args.batch)
                body = json.dumps(doc, separators=(",", ":"))
                if args.dry_run:
                    print(json.dumps(doc, indent=2))
                    continue
                clients[n].publish(f"smarthive/v1/nodes/{n}/telemetry", body, qos=1).wait_for_publish(timeout=10)
                last = doc["readings"][-2:]
                log.info("%s  temp %s  rh %s", n, last[0]["value"], last[1]["value"])
            sent += 1
            if args.count == 0 or sent < args.count:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        for n, c in clients.items():
            c.publish(f"smarthive/v1/nodes/{n}/status", json.dumps({"state": "offline", "reason": "shutdown"}),
                      qos=1, retain=True).wait_for_publish(timeout=5)
            c.disconnect()
            c.loop_stop()
    log.info("sent %d messages per node", sent)


if __name__ == "__main__":
    sys.exit(main())
