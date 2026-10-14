import os

from sqlalchemy import create_engine


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "postgresql+psycopg://smarthive:smarthive@localhost:5432/smarthive")


def engine():
    return create_engine(database_url(), pool_pre_ping=True)
