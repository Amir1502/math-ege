import json
from copy import deepcopy

import pytest

from app.content import ContentError, validate_content


def test_curriculum_lists_types_without_releasing_task_answers(client, content):
    response = client.get("/api/v1/curriculum")
    assert response.status_code == 200
    data = response.json()
    assert len(data["families"]) == len({task.family_id for task in content.tasks})
    assert len(data["lessons"]) == len(content.lessons)
    assert not {"answer", "solution", "hints"} & data["families"][0].keys()
    lesson = client.get(f"/api/v1/lessons/by-id/{content.lessons[0].id}")
    assert lesson.status_code == 200
    assert lesson.json()["id"] == content.lessons[0].id


def test_foundation_links_are_stable_and_prerequisites_cannot_cycle(content_dir):
    profile, lessons, tasks = [json.loads((content_dir / name).read_text(encoding="utf-8"))
                               for name in ("profile.json", "lessons.json", "tasks.json")]
    basic = {**deepcopy(lessons[0]), "id": "base-fractions", "kind": "foundation", "slot": 0,
             "related_slot_ids": [profile["slots"][0]["id"]], "skill_ids": ["base-fractions"]}
    lessons[0]["prerequisite_ids"] = [basic["id"]]
    bundle = validate_content(profile, [*lessons, basic], tasks)
    assert bundle.lessons[-1].slot == 0
    basic["prerequisite_ids"] = [lessons[0]["id"]]
    with pytest.raises(ContentError, match="cycle"):
        validate_content(profile, [*lessons, basic], tasks)
