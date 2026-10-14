import argparse
import asyncio
import json
import logging
import signal
import sys

from smarthive.config import Settings


class JsonFormatter(logging.Formatter):
    """One JSON object per line on stdout; `extra={"fields": {...}}` becomes top-level keys."""

    def format(self, record: logging.LogRecord) -> str:
        doc: dict[str, object] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            **getattr(record, "fields", {}),
        }
        if record.exc_info:
            doc["exc"] = self.formatException(record.exc_info)
        return json.dumps(doc, default=str)


def _ingest(settings: Settings) -> None:
    from smarthive.ingest.service import run  # imported here so `--help` needs no MQTT stack

    async def main() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, stop.set)
            except NotImplementedError:  # Windows event loops have no signal handlers
                signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))
        await run(settings, stop)

    asyncio.run(main())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="smarthive")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ingest", help="subscribe to telemetry and store it")
    parser.parse_args(argv)

    settings = Settings()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=settings.log_level.upper(), handlers=[handler])
    _ingest(settings)


if __name__ == "__main__":
    main()
