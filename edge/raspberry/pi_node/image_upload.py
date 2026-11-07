"""Uploads kept images to POST /device/v1/images, one at a time, threat pictures first (messaging contract).

| Response            | Node does                                        |
|---------------------|--------------------------------------------------|
| 201, 200            | mark uploaded (200: the server already had it)   |
| 409, 413, 415, 422  | mark rejected, never retried; the file stays     |
| anything else       | retry with backoff (5xx, network, 401/403 token) |
"""

import json
import logging
import random
import ssl
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from pathlib import Path

from pi_node.outbox import ImageRow, Outbox

log = logging.getLogger("pi_node")

TIMEOUT_S = 30.0
MIN_BACKOFF_S = 1.0
MAX_BACKOFF_S = 300.0
_DONE = {200, 201}
_REJECTED = {409, 413, 415, 422}


def multipart(meta: bytes, data: bytes, filename: str) -> tuple[str, bytes]:
    """(Content-Type, body) of the meta + file form the endpoint expects."""
    boundary = uuid.uuid4().hex
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="meta"\r\nContent-Type: application/json\r\n\r\n',
        meta,
        f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        b"Content-Type: image/jpeg\r\n\r\n",
        data,
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    return f"multipart/form-data; boundary={boundary}", body


def read_token(path: Path) -> str:
    token = path.read_text().strip()
    if not token:
        raise ValueError(f"{path} is empty: put the node's device token there (shown once at registration)")
    return token


class ImageUploader:
    def __init__(self, api_url: str, token: str, outbox: Outbox, ca: str | None = None,
                 clock: Callable[[], float] = time.monotonic, opener: Callable | None = None) -> None:
        self.url = api_url.rstrip("/") + "/device/v1/images"
        self.token = token
        self.outbox = outbox
        self.clock = clock
        context = ssl.create_default_context(cafile=ca) if ca else None
        self._open = opener or (lambda req: urllib.request.urlopen(req, timeout=TIMEOUT_S, context=context))
        self._delay = MIN_BACKOFF_S
        self._retry_at = 0.0

    def _post(self, row: ImageRow) -> tuple[int | None, str]:
        """(HTTP status, detail); status None when the server could not be reached."""
        content_type, body = multipart(row.meta, row.path.read_bytes(), f"{row.image_id}.jpg")
        req = urllib.request.Request(self.url, data=body, method="POST", headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": content_type})
        try:
            with self._open(req) as resp:
                return resp.status, ""
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read()).get("title", "")
            except (ValueError, AttributeError, OSError):
                detail = ""
            return e.code, detail
        except (urllib.error.URLError, OSError) as e:  # refused, DNS, TLS, timeout
            return None, str(e)

    def drain(self, stop: threading.Event, deadline: float) -> int:
        """Upload until nothing is pending, the deadline passes or an upload fails. Returns how many went up."""
        done = 0
        while not stop.is_set() and self.clock() < deadline and self.clock() >= self._retry_at:
            rows = self.outbox.pending_images(limit=1)
            if not rows:
                break
            row = rows[0]
            try:
                status, detail = self._post(row)
            except FileNotFoundError:
                self.outbox.mark_image_rejected(row.image_id, "file missing on the node")
                log.error("image %s: the file is gone", row.image_id)
                continue
            if status in _DONE:
                self.outbox.mark_uploaded(row.image_id)
                self._delay = MIN_BACKOFF_S
                done += 1
            elif status in _REJECTED:
                self.outbox.mark_image_rejected(row.image_id, f"{status} {detail}".strip())
                log.error("image %s rejected: %s %s", row.image_id, status, detail)
            else:
                self.outbox.mark_image_failed(row.image_id)
                self._retry_at = self.clock() + self._delay * random.uniform(0.5, 1.0)
                self._delay = min(self._delay * 2, MAX_BACKOFF_S)
                log.warning("image upload failed (%s %s), %d s backoff", status, detail,
                            self._retry_at - self.clock())
                break
        return done
