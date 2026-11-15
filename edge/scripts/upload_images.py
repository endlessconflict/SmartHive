"""Uploads your own photos (JPEG or PNG) as if a node had taken them, through the same endpoint the node uses.

    # no token yet? It is asked for over MQTT with infra/pki/<node>.crt and kept in data/token-<node>.txt
    python edge/scripts/upload_images.py photos/ --node node-0001

    # hornet photos: kept 365 days and shown as detections; without --reason they are "periodic" (30 days)
    python edge/scripts/upload_images.py photos/hornets --node node-0001 --reason threat --object hornet:0.9

The database (Neon or local) gets each image's record; the file goes to the API's image volume. The node must
be attached to a hive at `captured_at` (the file's date, or now with --now) for the photo to show in its gallery.
Uploading the same file again is harmless: the image id comes from its hash.
"""

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "raspberry"))

from pi_node.image_upload import multipart  # noqa: E402

MAX_BYTES = 5_000_000  # the API's default limit
_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) from the JPEG's frame header, or None when it can not be found."""
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        length = int.from_bytes(data[i + 2:i + 4], "big")
        if marker in _SOF:
            return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
        i += 2 + length
    return None


def png_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) from the PNG's IHDR chunk."""
    if len(data) < 24 or data[12:16] != b"IHDR":
        return None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


TYPES = {".jpg": ("image/jpeg", jpeg_size), ".jpeg": ("image/jpeg", jpeg_size), ".png": ("image/png", png_size)}


def parse_object(text: str, size: tuple[int, int] | None) -> dict:
    cls, _, conf = text.partition(":")
    w, h = size or (1, 1)
    return {"cls": cls, "conf": float(conf or 1.0), "box": [0, 0, w, h]}  # the whole picture


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path, help="folder with .jpg/.jpeg/.png files (or one file)")
    ap.add_argument("--node", required=True, help="the node the photos belong to")
    ap.add_argument("--api", default="http://localhost:8080", help="Caddy, or the API")
    ap.add_argument("--token-file", type=Path, default=None, help="default data/token-<node>.txt")
    ap.add_argument("--token", default=None, help="a device token instead of the file (POST /nodes/{id}/device-token)")
    ap.add_argument("--pki", default="infra/pki", help="folder with ca.crt and <node>.crt/.key, to ask for a token")
    ap.add_argument("--mqtt-host", default="localhost")
    ap.add_argument("--mqtt-port", type=int, default=8883)
    ap.add_argument("--reason", default="periodic", choices=["threat", "varroa", "periodic", "on_demand", "sample"])
    ap.add_argument("--object", action="append", default=[], metavar="CLASS[:CONF]",
                    help="a detection to attach, e.g. hornet:0.9 (may repeat)")
    ap.add_argument("--now", action="store_true", help="captured now, instead of the file's date")
    args = ap.parse_args()

    token_file = args.token_file or Path("data") / f"token-{args.node}.txt"
    token = args.token
    if token is None and token_file.exists():
        token = token_file.read_text().strip() or None
    if token is None:
        token = fetch_token(args, token_file)

    files = [args.folder] if args.folder.is_file() else sorted(
        p for p in args.folder.iterdir() if p.suffix.lower() in TYPES)
    if not files:
        sys.exit(f"no .jpg or .png files in {args.folder}")

    url = args.api.rstrip("/") + "/device/v1/images"
    ok = 0
    for path in files:
        data = path.read_bytes()
        if len(data) > MAX_BYTES:
            print(f"skip {path.name}: {len(data) / 1e6:.1f} MB, over the 5 MB limit")
            continue
        if path.suffix.lower() not in TYPES:
            print(f"skip {path.name}: only .jpg, .jpeg and .png")
            continue
        media, size_of = TYPES[path.suffix.lower()]
        digest = hashlib.sha256(data).hexdigest()
        size = size_of(data)
        when = datetime.now(UTC) if args.now else datetime.fromtimestamp(path.stat().st_mtime, UTC)
        meta = {
            "image_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"smarthive:{args.node}:{digest}")),
            "node_id": args.node,
            "captured_at": when.isoformat(),
            "clock_synced": True,
            "reason": args.reason,
            "sha256": digest,
            "width": size[0] if size else None,
            "height": size[1] if size else None,
            "objects": [parse_object(o, size) for o in args.object],
        }
        content_type, body = multipart(json.dumps(meta).encode(), data, f"{meta['image_id']}{path.suffix.lower()}",
                                       media)
        status, detail = post(url, token, content_type, body)
        if status == 401 and args.token is None:  # replaced since it was saved: ask for a new one, once
            print("the saved token was refused; asking for a new one")
            token = fetch_token(args, token_file)
            status, detail = post(url, token, content_type, body)
        if status in (200, 201):
            print(f"{path.name}: {'stored' if status == 201 else 'already there'}")
            ok += 1
        else:
            print(f"{path.name}: {status} {detail}")
            if status == 401:
                sys.exit("the token was refused")
    print(f"{ok} of {len(files)} uploaded")


def post(url: str, token: str, content_type: str, body: bytes) -> tuple[int, str]:
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": content_type})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, ""
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read()).get("title", "")
        except ValueError:
            detail = ""
        return e.code, detail
    except urllib.error.URLError as e:
        sys.exit(f"cannot reach {url}: {e.reason}. Is the stack up (docker compose ... up -d)?")


def fetch_token(args: argparse.Namespace, token_file: Path) -> str:
    """Asks the backend over MQTT with the node's certificate, like the node does, and saves the answer."""
    import paho.mqtt.client as mqtt

    from pi_node.device_token import DeviceToken

    pki = Path(args.pki)
    cert, key = pki / f"{args.node}.crt", pki / f"{args.node}.key"
    if not cert.exists():
        sys.exit(f"{cert} not found: create it with infra/pki/gen_certs.sh {args.node}, or pass --token")
    if token_file.exists():
        token_file.unlink()  # DeviceToken asks only when it has none
    token = DeviceToken(args.node, token_file)
    # its own client id: the same id as a running node would disconnect it
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{args.node}-upload-{uuid.uuid4().hex[:6]}")
    client.tls_set(ca_certs=str(pki / "ca.crt"), certfile=str(cert), keyfile=str(key))
    client.on_connect = lambda c, *_: token.subscribe(c)
    print(f"asking the backend for {args.node}'s device token over MQTT ({args.mqtt_host}:{args.mqtt_port})")
    try:
        client.connect(args.mqtt_host, args.mqtt_port)
    except OSError as e:
        sys.exit(f"cannot reach the broker at {args.mqtt_host}:{args.mqtt_port}: {e}. Is the stack up?")
    client.loop_start()
    try:
        deadline = time.monotonic() + 40
        while token.value is None and time.monotonic() < deadline:
            time.sleep(0.5)
            token.request(client)
    finally:
        client.disconnect()
        client.loop_stop()
    if token.value is None:
        sys.exit("no answer from the backend: is the ingest service up (docker compose ps)?")
    print(f"got it, saved to {token_file}")
    return token.value


if __name__ == "__main__":
    main()
