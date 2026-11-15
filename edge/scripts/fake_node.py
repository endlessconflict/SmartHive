"""The real Raspberry Pi node code (outbox, uplink, MQTT) with simulated sensors, to try US03 without hardware.

    # against the Compose broker; the certificate comes from infra/pki/gen_certs.sh sim-0001
    python edge/scripts/fake_node.py --node sim-0001 --interval 5 --weight 41

    # how many messages are on disk and how many wait to be sent
    python edge/scripts/fake_node.py --node sim-0001 --show

    # also the image pipeline, with your photos as the camera (see pi_node/photo_camera.py for the folders)
    python edge/scripts/fake_node.py --node node-0001 --images --photos C:/fotos

Unlike fake_telemetry.py, which publishes straight to the broker, this one keeps what it cannot send, also
across restarts. Stop the broker while it runs (docker compose stop mosquitto) to see it.
"""

import argparse
import logging
import os
import random
import signal
import sqlite3
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "raspberry"))

from pi_node import main as node  # noqa: E402
from pi_node.dht11 import Measurement  # noqa: E402
from pi_node.photo_camera import PhotoCamera  # noqa: E402
from pi_node.hx711 import Weight  # noqa: E402
from pi_node.outbox import Outbox  # noqa: E402
from pi_node.retention import RetentionRule  # noqa: E402


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
    print(f"{path}: {total} messages, {total - unsent} sent, {unsent} waiting")
    try:
        images = db.execute(
            "SELECT reason, count(*), count(uploaded_at), count(rejected), sum(bytes) FROM images GROUP BY reason"
        ).fetchall()
    except sqlite3.OperationalError:
        images = []
    for reason, n, up, rejected, size in images:
        print(f"  images {reason:<7} {n:4d} kept ({size / 1024 / 1024:.1f} MB), {up} uploaded, "
              f"{n - up - rejected} waiting, {rejected} rejected")
    db.close()


def single_instance(lock_path: Path, node_id: str):
    """Two copies of one node fight over its MQTT client id and its files: refuse to start a second one."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    f = open(lock_path, "a+b")
    try:
        if os.name == "nt":
            import msvcrt

            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit(f"{node_id} is already running in another terminal: stop it (Ctrl+C) or use another --node")
    return f  # the lock lasts while the file stays open, and goes away with the process


def camera(cam: PhotoCamera, every: float, stop: threading.Event) -> None:
    seen = 0
    while not stop.wait(every):
        cam.shoot()
        seen += 1
        if seen % 50 == 0:
            logging.info("mock camera: %d frames analyzed", seen)


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
    ap.add_argument("--images", action="store_true",
                    help="also the image pipeline: mock camera and vision from --photos, the filter, the upload")
    ap.add_argument("--photos", type=Path, default=None,
                    help="your photos; subfolders hornet/, shb/, varroa/ say what they show (pi_node/photo_camera.py)")
    ap.add_argument("--visit-rate", type=float, default=0.03, help="chance per frame that a pest visit starts")
    ap.add_argument("--periodic-min", type=float, default=60,
                    help="keep one image when none was kept for this long (0: never)")
    ap.add_argument("--api", default="http://localhost:8080", help="where images go (Caddy)")
    ap.add_argument("--token-file", type=Path, default=None,
                    help="where the node keeps the device token it gets over MQTT; default data/token-<node>.txt")
    ap.add_argument("--frame-every", type=float, default=2.0, metavar="S", help="seconds between analyzed frames")
    ap.add_argument("--sample-rate", type=float, default=RetentionRule().sample_rate)
    args = ap.parse_args()

    outbox_path = args.outbox or Path("data") / f"outbox-{args.node}.db"
    if args.show:
        show(outbox_path)
        return

    lock = single_instance(outbox_path.with_suffix(".lock"), args.node)  # noqa: F841
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    pki = Path(args.pki)
    tls = not args.no_tls
    scale_cfg = None
    if args.weight is not None:
        scale_cfg = node.ScaleConfig(0, 0, 0, 1.0, args.interval, "")
    images_cfg = None
    cam = None
    if args.images:
        if args.photos is None:
            sys.exit("--images needs --photos <folder with your photos>: no picture is generated")
        frames_dir = Path("data") / f"frames-{args.node}"  # RAM on the Pi: empty after a restart, so here too
        for old in (*frames_dir.glob("*.jpg"), *frames_dir.glob("*.json")):
            old.unlink(missing_ok=True)
        try:
            cam = PhotoCamera(args.photos, frames_dir, visit_rate=args.visit_rate)
        except (OSError, ValueError) as e:
            sys.exit(str(e))
        logging.info("mock camera: %d background photos, pests %s", len(cam.background),
                     {k: len(v) for k, v in cam.pests.items()} or "none")
        token_file = args.token_file or Path("data") / f"token-{args.node}.txt"  # asked for if missing
        images_cfg = node.ImagesConfig(
            api_url=args.api,
            device_token_file=token_file,
            frames_dir=frames_dir,
            image_dir=Path("data") / f"images-{args.node}",
            rule=RetentionRule(sample_rate=args.sample_rate, periodic_every_s=args.periodic_min * 60 or None),
            raise_events=True,
        )
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
        images=images_cfg,
    )
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    if cam is not None:
        threading.Thread(target=camera, args=(cam, args.frame_every, stop), daemon=True).start()
    outbox = Outbox(outbox_path)
    try:
        node.run(cfg, FakeDht11(), FakeScale(args.weight) if args.weight is not None else None, outbox, stop)
    finally:
        outbox.close()


if __name__ == "__main__":
    run()
