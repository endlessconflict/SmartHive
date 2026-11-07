"""Sends the outbox over MQTT: one message at a time, oldest first, sent only once the broker has confirmed it.

A crash between the PUBACK and the mark means the message goes out again after the restart. That is safe: it
keeps its msg_id, and the server stores each msg_id once.
"""

import logging
import random
import threading
import time
from collections.abc import Callable

from pi_node.outbox import Outbox, Row

log = logging.getLogger("pi_node")

ACK_TIMEOUT_S = 5.0
MIN_BACKOFF_S = 1.0
MAX_BACKOFF_S = 300.0


class Uplink:
    def __init__(self, client, outbox: Outbox, clock: Callable[[], float] = time.monotonic) -> None:
        self.client = client
        self.outbox = outbox
        self.clock = clock
        self._delay = MIN_BACKOFF_S
        self._retry_at = 0.0

    def _send(self, row: Row) -> bool:
        # only called while connected: paho would otherwise keep the message in its own memory queue
        info = self.client.publish(row.topic, row.payload, qos=1)
        try:
            info.wait_for_publish(ACK_TIMEOUT_S)
            return info.is_published()  # wait_for_publish just returns when it times out
        except (RuntimeError, ValueError):  # the connection dropped, or paho refused the message
            return False

    def drain(self, stop: threading.Event, deadline: float) -> int:
        """Send what is pending until it runs out, the deadline passes or a send fails. Returns how many went out."""
        sent = 0
        while not stop.is_set() and self.clock() < deadline and self.clock() >= self._retry_at:
            if not self.client.is_connected():
                break  # the rows wait on disk; paho reconnects by itself
            rows = self.outbox.pending(limit=1)
            if not rows:
                break
            if not self._send(rows[0]):
                self.outbox.mark_failed(rows[0].msg_id)
                self._retry_at = self.clock() + self._delay * random.uniform(0.5, 1.0)
                self._delay = min(self._delay * 2, MAX_BACKOFF_S)
                log.warning("no PUBACK for %s, %d s backoff", rows[0].msg_id, self._retry_at - self.clock())
                break
            self.outbox.mark_sent(rows[0].msg_id)
            self._delay = MIN_BACKOFF_S
            sent += 1
        return sent
