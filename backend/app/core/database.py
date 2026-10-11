from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def utcnow():
    return datetime.now(timezone.utc)


def as_utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


def build_engine(database_url):
    options = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    else:
        options.update(pool_size=5, max_overflow=5, pool_recycle=1800, connect_args={"connect_timeout": 10})
    return create_engine(database_url, **options)


def build_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
