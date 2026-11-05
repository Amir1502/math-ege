"""Alembic environment; DATABASE_URL and app configuration share one parser."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from app.config import Settings
from app.database import Database
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url") or Settings.from_env().database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def migrate(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    supplied = config.attributes.get("connection")
    if supplied is not None:
        migrate(supplied)
        return
    settings = Settings.from_env()
    override = config.get_main_option("sqlalchemy.url")
    if override:
        from dataclasses import replace

        settings = replace(settings, database_url=override)
    database = Database(settings)
    try:
        with database.engine.connect() as connection:
            migrate(connection)
    finally:
        database.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
