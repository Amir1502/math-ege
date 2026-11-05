"""PostgreSQL rejects DDL identifiers longer than 63 characters; SQLite does not.

The deployed container and the live PostgreSQL gate therefore need a static proof
that the full migration chain renders for the PostgreSQL dialect.
"""

import io
import re
from contextlib import redirect_stdout

from alembic import command
from alembic.config import Config
from sqlalchemy.dialects import postgresql

from app.accounts import models as accounts_models  # noqa: F401
from app.assessments import models as assessments_models  # noqa: F401
from app.config import BACKEND_ROOT
from app.editor import models as editor_models  # noqa: F401
from app.learning import models as learning_models  # noqa: F401
from app.models import Base

DDL_NAME = re.compile(
    r"(?:CREATE TABLE (\w+)|CREATE (?:UNIQUE )?INDEX (\w+) ON|ALTER TABLE (\w+)"
    r"|CONSTRAINT (\w+) )",
)


def render_postgres_sql() -> str:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.set_main_option(
        "sqlalchemy.url", "postgresql+psycopg://verify:placeholder@127.0.0.1:5432/verify",
    )
    buffer = io.StringIO()
    config.output_buffer = buffer
    with redirect_stdout(buffer):
        command.upgrade(config, "head", sql=True)
    return buffer.getvalue()


def test_metadata_identifiers_fit_the_postgres_limit():
    limit = postgresql.dialect().max_identifier_length
    names = set()
    for table in Base.metadata.sorted_tables:
        names.add(table.name)
        names.update(column.name for column in table.columns)
        names.update(item.name for item in table.constraints if item.name)
        names.update(index.name for index in table.indexes if index.name)
    oversized = sorted(name for name in names if len(name) > limit)
    assert oversized == []


def test_whole_migration_chain_renders_for_postgres_without_oversized_names():
    sql = render_postgres_sql()
    assert "CREATE TABLE attempts" in sql
    assert "ALTER TABLE account_magic_links ADD CONSTRAINT" in sql
    assert "fk_account_totp_credentials_enrollment_session" in sql
    assert "_alembic_tmp" not in sql
    names = [next(group for group in match if group) for match in DDL_NAME.findall(sql)]
    limit = postgresql.dialect().max_identifier_length
    assert sorted(name for name in names if len(name) > limit) == []