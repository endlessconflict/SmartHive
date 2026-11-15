"""The token the node uploads images with, fetched over MQTT so nobody has to copy it (messaging contract).

The node's certificate already proves who it is to the broker, and the ACL lets a node use only its own
topics. So when the node has no token, or the API refused it, it publishes on `.../<node>/token/req` and the
backend answers on `.../<node>/token` with a fresh one. Only its hash is stored on the server; the node keeps
it in `path` (mode 600) and reuses it after a restart.
"""

import json
import logging
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

import paho.mqtt.client as mqtt

from pi_node import payload

log = logging.getLogger("pi_node")

RETRY_S = 30.0  # a request the backend did not answer (ingest down) is sent again after this long


class DeviceToken:
    def __init__(self, node_id: str, path: Path, clock: Callable[[], float] = time.monotonic) -> None:
        self.path = path
        self.topic = payload.topic(node_id, "token")
        self.request_topic = payload.topic(node_id, "token/req")
        self.clock = clock
        self._lock = threading.Lock()
        self._value = self._read()
        self._asked_at: float | None = None

    def _read(self) -> str | None:
        try:
            return self.path.read_text().strip() or None
        except FileNotFoundError:
            return None

    @property
    def value(self) -> str | None:
        with self._lock:
            return self._value

    def subscribe(self, client: mqtt.Client) -> None:
        """Call on every connect: the node's session is clean, so the subscription does not survive."""
        client.message_callback_add(self.topic, self._on_message)
        client.subscribe(self.topic, qos=1)
        with self._lock:
            self._asked_at = None  # a request sent before the drop may have been lost with it
        self._ask(client)

    def request(self, client: mqtt.Client) -> None:
        """Ask for a token when there is none, at most once every RETRY_S."""
        if client.is_connected():  # offline, the request would only pile up in paho's queue
            self._ask(client)

    def _ask(self, client: mqtt.Client) -> None:
        with self._lock:
            if self._value is not None:
                return
            if self._asked_at is not None and self.clock() - self._asked_at < RETRY_S:
                return
            self._asked_at = self.clock()
        client.publish(self.request_topic, b"{}", qos=1)
        log.info("asked the backend for a device token")

    def refused(self, client: mqtt.Client) -> None:
        """The API answered 401: the token was replaced or the node re-created. Forget it and ask again."""
        with self._lock:
            self._value = None
            self._asked_at = None
        self.request(client)

    def _on_message(self, _client: mqtt.Client, _userdata: object, msg: mqtt.MQTTMessage) -> None:
        try:
            token = json.loads(msg.payload)["token"]
            if not isinstance(token, str) or not token:
                raise ValueError("empty token")
        except (ValueError, KeyError, TypeError):
            log.error("unreadable device token message on %s", msg.topic)
            return
        self._save(token)
        with self._lock:
            self._value = token
            self._asked_at = None
        log.info("device token received and saved to %s", self.path)

    def _save(self, token: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(token + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)
