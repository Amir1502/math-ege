#!/bin/sh
set -eu
umask 077
set -a
. "${OPS_BACKUP_ENV_FILE:-/etc/math-ege/backup.env}"
set +a
: "${OPS_APP_DIR:?Set the absolute checkout directory}"
: "${OPS_BACKUP_DIR:?Set the dedicated backup directory}"
: "${OPS_SOURCE_DATABASE:?Set the source database name}"
: "${OPS_EXPECTED_HEAD:?Set the deployed Alembic revision}"
: "${PGUSER:?Set the PostgreSQL backup role}"
exec "$OPS_APP_DIR/backend/.venv/bin/python" \
    "$OPS_APP_DIR/scripts/ops/backup.py" backup --expected-head "$OPS_EXPECTED_HEAD"
