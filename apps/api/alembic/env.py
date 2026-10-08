"""Alembic environment.

The database URL is read from application Settings rather than alembic.ini, so
migrations always target the same database the app does.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from sendox_api.config import get_settings
from sendox_api.db import get_engine

# Imported for the side effect of populating Base.metadata.
from sendox_api.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
settings = get_settings()


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = get_engine(settings)
    with engine.connect() as connection:
        _do_run(connection)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
