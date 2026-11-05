import json
from copy import deepcopy

import pytest

from app.content import ContentError, public_task, validate_content
from app.generators.base import make_task


def package(content_dir):
    return [
        json.loads((content_dir / name).read_text(encoding="utf-8"))
        for name in ("profile.json", "lessons.json", "tasks.json")
    ]


def test_safe_figure_and_private_generation_metadata(content, content_dir):
    profile, lessons, tasks = package(content_dir)
    generated = make_task(
        content.profile, 1, "rectangle-area", 0, title="Площадь",
        statement="Стороны прямоугольника равны 3 и 4. Найдите площадь.",
        answer=12, skills=["plane-areas"], hints=["Площадь.", "Умножение.", "3 · 4."],
        solution=["3 · 4 = 12."],
        figure={
            "description": "Прямоугольник со сторонами 3 и 4.",
            "x_min": -1, "x_max": 5, "y_min": -1, "y_max": 4, "axes": False,
            "lines": [{"points": [
                {"x": 0, "y": 0}, {"x": 4, "y": 0}, {"x": 4, "y": 3},
                {"x": 0, "y": 3}, {"x": 0, "y": 0},
            ]}], "circles": [], "labels": [{"x": 2, "y": -0.5, "text": "4"}],
        },
    )
    bundle = validate_content(profile, lessons, [*tasks, generated])
    view = public_task(bundle.tasks[-1]).model_dump(mode="json")
    assert view["figure"]["description"].startswith("Прямоугольник")
    assert not {"answer", "generation", "source", "solution", "hints"} & view.keys()


def test_multiple_family_lessons_with_explicit_practice_links(content_dir):
    profile, lessons, tasks = package(content_dir)
    extra = {**deepcopy(lessons[0]), "id": "extra-plane-lesson"}
    extra["family_ids"] = [tasks[0]["family_id"]]
    extra["practice_task_ids"] = [task["id"] for task in tasks if task["slot"] == 1][:3]
    bundle = validate_content(profile, [*lessons, extra], tasks)
    assert len(bundle.lessons) == 14


def test_reviewed_package_requires_named_reviewer_distinct_from_author(content_dir):
    profile, lessons, tasks = package(content_dir)
    tasks[0]["review_status"] = "reviewed"
    with pytest.raises(ContentError):
        validate_content(profile, lessons, tasks)
    tasks[0]["source"]["reviewed_by"] = tasks[0]["source"]["author"]
    with pytest.raises(ContentError):
        validate_content(profile, lessons, tasks)
    tasks[0]["source"]["reviewed_by"] = "independent-reviewer-id"
    bundle = validate_content(profile, lessons, tasks)
    enabled = bundle.available_tasks(allow_demo_content=False)
    assert [task.id for task in enabled] == [tasks[0]["id"]]
    assert bundle.public_profile(allow_demo_content=False).demo_mode is False


@pytest.mark.parametrize("field,value", [("x_max", float("inf")), ("onclick", "run()")])
def test_figure_rejects_nonfinite_and_executable_attributes(content_dir, field, value):
    profile, lessons, tasks = package(content_dir)
    tasks[0]["figure"] = {
        "description": "Отрезок.", "x_min": -1, "x_max": 5, "y_min": -1, "y_max": 4,
        "axes": False, "lines": [], "circles": [], "labels": [], field: value,
    }
    with pytest.raises(ContentError):
        validate_content(profile, lessons, tasks)


def test_historical_task_without_new_optional_fields_still_serializes(content_dir):
    _, _, tasks = package(content_dir)
    view = public_task(tasks[0]).model_dump()
    assert view["figure"] is None
    assert view["slot_id"] is None
