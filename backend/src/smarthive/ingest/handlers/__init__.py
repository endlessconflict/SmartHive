"""The handler for each node topic. To support a new message type, add a module and list it here."""

from smarthive.ingest.base import Handler
from smarthive.ingest.handlers import events, health, status, summary, telemetry

HANDLERS: dict[str, Handler] = {
    h.kind: h for h in (telemetry.HANDLER, events.HANDLER, summary.HANDLER, health.HANDLER, status.HANDLER)
}

TOPIC_PREFIX = "smarthive/v1/nodes"
TOPIC_FILTERS = [f"{TOPIC_PREFIX}/+/{kind}" for kind in HANDLERS]
