"""Build-only validation over the exact source bytes, using the existing backend."""

import base64
import json
import sys
from pathlib import Path

sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(sys.argv[1]).resolve()))

from app.content import ContentError, validate_content  # noqa: E402
from app.editor.validation import data_only  # noqa: E402
from app.generators import reproduce  # noqa: E402
from app.instances import instance_key  # noqa: E402


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContentError("Duplicate JSON keys are not allowed")
        result[key] = value
    return result


def main():
    encoded = json.load(sys.stdin, object_pairs_hook=unique_object)
    names = ("profile.json", "lessons.json", "tasks.json", "manifest.json")
    if set(encoded) != set(names):
        raise ContentError("The offline package requires exactly four source JSON files")
    values = {
        name: json.loads(base64.b64decode(encoded[name], validate=True).decode("utf-8"),
                         object_pairs_hook=unique_object)
        for name in names
    }
    bundle = validate_content(*(values[name] for name in names[:3]))
    source_manifest = values["manifest.json"]
    for raw in (values["profile.json"], source_manifest, *values["lessons.json"],
                *values["tasks.json"]):
        data_only(raw)
    positions = set(range(1, 14))
    if (len(bundle.tasks) != 845 or len(bundle.lessons) != 99
            or len(bundle.profile.slots) != 13
            or {slot.number for slot in bundle.profile.slots} != positions
            or {task.slot for task in bundle.tasks} != positions):
        raise ContentError("The offline course requires 845 tasks, 99 lessons and all 13 slots")
    if (bundle.profile.status != "draft"
            or any(task.review_status != "demo" or task.source.reviewed_by is not None
                   for task in bundle.tasks)
            or any(lesson.review_status != "demo" or lesson.reviewed_by is not None
                   for lesson in bundle.lessons)):
        raise ContentError("The preview must retain draft/demo status and null reviewers")
    if (source_manifest.get("profile_id") != bundle.profile.id
            or source_manifest.get("profile_revision") != bundle.profile.revision
            or source_manifest.get("task_count") != 845
            or source_manifest.get("lesson_count") != 99
            or source_manifest.get("review_status") != "demo"
            or source_manifest.get("reviewed_by") is not None):
        raise ContentError("The original build manifest does not match the course")
    generated = [task for task in bundle.tasks if task.generation is not None]
    if len(generated) != 780:
        raise ContentError("The course must preserve all 65 original and 780 materialized tasks")
    fields = ("id", "revision", "slot", "slot_id", "family_id", "skill_ids", "profile_id",
              "generation", "statement", "answer", "formula", "table", "figure", "rounding",
              "hints", "solution")
    for task in generated:
        materialized = reproduce(task.generation.template_id, task.generation.seed, bundle.profile)
        if any(getattr(task, field) != getattr(materialized, field) for field in fields):
            raise ContentError("A materialized task differs from its original seed and revision")
    print(json.dumps({"source_manifest": source_manifest,
                      "instance_keys": {task.id: instance_key(task) for task in bundle.tasks}},
                     ensure_ascii=True, allow_nan=False))


if __name__ == "__main__":
    main()
