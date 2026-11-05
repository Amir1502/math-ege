"""Central assembly contracts; arithmetic oracles belong to the authored shards."""

import hashlib
import json
import os
import re
import sys
from collections import Counter
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from app import generators
from app.content import ContentError, Task, load_content, public_task, validate_content
from app.generators import algebra_analysis, applied_finance, build, geometry_probability
from tests import test_course_algebra as algebra_checks
from tests import test_course_applied as applied_checks
from tests import test_course_geometry as geometry_checks

LEGACY_DIR = Path(__file__).resolve().parents[1] / "content"
LEGACY_HASHES = {
    "profile.json": "bcb7ce673f9207d973fd2e3804af069ea21bbd87ae2c6a96bc6da73972b5579c",
    "lessons.json": "fb8654f49d2969aeb4242ca20f55f8e22d3cbcbfeb084bb4fcd2f9f4b184398b",
    "tasks.json": "f00810c2a9fe43a1cafd051929b88c202b834b5ae12554d559c8ed6f55309ff5",
}
SHARDS = (geometry_probability, algebra_analysis, applied_finance)
ALL_FAMILIES = tuple(family for shard in SHARDS for family in shard.FAMILIES)
RUNTIME = tuple(family for family in ALL_FAMILIES if family.supports_runtime)
MAX_SEED = 2**32 - 1
RUNTIME_SEEDS = (0, MAX_SEED, *((index * 2654435761) & MAX_SEED for index in range(1, 999)))
SIGNED_FAMILIES = {
    "vector-scaled-difference": {-1, 0, 1}, "vector-dot-product": {-1, 0, 1},
    "vector-angle": {0, 1}, "combinatorial-subset": {0, 1},
    "radical-conjugates": {-1, 1}, "trigonometric-double-angle": {-1},
    "tangent-from-two-points": {-1, 1}, "integral-signed-areas": {-1, 0, 1},
    "line-reconstruction": {-1, 0, 1}, "parabola-vertex": {-1, 0, 1},
    "reciprocal-parameter": {-1, 1}, "line-intersection": {-1, 0, 1},
    "polyline-maximum": {-1, 0, 1},
}


@pytest.fixture(scope="module")
def original():
    return load_content(LEGACY_DIR)


@pytest.fixture(scope="module")
def artifacts():
    return build.build_course()


@pytest.fixture(scope="module")
def course(artifacts):
    return validate_content(*(json.loads(artifacts[name])
                              for name in ("profile.json", "lessons.json", "tasks.json")))


@pytest.fixture(scope="module")
def samples(course):
    # Two legacy families share stable IDs with new generators. Their original
    # five tasks are preserved separately from the ten generated snapshots.
    return {family.id: [task for task in course.tasks
                       if task.family_id == family.id and task.generation is not None]
            for family in ALL_FAMILIES}


def fraction(value):
    return Fraction(str(value).replace("−", "-").replace(",", "."))


def sign(value):
    return (value > 0) - (value < 0)


def visible_values(task):
    return tuple(fraction(value) for value in re.findall(r"[-−]?[0-9]+(?:[,.][0-9]+)?",
                                                        task.statement))


def table_values(task):
    return tuple(fraction(row[1]) for row in task.table.rows)


def points(task):
    return tuple((fraction(p.x), fraction(p.y)) for p in task.figure.lines[0].points)


def expected_answer(task):
    # Reuse the shards' public-input oracles, not their generator parameters or
    # the application checker. Importing their modules does not rerun their tests.
    raw = task.model_dump(mode="json")
    if task.slot <= 5:
        return geometry_checks._expected(task.family_id, task.statement, raw["table"])
    if task.slot <= 9:
        return algebra_checks.ORACLES[task.slot](raw)
    return applied_checks.oracle(raw)


def test_registry_is_the_ordered_union_with_exact_runtime_quota():
    assert isinstance(generators.FAMILIES, tuple)
    assert generators.FAMILIES == ALL_FAMILIES
    assert tuple(map(len, (shard.FAMILIES for shard in SHARDS))) == (29, 25, 24)
    assert len(generators.FAMILIES) == len(generators.FAMILY_BY_ID) == 78
    assert generators.RUNTIME_FAMILIES == RUNTIME
    assert len(RUNTIME) == 26
    assert Counter(family.slot for family in RUNTIME) == dict.fromkeys(range(1, 14), 2)
    with pytest.raises(TypeError):
        generators.FAMILY_BY_ID["unregistered"] = ALL_FAMILIES[0]


@pytest.mark.parametrize("seed", [-1, 2**32, True, False, 1.0, "0", None, Fraction(1)])
def test_registry_rejects_non_uint32_seeds_before_calling_a_family(seed, original):
    for call in (generators.generate, generators.reproduce):
        with pytest.raises(ValueError, match="unsigned 32-bit"):
            call(RUNTIME[0].id, seed, original.profile)


@pytest.mark.parametrize(
    "identifier", ["missing", "os.system", "../geometry_probability", [], None],
)
def test_registry_has_no_dynamic_dispatch(identifier, original):
    for call in (generators.generate, generators.reproduce):
        with pytest.raises(ValueError, match="registered"):
            call(identifier, 0, original.profile)


@pytest.mark.parametrize("family", ALL_FAMILIES, ids=lambda family: family.id)
def test_every_static_snapshot_is_reproducible_without_enabling_runtime(family, original):
    expected = Task.model_validate(family.generate(MAX_SEED, original.profile))
    assert generators.reproduce(family.id, MAX_SEED, original.profile) == expected
    if family.supports_runtime:
        assert generators.generate(family.id, MAX_SEED, original.profile) == expected
    else:
        with pytest.raises(ValueError, match="runtime"):
            generators.generate(family.id, MAX_SEED, original.profile)


@pytest.mark.parametrize("field,value", [
    ("profile_id", "wrong-profile"), ("family_id", "other-family"),
    ("slot_id", "other-slot"), ("slot", 2), ("skill_ids", ["plane-angles"]),
    ("id", "unrelated-instance"), ("review_status", "reviewed"),
    ("formula", r"\input{local-file}"), ("statement", "<script>alert(1)</script>"),
    ("generation", {"template_id": "other-family", "template_version": "1", "seed": 0}),
])
def test_registry_validates_generated_data_and_binding(monkeypatch, original, field, value):
    family = RUNTIME[0]

    def broken(seed, profile):
        return {**family.generate(seed, profile), field: value}

    monkeypatch.setattr(generators, "_RUNTIME_BY_ID", {family.id: replace(family, generate=broken)})
    with pytest.raises(ContentError):
        generators.generate(family.id, 0, original.profile)


def test_runtime_revalidates_mutated_profile_instances(original):
    profile = original.profile.model_copy(deep=True)
    profile.slots.append(profile.slots[0])
    with pytest.raises(ContentError, match="unique"):
        generators.generate(RUNTIME[0].id, 0, profile)
    profile = original.profile.model_copy(deep=True)
    profile.title = "<img src=x onerror=alert(1)>"
    with pytest.raises(ContentError):
        generators.generate(RUNTIME[0].id, 0, profile)


def test_original_package_bytes_are_the_fixed_regression_fixture(original):
    assert len(original.tasks) == 65 and len(original.lessons) == 13
    for name, expected in LEGACY_HASHES.items():
        assert hashlib.sha256((LEGACY_DIR / name).read_bytes()).hexdigest() == expected
        assert json.loads((LEGACY_DIR / name).read_bytes())


def test_materialized_artifacts_equal_a_fresh_validated_build(artifacts):
    assert set(artifacts) == set(build.ARTIFACT_NAMES)
    for name, expected in artifacts.items():
        assert (LEGACY_DIR / "course" / name).read_bytes() == expected, name
    for name, digest in LEGACY_HASHES.items():
        assert artifacts[f"legacy/{name}"] == (LEGACY_DIR / name).read_bytes()
        assert hashlib.sha256(artifacts[f"legacy/{name}"]).hexdigest() == digest


def test_course_is_a_complete_package_with_original_snapshots(artifacts, original, course):
    raw_tasks = json.loads(artifacts["tasks.json"])
    raw_lessons = json.loads(artifacts["lessons.json"])
    assert raw_tasks[:65] == json.loads((LEGACY_DIR / "tasks.json").read_bytes())
    assert raw_lessons[:13] == json.loads((LEGACY_DIR / "lessons.json").read_bytes())
    assert len(course.tasks) == 845 and len(course.lessons) == 99
    assert course.profile.id == original.profile.id
    assert course.profile.revision == original.profile.revision + ".course-1"
    assert course.profile.status == "draft"
    assert [slot.lesson_id for slot in course.profile.slots] == [
        lesson.id for lesson in original.lessons
    ]
    assert Counter(task.slot for task in course.tasks) == {
        1: 65, 2: 55, 3: 75, 4: 55, 5: 65, 6: 95, 7: 55,
        8: 55, 9: 65, 10: 55, 11: 65, 12: 65, 13: 75,
    }
    assert len({task.id for task in course.tasks}) == len(course.tasks)
    assert all(task.review_status == "demo" and task.source.reviewed_by is None
               for task in course.tasks)
    assert all(lesson.review_status == "demo" and lesson.reviewed_by is None
               for lesson in course.lessons)
    assert course.available_tasks(allow_demo_content=False) == ()


def test_all_87_exam_skills_have_lessons_and_independent_practice(course, samples):
    authored = {lesson.family_ids[0]: lesson for lesson in course.lessons
                if lesson.id.startswith("course-")}
    assert len(authored) == 78
    all_skills = {skill.id for slot in course.profile.slots for skill in slot.skills}
    assert len(all_skills) == 87
    covered = set()
    for family in ALL_FAMILIES:
        lesson = authored[family.id]
        assert lesson.family_ids == [family.id]
        assert set(lesson.skill_ids) == set(family.skill_ids)
        assert len(lesson.practice_task_ids) == len(set(lesson.practice_task_ids)) == 3
        family_tasks = {task.id: task for task in samples[family.id]}
        practice = [family_tasks[identifier] for identifier in lesson.practice_task_ids]
        assert len({task.answer for task in practice}) == 3
        assert all(task.slot == lesson.slot and task.slot_id == lesson.slot_id for task in practice)
        assert set().union(*(set(task.skill_ids) for task in practice)) == set(lesson.skill_ids)
        assert lesson.practice_task_ids != [f"course-{family.id}-{i}" for i in range(3)]
        if family.slot >= 10:
            example = applied_checks.example_task(lesson.example.model_dump(), family)
            for task in practice:
                assert applied_checks.inputs(example) != applied_checks.inputs(task.model_dump())
        elif family.slot >= 6:
            worked = algebra_checks.visible_numbers(lesson.example.statement)
            for task in practice:
                table = task.table.model_dump() if task.table else None
                assert algebra_checks.visible_numbers(task.statement, table) != worked
        else:
            worked = geometry_checks._numbers(lesson.example.statement)
            assert all(visible_values(task) != worked for task in practice)
        covered.update(lesson.skill_ids)
    assert covered == all_skills


def test_foundations_are_eight_advisory_slot_zero_lessons(course):
    foundations = [lesson for lesson in course.lessons if lesson.kind == "foundation"]
    assert len(foundations) == 8
    assert {lesson.id for lesson in foundations} == {
        "base-fractions", "base-negative-numbers", "base-percentages", "base-powers",
        "base-roots", "base-algebra-expressions", "base-coordinates", "base-linear-equations",
    }
    stable_slots = {slot.id for slot in course.profile.slots}
    foundation_ids = {lesson.id for lesson in foundations}
    for lesson in foundations:
        assert lesson.slot == 0 and lesson.slot_id is None
        assert lesson.related_slot_ids and set(lesson.related_slot_ids) <= stable_slots
        assert set(lesson.prerequisite_ids) <= foundation_ids
        assert lesson.family_ids == lesson.practice_task_ids == []
        assert all(skill.startswith("foundation-") for skill in lesson.skill_ids)
    for lesson in course.lessons:
        if lesson.id.startswith("course-"):
            expected = {base.id for base in foundations if lesson.slot_id in base.related_slot_ids}
            assert expected <= set(lesson.prerequisite_ids)


def test_materialized_lessons_use_current_shard_text(course):
    by_id = {lesson.id: lesson for lesson in course.lessons}
    for shard in SHARDS:
        for raw in shard.build_lessons(course.profile):
            materialized = by_id[raw["id"]].model_dump(mode="json")
            for field in ("sections", "example", "takeaway", "family_ids"):
                assert materialized[field] == raw[field], (raw["id"], field)


@pytest.mark.parametrize("family", ALL_FAMILIES, ids=lambda family: family.id)
def test_stratified_pool_covers_all_32_bits_and_both_boundaries(family):
    seeds = build.candidate_seeds(family.id)
    assert seeds == build.candidate_seeds(family.id)
    assert len(seeds) == len(set(seeds)) >= 512
    assert all(type(seed) is int and 0 <= seed <= MAX_SEED for seed in seeds)
    assert {0, MAX_SEED} <= set(seeds)
    assert {seed // (2**32 // 512) for seed in seeds} == set(range(512))


def test_known_sign_and_slow_parameter_branches_are_in_the_candidate_pool():
    for identifier, required in {
        "tangent-from-two-points": {17}, "integral-signed-areas": {51, 68},
        "vector-scaled-difference": {817, 855}, "vector-dot-product": {74, 75},
        "right-triangle-area": {200, 400, 600, 800}, "right-prism-volume": {7387},
        "resistance-temperature": {23, 276}, "river-speed-system": {23, 46, 69},
        "reciprocal-parameter": {23, 115},
    }.items():
        assert required <= set(build.candidate_seeds(identifier))


@pytest.mark.parametrize("family", ALL_FAMILIES, ids=lambda family: family.id)
def test_static_samples_maximize_answers_and_have_real_unique_conditions(family, course, samples):
    chosen = samples[family.id]
    assert len(chosen) == 10
    assert len({(task.statement, tuple(tuple(row) for row in task.table.rows) if task.table else ())
                for task in chosen}) == 10
    available = {fraction(family.generate(seed, course.profile)["answer"])
                 for seed in build.candidate_seeds(family.id)}
    assert len({fraction(task.answer) for task in chosen}) == min(10, len(available))
    assert {sign(fraction(task.answer)) for task in chosen} == SIGNED_FAMILIES.get(family.id, {1})
    for task in chosen:
        assert task.generation is not None
        assert task.generation.seed in build.candidate_seeds(family.id)
        assert fraction(task.answer) == expected_answer(task), task.id
        assert generators.reproduce(family.id, task.generation.seed, course.profile) == task


def test_normalized_geometry_models_vary_beyond_scale_and_translation(samples):
    assert {visible_values(task)[0] / visible_values(task)[1]
            for task in samples["right-triangle-area"]} == {
        Fraction(3, 5), Fraction(5, 13), Fraction(8, 17), Fraction(7, 25), Fraction(20, 29),
    }
    displacement = [visible_values(task) for task in samples["displacement-length"]]
    assert {abs(bx - ax) / (by - ay) for ax, ay, bx, by in displacement} == {
        Fraction(3, 4), Fraction(5, 12), Fraction(8, 15), Fraction(7, 24), Fraction(20, 21),
    }
    assert {sign(bx - ax) for ax, _, bx, _ in displacement} == {-1, 1}
    prisms = [visible_values(task) for task in samples["right-prism-volume"]]
    assert len({height for _, _, height in prisms}) == 10
    assert len({a / b for a, b, _ in prisms}) == 10
    trapezoids = [visible_values(task) for task in samples["trapezoid-area"]]
    assert len({b - a for a, b, _ in trapezoids}) == 10
    assert len({height for _, _, height in trapezoids}) == 10
    assert len({visible_values(task)[1] / visible_values(task)[0]
                for task in samples["similar-triangles-area"]}) == 7


@pytest.mark.parametrize("family_id", [
    "distribution-weighted-mean", "distribution-weighted-variance", "distribution-step-cdf",
])
def test_distribution_selection_changes_gaps_and_weights_not_just_origin(family_id, samples):
    rows = [tuple((fraction(x), fraction(p)) for x, p in task.table.rows)
            for task in samples[family_id]]
    centered = {tuple((x - distribution[0][0], p) for x, p in distribution)
                for distribution in rows}
    assert len(centered) == 10
    assert len({tuple(p for _, p in distribution) for distribution in rows}) == 6
    assert len({(b[0] - a[0], c[0] - b[0]) for a, b, c in rows}) >= 5


def test_small_answer_domains_are_fully_covered_without_inventing_extra_answers(samples):
    expected = {
        "distribution-two-point-deviation": {Fraction(i) for i in (1, 2, 3, 4)},
        "distribution-step-cdf": {Fraction(i, 10) for i in (5, 6, 7, 8)},
        "derivative-positive-length": {Fraction(i) for i in (6, 9, 12, 15, 18)},
        "river-speed-system": {Fraction(i) for i in (2, 3, 4, 5)},
        "logarithm-difference": {Fraction(i) for i in (2, 3, 4)},
        "vector-angle": {Fraction(i) for i in (0, 45, 90, 135, 180)},
    }
    for identifier, answers in expected.items():
        assert {fraction(task.answer) for task in samples[identifier]} == answers
    assert {fraction(task.table.rows[1][0]) - fraction(task.table.rows[0][0])
            for task in samples["distribution-two-point-deviation"]} == {2, 4, 6, 8}


def test_calculus_models_vary_after_removing_horizontal_and_vertical_translations(samples):
    graphs = [points(task) for task in samples["piecewise-function-value"]]
    normalized = {tuple((x - graph[0][0], y - graph[0][1]) for x, y in graph)
                  for graph in graphs}
    assert len(normalized) == 10
    assert {graph[1][0] - graph[0][0] for graph in graphs} == {4, 6, 8, 10, 12}
    assert {graph[1][1] - graph[0][1] for graph in graphs} == {2, 4, 6, 8, 10}
    derivatives = [points(task) for task in samples["derivative-positive-length"]]
    assert {graph[1][0] - graph[0][0] for graph in derivatives} == {4, 6, 8, 10, 12}
    assert {graph[1][1] for graph in derivatives} == set(range(1, 9))
    assert {(p[1][1] - p[0][1]) / (p[1][0] - p[0][0])
            for p in map(points, samples["derivative-turning-point"])} == set(range(1, 9))


def test_applied_models_cover_hidden_slow_parameters_and_graph_branches(samples):
    resistance = [table_values(task) for task in samples["resistance-temperature"]]
    assert len({measured / base for base, _, _, measured in resistance}) == 10
    river = [table_values(task) for task in samples["river-speed-system"]]
    assert {down_hours for _, down_hours, _, _ in river} == {2, 3, 4}
    assert {up_hours for _, _, _, up_hours in river} == {3, 4}
    assert {table_values(task)[0] for task in samples["reciprocal-parameter"]} == {1, 2, 3, 4, 5}
    lines = [table_values(task) for task in samples["line-reconstruction"]]
    assert {(yb - ya) / (xb - xa) for xa, ya, xb, yb, _ in lines} == {
        Fraction(i, 2) for i in (-7, -5, -3, -1, 1, 3, 5, 7)
    }
    parabolas = [table_values(task) for task in samples["parabola-vertex"]]
    assert {(py - k) / (px - h)**2 for h, k, px, py, _ in parabolas} == {-3, -2, -1, 1, 2, 3}
    assert {table_values(task)[1] / table_values(task)[0]
            for task in samples["exponential-data"]} == {Fraction(1, 2), 2, 3, 4}
    locations = set()
    for task in samples["polyline-maximum"]:
        values = table_values(task)
        at_right = values[5] + (values[7] - values[5]) / 3
        locations.add(sign(values[3] - at_right))
    assert locations == {-1, 0, 1}
    assert {table_values(task)[2] for task in samples["equal-principal-credit"]} == set(range(3, 9))


def test_sign_branches_are_also_in_lesson_practice(course):
    tasks = {task.id: task for task in course.tasks}
    for lesson in course.lessons:
        if lesson.id.startswith("course-"):
            family = lesson.family_ids[0]
            observed = {sign(fraction(tasks[identifier].answer))
                        for identifier in lesson.practice_task_ids}
            assert observed == SIGNED_FAMILIES.get(family, {1}), family


def test_theorem_choice_materialization_preserves_deferred_help(course):
    tasks = [task for task in course.tasks
             if task.generation and "plane-theorem-choice" in task.skill_ids]
    assert len(tasks) == 50
    for task in tasks:
        public = public_task(task).model_dump()
        assert public["formula"] is None
        assert not {"answer", "solution", "hints", "source", "generation"} & public.keys()
        assert len(task.hints) == 3 and task.solution


def test_manifest_reports_actual_selected_values_and_blank_review_worksheet(artifacts, samples):
    manifest = json.loads(artifacts["manifest.json"])
    assert manifest["legacy_sha256"] == LEGACY_HASHES
    assert manifest["new_task_count"] == 780 and manifest["runtime_family_count"] == 26
    assert manifest["review_status"] == "demo" and manifest["reviewed_by"] is None
    assert len(manifest["families"]) == 78
    worksheet = artifacts["review-worksheet.md"].decode("utf-8")
    for record in manifest["families"]:
        tasks = samples[record["family_id"]]
        assert record["seeds"] == [task.generation.seed for task in tasks]
        assert record["answers"] == [task.answer for task in tasks]
        assert record["answer_count"] == len({task.answer for task in tasks})
        assert record["signs"] == sorted({sign(fraction(task.answer)) for task in tasks})
        assert record["signs"] == record["candidate_signs"]
        for task in tasks:
            assert f"| `{task.id}` | {task.generation.seed} | | | |" in worksheet
    assert worksheet.count("| | | |") == 780 + 8


@pytest.mark.parametrize("family", RUNTIME, ids=lambda family: family.id)
def test_runtime_registry_on_1000_spread_seeds_with_public_input_oracles(family, original):
    assert len(RUNTIME_SEEDS) == len(set(RUNTIME_SEEDS)) == 1000
    assert {0, MAX_SEED} <= set(RUNTIME_SEEDS)
    for seed in RUNTIME_SEEDS:
        task = generators.generate(family.id, seed, original.profile)
        assert task.generation.seed == seed and task.generation.template_id == family.id
        assert fraction(task.answer) == expected_answer(task), (family.id, seed)
        assert generators.generate(family.id, seed, original.profile) == task, (family.id, seed)


def test_different_seeds_can_represent_the_same_mathematical_instance(original):
    first = generators.generate("complement-quality", 0, original.profile)
    repeated = generators.generate("complement-quality", 999, original.profile)
    assert first.id != repeated.id
    assert first.statement == repeated.statement and first.answer == repeated.answer


@pytest.fixture
def write_artifacts():
    # Exercise filesystem boundaries independently of mathematical assembly.
    # The full, real build is checked by the materialization tests above.
    snapshots = {name: (LEGACY_DIR / name).read_bytes() for name in LEGACY_HASHES}
    return {
        **snapshots,
        **{f"legacy/{name}": value for name, value in snapshots.items()},
        "manifest.json": b"{}\n",
        "review-worksheet.md": b"# Unfilled test worksheet\n",
    }


@pytest.fixture
def isolated_output(monkeypatch, tmp_path, write_artifacts):
    legacy = tmp_path / "content"
    legacy.mkdir()
    for name in LEGACY_HASHES:
        (legacy / name).write_bytes(write_artifacts[f"legacy/{name}"])
    monkeypatch.setattr(build, "LEGACY_DIR", legacy)
    monkeypatch.setattr(build, "COURSE_DIR", legacy / "course")
    monkeypatch.setattr(build, "build_course", lambda: dict(write_artifacts))
    return legacy


def test_writer_only_changes_generated_artifacts_and_check_is_read_only(
    isolated_output, write_artifacts,
):
    course_dir = isolated_output / "course"
    course_dir.mkdir()
    (course_dir / "reviewer-notes.txt").write_text("Unrelated local notes", encoding="utf-8")
    assert set(build.check_course()) == set(build.ARTIFACT_NAMES)
    assert not (course_dir / "profile.json").exists()
    assert len(build.write_course()) == 8
    assert build.check_course() == ()
    for name, expected in write_artifacts.items():
        assert (course_dir / name).read_bytes() == expected
    for name, expected in LEGACY_HASHES.items():
        assert hashlib.sha256((isolated_output / name).read_bytes()).hexdigest() == expected
    assert (course_dir / "reviewer-notes.txt").read_text(encoding="utf-8") == (
        "Unrelated local notes"
    )
    (course_dir / "tasks.json").write_bytes(b"[]\n")
    assert build.check_course() == ("tasks.json",)
    assert (course_dir / "tasks.json").read_bytes() == b"[]\n"


def test_writer_refuses_legacy_output_path_before_writing(isolated_output, monkeypatch):
    monkeypatch.setattr(build, "COURSE_DIR", isolated_output)
    with pytest.raises(ContentError, match="content/course"):
        build.write_course()
    for name, digest in LEGACY_HASHES.items():
        assert hashlib.sha256((isolated_output / name).read_bytes()).hexdigest() == digest


def test_writer_rejects_a_hard_link_to_a_legacy_snapshot_before_any_write(isolated_output):
    course_dir = isolated_output / "course"
    course_dir.mkdir()
    os.link(isolated_output / "tasks.json", course_dir / "tasks.json")
    with pytest.raises(ContentError, match="unshared"):
        build.write_course()
    assert not (course_dir / "profile.json").exists()
    assert hashlib.sha256((isolated_output / "tasks.json").read_bytes()).hexdigest() == (
        LEGACY_HASHES["tasks.json"]
    )


def test_writer_rejects_any_extra_artifact_path(isolated_output, monkeypatch, write_artifacts):
    monkeypatch.setattr(build, "build_course", lambda: {**write_artifacts, "../tasks.json": b"[]"})
    with pytest.raises(ContentError, match="fixed generated"):
        build.write_course()
    assert not (isolated_output / "course").exists()


def test_writer_stops_before_any_write_when_assembly_fails(isolated_output, monkeypatch):
    def invalid_build():
        raise ContentError("Incomplete or invalid course")

    monkeypatch.setattr(build, "build_course", invalid_build)
    with pytest.raises(ContentError, match="Incomplete or invalid course"):
        build.write_course()
    assert not (isolated_output / "course").exists()


@pytest.mark.parametrize("args", [[], ["--write", "--check"], ["--write", "--output", "content"]])
def test_cli_requires_an_explicit_mode_and_has_no_arbitrary_output_option(args, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["app.generators.build", *args])
    with pytest.raises(SystemExit) as error:
        build.main()
    assert error.value.code == 2
