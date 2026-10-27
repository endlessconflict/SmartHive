"""MQTT loop around the handler: persistent session, manual acknowledgement, reconnect, clean shutdown."""

import asyncio
import logging

import aiomqtt
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from smarthive.config import Settings
from smarthive.ingest.handler import ingest
from smarthive.ingest.handlers import TOPIC_FILTERS

log = logging.getLogger("smarthive.ingest")

MAX_BACKOFF_S = 30.0
# Broker or database away for a moment: wait and try again, never drop a valid batch.
TRANSIENT = (OSError, OperationalError, InterfaceError)


def tls_parameters(settings: Settings) -> aiomqtt.TLSParameters | None:
    """TLS only when a CA is configured; a client certificate needs its key and the other way round."""
    if not settings.mqtt_tls_ca:
        return None
    if bool(settings.mqtt_tls_cert) != bool(settings.mqtt_tls_key):
        raise ValueError("SMARTHIVE_MQTT_TLS_CERT and SMARTHIVE_MQTT_TLS_KEY must be set together")
    return aiomqtt.TLSParameters(
        ca_certs=settings.mqtt_tls_ca, certfile=settings.mqtt_tls_cert, keyfile=settings.mqtt_tls_key
    )


async def process(engine: AsyncEngine, topic: str, payload: bytes, sleep: float = 1.0) -> None:
    """Handle one message to completion. Never raises, so nothing in here can end the message loop."""
    delay = sleep
    while True:
        try:
            await ingest(engine, topic, payload)
            return
        except TRANSIENT as e:
            log.warning(
                "database_unavailable",
                extra={"fields": {"topic": topic, "error": str(e)[:200], "retry_in_s": delay}},
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, MAX_BACKOFF_S)
        except Exception:
            # a valid batch the database refuses will be refused again; log it loudly and move on
            log.exception("message_insert_failed", extra={"fields": {"topic": topic}})
            return


async def _consume(settings: Settings, engine: AsyncEngine, busy: asyncio.Lock) -> None:
    tls = tls_parameters(settings)
    backoff = 1.0
    while True:
        client = aiomqtt.Client(
            settings.mqtt_host,
            settings.mqtt_port,
            username=settings.mqtt_username,
            password=settings.mqtt_password,
            identifier=settings.mqtt_client_id,
            clean_session=False,  # QoS 1 messages published while we were down are delivered on return
            tls_params=tls,
        )
        # aiomqtt does not expose manual acknowledgement; paho 2.x does. Without it the PUBACK would go
        # out before our insert commits and a crash in between would lose the batch.
        paho = client._client  # noqa: SLF001
        paho.manual_ack_set(True)
        try:
            async with client:
                backoff = 1.0
                for topic_filter in TOPIC_FILTERS:
                    await client.subscribe(topic_filter, qos=1)
                log.info("mqtt_connected", extra={"fields": {"host": settings.mqtt_host}})
                async for message in client.messages:
                    async with busy:
                        payload = message.payload if isinstance(message.payload, bytes) else b""
                        await process(engine, str(message.topic), payload)
                        paho.ack(message.mid, message.qos)  # after the commit, or after a logged rejection
        except aiomqtt.MqttError as e:
            log.warning("mqtt_disconnected", extra={"fields": {"error": str(e), "retry_in_s": backoff}})
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_S)


async def run(settings: Settings, stop: asyncio.Event) -> None:
    """Run until `stop` is set; the message being inserted at that moment is finished first."""
    engine = create_async_engine(settings.engine_url, pool_pre_ping=True)
    busy = asyncio.Lock()
    task = asyncio.create_task(_consume(settings, engine, busy))
    try:
        stopped = asyncio.create_task(stop.wait())
        await asyncio.wait({task, stopped}, return_when=asyncio.FIRST_COMPLETED)
        async with busy:  # waits for the in-flight insert
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    finally:
        await engine.dispose()
        log.info("ingest_stopped")
