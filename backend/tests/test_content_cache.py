"""The read path must not re-parse and revalidate the whole bank per request."""

import json
from pathlib import Path

import pytest

from app.config import Settings
from app.content import ContentError, load_content
from app.database import Database
from app.editor.repository import combined_content


def _rewrite_note(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["verification_note"] = payload["verification_note"] + " Изменено."
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload["verification_note"]


def test_unchanged_package_is_reused_and_a_rewrite_is_revalidated(content_dir):
    first = load_content(content_dir)
    assert load_content(content_dir) is first

    note = _rewrite_note(content_dir / "profile.json")
    second = load_content(content_dir)

    assert second is not first
    assert second.profile.verification_note == note
    assert load_content(content_dir) is second


def test_cache_keys_are_isolated_per_directory(content_dir, tmp_path):
    other = tmp_path / "other-content"
    other.mkdir()
    for name in ("profile.json", "lessons.json", "tasks.json"):
        (other / name).write_bytes((content_dir / name).read_bytes())

    assert load_content(other) is not load_content(content_dir)


def test_missing_package_is_never_cached(content_dir, tmp_path):
    with pytest.raises(ContentError):
        load_content(tmp_path / "absent")
    with pytest.raises(ContentError):
        load_content(tmp_path / "absent")


def test_nothing_published_serves_the_validated_base_without_repacking(content_dir, tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'cache.sqlite3').as_posix()}",
        content_dir=content_dir,
        allow_demo_content=True,
    )
    database = Database(settings)
    try:
        database.create_schema_for_tests()
        with database.transaction() as db:
            served = combined_content(db, settings)
    finally:
        database.dispose()

    assert served is load_content(content_dir)