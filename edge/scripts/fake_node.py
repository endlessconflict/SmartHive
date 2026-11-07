"""The real Raspberry Pi node code (outbox, uplink, MQTT) with simulated sensors, to try US03 without hardware.

    # against the Compose broker; the certificate comes from infra/pki/gen_certs.sh sim-0001
    python edge/scripts/fake_node.py --node sim-0001 --interval 5 --weight 41

    # how many messages are on disk and how many wait to be sent
    python edge/scripts/fake_node.py --node sim-0001 --show

Unlike fake_telemetry.py, which publishes straight to the broker, this one keeps what it cannot send, also
across restarts. Stop the broker while it runs (docker compose stop mosquitto) to see it.
"""

import argparse
import logging
import random
import signal
import sqlite3
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "raspberry"))

from pi_node import main as node  # noqa: E402
from pi_node.dht11 import Measurement  # noqa: E402
from pi_node.hx711 import Weight  # noqa: E402
from pi_node.outbox import Outbox  # noqa: E402


class FakeDht11:
    def read(self) -> Measurement:
        return Measurement(round(random.gauss(35, 0.8), 1), round(random.gauss(58, 3), 1))


class FakeScale:
    def __init__(self, kg: float) -> None:
        self.kg = kg

    def read(self) -> Weight:
        return Weight(random.gauss(self.kg, 0.03), "ok")


def show(path: Path) -> None:
    if not path.exists():
        sys.exit(f"{path} does not exist yet: run the node first")
    db = sqlite3.connect(path)
    total, unsent = db.execute("SELECT count(*), count(*) - count(sent_at) FROM outbox").fetchone()
    db.close()
    print(f"{path}: {total} messages, {total - unsent} sent, {unsent} waiting")


def run() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--node", default="sim-0001", help="must match the certificate; use the sim- prefix")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=None, help="default 8883, or 1883 with --no-tls")
    ap.add_argument("--no-tls", action="store_true", help="plain MQTT, for a local test broker")
    ap.add_argument("--pki", default="infra/pki", help="folder with ca.crt and <node>.crt/<node>.key")
    ap.add_argument("--interval", type=float, default=5.0, help="seconds between samples")
    ap.add_argument("--weight", type=float, default=None, metavar="KG", help="also send weight around this value")
    ap.add_argument("--outbox", type=Path, default=None, help="default data/outbox-<node>.db")
    ap.add_argument("--show", action="store_true", help="print the outbox counts and exit")
    args = ap.parse_args()

    outbox_path = args.outbox or Path("data") / f"outbox-{args.node}.db"
    if args.show:
        show(outbox_path)
        return

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    pki = Path(args.pki)
    tls = not args.no_tls
    scale_cfg = None
    if args.weight is not None:
        scale_cfg = node.ScaleConfig(0, 0, 0, 1.0, args.interval, "")
    cfg = node.Config(
        args.node,
        args.interval,
        args.host,
        args.port or (8883 if tls else 1883),
        tls,
        str(pki / "ca.crt") if tls else None,
        str(pki / f"{args.node}.crt") if tls else None,
        str(pki / f"{args.node}.key") if tls else None,
        scale_cfg,
        outbox_path,
    )
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    outbox = Outbox(outbox_path)
    try:
        node.run(cfg, FakeDht11(), FakeScale(args.weight) if args.weight is not None else None, outbox, stop)
    finally:
        outbox.close()


if __name__ == "__main__":
    run()
