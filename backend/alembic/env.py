from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.core.database import Base
import app.models  # noqa: F401; register every mapped table.

config = context.config
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=get_settings().database_url, target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"}, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def migrate(connection):
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    if config.attributes.get("connection") is not None:
        migrate(config.attributes["connection"])
        return
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_settings().database_url
    engine = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool,
                                connect_args={"connect_timeout": 10})
    with engine.connect() as connection:
        migrate(connection)
    engine.dispose()


run_migrations_offline() if context.is_offline_mode() else run_migrations_online()
