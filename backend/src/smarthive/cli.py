import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import uuid
from pathlib import Path

from smarthive.config import Settings
from smarthive.seeder import SCENARIOS


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

    # aiomqtt needs add_reader/add_writer, which the default Windows (proactor) loop lacks
    factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    with asyncio.Runner(loop_factory=factory) as runner:  # asyncio.run takes loop_factory only from 3.12
        runner.run(main())


def _worker(settings: Settings) -> None:
    from smarthive.alerts.engine import run

    async def main() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, stop.set)
            except NotImplementedError:  # Windows event loops have no signal handlers
                signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))
        await run(settings, stop)

    # asyncpg's LISTEN callback needs no special loop, but keep the same loop as `ingest` on Windows
    factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    with asyncio.Runner(loop_factory=factory) as runner:
        runner.run(main())


def _backup(settings: Settings) -> None:
    from smarthive import maintenance

    if not settings.backup_dir:
        raise SystemExit("SMARTHIVE_BACKUP_DIR is not set")
    dump = asyncio.run(maintenance.backup(settings.db_url, Path(settings.backup_dir), settings.backup_keep))
    print(dump)


def _restore_check(settings: Settings, dump: str) -> None:
    from smarthive import maintenance

    result = asyncio.run(maintenance.restore_check(settings.db_url, Path(dump)))
    for table, (expected, restored) in result.items():
        print(f"{table}: expected at least {expected}, restored {restored}")
    print("restore check passed")


def _seed(
    settings: Settings, node: str, scenario: str, rounds: int, interval: float, seed: int | None
) -> None:
    from smarthive.seeder import publish

    factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None  # aiomqtt, see _ingest
    with asyncio.Runner(loop_factory=factory) as runner:
        sent = runner.run(publish(settings, node, scenario, rounds, interval, seed))
    print(f"published {sent} messages as {node} ({scenario})")


def _migrate(settings: Settings) -> None:
    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "db" / "migrations"))
    os.environ["SMARTHIVE_DB_URL"] = settings.db_url  # read by migrations/env.py
    command.upgrade(config, "head")


def _api(settings: Settings, host: str, port: int) -> None:
    import uvicorn

    from smarthive.api.app import create_app

    uvicorn.run(
        create_app(settings),
        host=host,
        port=port,
        proxy_headers=True,
        forwarded_allow_ips=settings.forwarded_allow_ips,
        log_config=None,  # our JSON logging stays in charge
    )


def _create_user(settings: Settings, email: str, name: str, role: str, password_stdin: bool) -> None:
    import getpass

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from smarthive.api.security import hash_password

    password = sys.stdin.readline().rstrip("\n") if password_stdin else getpass.getpass("Password: ")
    if len(password) < 12:
        sys.exit("The password needs at least 12 characters.")

    async def run() -> None:
        engine = create_async_engine(settings.engine_url)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO users (id, email, display_name, password_hash, role) "
                        "VALUES (:id, :email, :name, :hash, :role)"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "email": email,
                        "name": name,
                        "hash": hash_password(password),
                        "role": role,
                    },
                )
        finally:
            await engine.dispose()

    asyncio.run(run())
    print(f"created {role} {email}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="smarthive")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ingest", help="subscribe to node topics and store them")
    sub.add_parser("worker", help="evaluate alert rules and open alerts")
    sub.add_parser("backup", help="write a database dump now and prune old ones")
    check = sub.add_parser(
        "restore-check", help="restore a dump into a scratch database and compare row counts"
    )
    check.add_argument("dump")
    seed = sub.add_parser("seed", help="publish fake node messages to the broker (test data)")
    seed.add_argument("--node", default="node-0001", help="node id; must match the client certificate CN")
    seed.add_argument("--scenario", choices=SCENARIOS, default="normal")
    seed.add_argument("--rounds", type=int, default=1)
    seed.add_argument("--interval", type=float, default=5.0, help="seconds between rounds")
    seed.add_argument("--seed", type=int, default=None, help="random seed, for repeatable values")
    sub.add_parser("migrate", help="apply database migrations up to the latest")
    api = sub.add_parser("api", help="serve the REST API")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8000)
    user = sub.add_parser("create-user", help="create a user; the password is asked for, never an argument")
    user.add_argument("--email", required=True)
    user.add_argument("--name", required=True)
    user.add_argument("--role", choices=["beekeeper", "admin"], default="admin")
    user.add_argument("--password-stdin", action="store_true", help="read the password from stdin")
    args = parser.parse_args(argv)

    settings = Settings()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=settings.log_level.upper(), handlers=[handler])
    if args.command == "ingest":
        _ingest(settings)
    elif args.command == "worker":
        _worker(settings)
    elif args.command == "backup":
        _backup(settings)
    elif args.command == "restore-check":
        _restore_check(settings, args.dump)
    elif args.command == "seed":
        _seed(settings, args.node, args.scenario, args.rounds, args.interval, args.seed)
    elif args.command == "migrate":
        _migrate(settings)
    elif args.command == "api":
        _api(settings, args.host, args.port)
    else:
        _create_user(settings, args.email, args.name, args.role, args.password_stdin)


if __name__ == "__main__":
    main()
