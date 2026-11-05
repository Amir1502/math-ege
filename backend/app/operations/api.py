"""Staff diagnostics and an explicitly enabled, empty verification-target check."""

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import func, select, text

from app.accounts import require_staff
from app.errors import ApiError, not_found
from app.models import AttemptRecord, Guest, LearningSessionRecord
from app.operations.common import OperationError, verification_namespace
from app.operations.health import OperationHealth

router = APIRouter(prefix="/api/v1/operations", tags=["operations"])


@router.get("/health")
def diagnostics(request: Request) -> dict[str, Any]:
    require_staff(request)
    health = getattr(request.app.state, "operation_health", None)
    if not isinstance(health, OperationHealth):
        raise ApiError(503, "operations_unavailable", "Диагностика операций недоступна.")
    return health.snapshot()


@router.get("/load-target")
def load_target(request: Request) -> dict[str, Any]:
    """No route data is returned for ordinary development/production databases.

    The namespace is checked through the live connection, not a client header or URL.
    Normal operation never enables this endpoint; no learner identity is returned.
    """
    if request.app.state.settings.environment != "verification":
        raise not_found()
    try:
        namespace = verification_namespace(os.environ.get("OPS_VERIFICATION_NAMESPACE", ""))
    except OperationError:
        raise not_found() from None
    database = request.app.state.database
    with database.transaction() as db:
        if database.engine.dialect.name == "postgresql":
            actual = db.scalar(text("SELECT current_database()"))
        elif database.engine.dialect.name == "sqlite":
            attached = db.connection().exec_driver_sql("PRAGMA database_list").mappings()
            actual = next((
                Path(row["file"]).stem for row in attached
                if row["name"] == "main" and row["file"]
            ), None)
        else:
            raise not_found()
        if actual != namespace:
            raise not_found()
        counts = {
            "guests": db.scalar(select(func.count()).select_from(Guest)),
            "learning_sessions": db.scalar(select(func.count()).select_from(LearningSessionRecord)),
            "attempts": db.scalar(select(func.count()).select_from(AttemptRecord)),
        }
    return {"version": "1", "namespace": namespace, "database_namespace": actual,
            "empty": all(value == 0 for value in counts.values()), "counts": counts}
