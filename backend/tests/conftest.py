"""Isolated SQLite databases and copies of the actual content package."""

import json
from collections.abc import Iterator
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import LEGACY_CONTENT_DIR, Settings
from app.content import load_content
from app.main import create_app

TEST_ORIGIN = "http://testserver"
MUTATION_HEADERS = {"Origin": TEST_ORIGIN, "X-Requested-With": "math-ege"}


@pytest.fixture
def content_dir(tmp_path: Path) -> Path:
    """Copy real content; use the isolated fixture only while content is absent."""
    directory = tmp_path / "content"
    directory.mkdir()
    names = ("profile.json", "lessons.json", "tasks.json")
    if all((LEGACY_CONTENT_DIR / name).exists() for name in names):
        for name in names:
            (directory / name).write_bytes((LEGACY_CONTENT_DIR / name).read_bytes())
        return directory

    slots = [
        {
            "number": number, "id": f"slot-{number}", "title": f"Позиция {number}",
            "level": "Б", "summary": "Изолированная тестовая матрица.",
            "skills": [{"id": f"skill-{number}", "title": "Вычисление"}],
            "lesson_id": f"lesson-{number}",
        }
        for number in range(1, 14)
    ]
    profile = {
        "id": "test-profile", "year": 2027, "title": "Тестовый проект", "status": "draft",
        "revision": "test-1", "verified_at": "2026-11-05",
        "verification_note": "Только изолированная тестовая фикстура.",
        "source_urls": ["https://example.org/specification"], "slots": slots,
    }
    lessons = [
        {
            "id": f"lesson-{number}", "title": "Вычисление", "slot": number, "minutes": 3,
            "skill_ids": [f"skill-{number}"],
            "sections": [{"heading": "Правило", "body": "Разделите два на четыре.",
                          "formula": None}],
            "example": {"statement": "Найдите половину.", "steps": ["Разделите на два."],
                        "answer": "0,5"},
            "takeaway": "Проверяйте точный ответ.",
        }
        for number in range(1, 14)
    ]
    tasks = [
        {
            "id": f"test-task-{number}-{index}", "revision": "test-1", "slot": number,
            "topic": "Вычисление", "title": "Половина", "statement": "Найдите 2/4.",
            "formula": None, "table": None, "skill_ids": [f"skill-{number}"],
            "family_id": f"test-family-{number}", "estimated_seconds": 60,
            "review_status": "demo", "hint_count": 3, "answer": "0,5",
            "hints": ["Сократите дробь.", "Разделите на два.", "Запишите десятичную дробь."],
            "solution": ["2/4 = 1/2 = 0,5."],
            "source": {"author": "Test fixture", "origin": "Original test fixture",
                       "rights": "Test use", "reviewed_by": None},
            "profile_id": "test-profile", "difficulty": 1, "rounding": None,
        }
        for number in range(1, 14)
        for index in range(5)
    ]
    for name, value in zip(names, (profile, lessons, tasks), strict=True):
        (directory / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return directory


@pytest.fixture
def content(content_dir):
    return load_content(content_dir)


@pytest.fixture
def clock():
    return [datetime(2026, 11, 5, 12, 0, tzinfo=UTC)]


@pytest.fixture
def client_factory(tmp_path, content_dir, clock):
    with ExitStack() as stack:
        count = 0

        def make_client(**overrides):
            nonlocal count
            count += 1
            settings = Settings(
                **{
                    "database_url": f"sqlite:///{(tmp_path / f'test-{count}.sqlite3').as_posix()}",
                    "content_dir": content_dir,
                    "allow_demo_content": True,
                    "allowed_origins": (TEST_ORIGIN,),
                    **overrides,
                }
            )
            app = create_app(settings, clock=lambda: clock[0])
            app.state.database.create_schema_for_tests()
            return stack.enter_context(
                TestClient(app, base_url=TEST_ORIGIN, headers=MUTATION_HEADERS)
            )

        yield make_client


@pytest.fixture
def client(client_factory) -> Iterator[TestClient]:
    yield client_factory()


@pytest.fixture
def guest_client(client):
    response = client.post("/api/v1/guest", json={})
    assert response.status_code == 200
    return client
