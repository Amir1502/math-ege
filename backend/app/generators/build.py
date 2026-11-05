"""Deterministic course assembly. CLI writes only its fixed generated artifacts."""

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from app.content import ContentError, Task, validate_content
from app.generators import (
    FAMILIES,
    FAMILY_BY_ID,
    MAX_SEED,
    RUNTIME_FAMILIES,
    _data_only,
    _generate,
    _validated_profile,
    algebra_analysis,
    applied_finance,
    base,
    foundations,
    geometry_probability,
)
from app.generators.base import Family
from app.schemas import Lesson, ProfileSource

LEGACY_DIR = Path(__file__).resolve().parents[2] / "content"
COURSE_DIR = LEGACY_DIR / "course"
SAMPLES_PER_FAMILY = 10
SEED_STRATA = 512
BUILD_VERSION = "stratified-v1"
ARTIFACT_NAMES = (
    "profile.json", "lessons.json", "tasks.json",
    "legacy/profile.json", "legacy/lessons.json", "legacy/tasks.json",
    "review-worksheet.md", "manifest.json",
)
_SHARDS = (geometry_probability, algebra_analysis, applied_finance)
_SOURCE_MODULES = (base, *_SHARDS, foundations)
_NUMBER = re.compile(r"[-−]?[0-9]+(?:[,.][0-9]+)?")
# Rare signs and known mixed-radix transitions supplement (not replace) the
# full-domain strata. They are candidates, not mandatory materialized seeds.
_BRANCH_SEEDS = {
    "right-triangle-area": (200, 400, 600, 800),
    "displacement-length": (100, 200, 300, 400, 500),
    "vector-scaled-difference": (817, 855),
    "vector-dot-product": (74, 75, 4898),
    "right-prism-volume": (7387,),
    "trapezoid-area": (97, 2813),
    "distribution-weighted-mean": (40, 200, 1000, 3000),
    "distribution-weighted-variance": (40, 200, 1000, 3000),
    "distribution-two-point-deviation": (40, 80, 120),
    "distribution-step-cdf": (1000, 2000, 3000, 4000, 5000),
    "piecewise-function-value": (30, 150, 1200),
    "derivative-positive-length": (20, 100),
    "tangent-from-two-points": (17,),
    "integral-signed-areas": (51, 68),
    "radical-conjugates": (80,),
    "resistance-temperature": (23, 276),
    "river-speed-system": (23, 46, 69),
    "line-reconstruction": (7, 8, 92),
    "parabola-vertex": (2, 3, 69),
    "reciprocal-parameter": (23, 115),
    "exponential-data": (69,),
    "line-intersection": (5, 6),
    "polyline-maximum": (5, 6, 115, 184),
}


def candidate_seeds(template_id: str) -> tuple[int, ...]:
    """One SHA-256-jittered seed in every equal uint32 stratum, plus anchors."""
    if not isinstance(template_id, str) or template_id not in FAMILY_BY_ID:
        raise ValueError("Template is not registered for static reproduction")
    width = 2**32 // SEED_STRATA
    seeds = [0, MAX_SEED, *range(1, 10), *_BRANCH_SEEDS.get(template_id, ())]
    for stratum in range(SEED_STRATA):
        key = f"{BUILD_VERSION}:{template_id}:{stratum}".encode("ascii")
        jitter = int.from_bytes(hashlib.sha256(key).digest()[:4], "big") % width
        seeds.append(stratum * width + jitter)
    return tuple(dict.fromkeys(seeds))


def _fraction(value: str | int | float) -> Fraction:
    return Fraction(str(value).replace("−", "-").replace(",", "."))


def _numbers(text: str) -> tuple[Fraction, ...]:
    return tuple(_fraction(value) for value in _NUMBER.findall(text))


def _sign(value: Fraction) -> int:
    return (value > 0) - (value < 0)


def _json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")


def _condition(task: Task) -> str:
    # All current shards publish their complete numerical inputs in text/tables.
    # Identity, seed, answer, help and decorative figure layout are not diversity.
    return json.dumps([
        " ".join(task.statement.split()), " ".join((task.formula or "").split()),
        task.table.model_dump() if task.table else None,
    ], ensure_ascii=False, sort_keys=True)


def _model_features(task: Task) -> dict[str, str]:
    """Auditable mathematical features from visible inputs, never from seed bits.

    Remove translations/scales where these conceal repeated models. A family
    with one intrinsic shape can legitimately have one normalized signature.
    ``branch.*`` labels are categorical alternatives prioritized before other
    parameter coverage. These signatures are not additional teaching families.
    """
    family = task.family_id
    n = _numbers(task.statement)
    v = [_fraction(row[1]) for row in task.table.rows] if task.table and task.slot >= 10 else []
    features: dict[str, Any] = {}
    match family:
        case "right-triangle-area":
            features = {"branch.leg_hypotenuse_ratio": n[0] / n[1]}
        case "trapezoid-area":
            a, b, height = n
            features = {"height": height, "base_difference": b - a}
        case "similar-triangles-area":
            ab, ad, _ = n
            features = {"linear_ratio": ad / ab}
        case "intersecting-chords":
            ae, eb, ce = n
            features = {"chord_ratio": ae / ce, "other_segment_ratio": eb / ce}
        case "displacement-length":
            ax, ay, bx, by = n
            features = {"branch.direction_x": _sign(bx - ax),
                        "branch.leg_ratio": abs(bx - ax) / (by - ay)}
        case "vector-sum-length":
            ax, ay, bx, by = n
            features = {"first_x_fraction": ax / (ax + bx),
                        "first_y_fraction": ay / (ay + by)}
        case "vector-scaled-difference":
            _, ay, _, _, factor = n
            features = {"multiplier": factor, "first_y_sign": _sign(ay)}
        case "vector-dot-product":
            ax, ay, bx, by = n
            features = {"coordinate_product_signs": (_sign(ax * bx), _sign(ay * by))}
        case "right-prism-volume":
            a, b, height = n
            features = {"height": height, "base_ratio": a / b}
        case "rectangular-box-surface":
            a, b, c = sorted(n)
            features = {"middle_ratio": b / a, "long_ratio": c / a}
        case "square-pyramid-volume" | "cylinder-volume-coefficient" | "cone-surface-coefficient":
            features = {"height_base_ratio": n[1] / n[0]}
        case "solid-similarity-volume":
            features = {"linear_ratio": n[1] / n[0]}
        case "urn-favorable-count":
            features = {"population": sum(n)}
        case "integer-event-boundaries":
            features = {"population": n[1]}
        case "coin-pattern-enumeration":
            features = {"tosses": n[0], "heads": n[1]}
        case "independent-at-least-one":
            features = {"first_probability": n[0], "second_probability": n[1]}
        case "conditional-without-replacement":
            features = {"population": n[0]}
        case "overlapping-event-union":
            _, a, b, both = n
            features = {"only_first": a - both, "only_second": b - both}
        case "total-probability-routing":
            assert task.table is not None
            rows = task.table.rows
            features = {"first_weight": rows[0][1], "first_defect": rows[0][2],
                        "second_defect": rows[1][2]}
        case "event-tree-exactly-one":
            features = {"after_success": n[1], "after_failure": n[2]}
        case ("distribution-weighted-mean" | "distribution-weighted-variance"
              | "distribution-step-cdf"):
            assert task.table is not None
            rows = [(_fraction(x), _fraction(p)) for x, p in task.table.rows]
            features = {"support_gaps": (rows[1][0] - rows[0][0], rows[2][0] - rows[1][0]),
                        "probability_weights": tuple(p for _, p in rows)}
        case "distribution-two-point-deviation":
            assert task.table is not None
            features = {"support_span": _fraction(task.table.rows[1][0])
                        - _fraction(task.table.rows[0][0])}
        case "distribution-uniform-interval":
            left, right, start, end = n
            features = {"relative_start": (start - left) / (right - left),
                        "relative_end": (end - left) / (right - left)}
        case "distribution-exponential-survival":
            features = {"rate": n[0]}
        case "distribution-normal-symmetry":
            features = {"distance_from_mean": n[0] - n[1]}
        case "exponential-common-base":
            features = {"base": n[0], "right_exponent": n[-1]}
        case "logarithmic-product-domain":
            features = {"base": n[0]}
        case "absolute-value-selected-root":
            features = {"distance_from_center": n[1]}
        case "power-product-quotient":
            features = {"negative_exponent": n[3]}
        case "radical-conjugates":
            features = {"subtracted_square_root": n[1]}
        case "rational-removable-factor":
            features = {"distance_from_excluded_point": n[-1] - n[-2]}
        case "logarithm-difference":
            features = {"base": n[0]}
        case "trigonometric-double-angle":
            match = re.search(r"sin α = ([0-9]+)/([0-9]+)", task.statement)
            if match is None:
                raise ContentError("Missing visible trigonometric ratio")
            features = {"branch.sine_ratio": _fraction(match[1]) / _fraction(match[2])}
        case ("piecewise-function-value" | "derivative-positive-length"
              | "derivative-turning-point" | "integral-signed-areas"):
            assert task.figure is not None
            points = [(_fraction(p.x), _fraction(p.y)) for p in task.figure.lines[0].points]
            (x0, y0), (x1, y1) = points[:2]
            if family == "piecewise-function-value":
                features = {"segment_width": x1 - x0, "segment_rise": y1 - y0}
            elif family == "derivative-positive-length":
                features = {"segment_width": x1 - x0, "amplitude": y1}
            elif family == "derivative-turning-point":
                features = {"derivative_slope": (y1 - y0) / (x1 - x0)}
            else:
                features = {"positive_negative_height_ratio": points[2][1] / -y0,
                            "segment_width": x1 - x0}
        case "antiderivative-initial-value":
            features = {"linear_coefficient": n[1], "initial_value": n[3], "target": n[4]}
        case "heat-balance":
            features = {"temperature_rise": v[3] - v[2]}
        case "pressure-force":
            features = {"area": v[1]}
        case "tank-net-flow":
            features = {"net_flow": v[1] - v[2], "outflow": v[2]}
        case "resistance-temperature":
            features = {"relative_resistance": v[3] / v[0]}
        case "stopping-distance":
            features = {"reaction_time": v[0], "deceleration": v[1]}
        case "catch-up-motion":
            features = {"speed_difference": v[1] - v[0], "delay_minutes": v[2]}
        case "river-speed-system":
            features = {"current_speed": (v[0] / v[1] - v[2] / v[3]) / 2,
                        "downstream_hours": v[1], "upstream_hours": v[3]}
        case "joint-pumps":
            features = {"individual_time_ratio": v[0] / v[1]}
        case "production-deadline":
            features = {"saved_days": v[2], "increase_per_saved_day": v[1] / v[2]}
        case "solution-dilution":
            features = {"concentration_ratio": v[1] / v[2], "target_concentration": v[2]}
        case "alloy-balance":
            features = {"low_concentration": v[1], "high_concentration": v[2],
                        "relative_target": (v[3] - v[1]) / (v[2] - v[1])}
        case "line-reconstruction":
            slope = (v[3] - v[1]) / (v[2] - v[0])
            features = {"branch.slope_sign": _sign(slope), "slope": slope}
        case "parabola-vertex":
            curvature = (v[3] - v[1]) / (v[2] - v[0]) ** 2
            features = {"branch.opening": _sign(curvature), "curvature": curvature}
        case "reciprocal-parameter":
            features = {"sample_abscissa": v[0]}
        case "exponential-data":
            ratio = v[1] / v[0]
            features = {"branch.growth": _sign(ratio - 1), "base": ratio}
        case "line-intersection":
            features = {"first_slope": v[1] - v[0], "second_slope": v[3] - v[2]}
        case "polyline-maximum":
            at_right = v[5] + (v[7] - v[5]) * (v[9] - v[4]) / (v[6] - v[4])
            location = "vertex" if v[3] > at_right else "right" if at_right > v[3] else "tie"
            features = {"branch.maximum_location": location,
                        "peak_rise": v[3] - v[1], "last_rise": v[7] - v[1]}
        case "successive-percentages":
            features = {"increase_percent": v[1], "discount_percent": v[2]}
        case ("capitalized-deposit" | "paid-interest-deposit"
              | "equal-principal-credit" | "equal-payment-credit"):
            features = {"rate_percent": v[1], "periods": v[2]}
        case "family-budget":
            features = {"reserve_percent": v[4]}
        case "tariff-threshold":
            features = {"unit_price_difference": v[0] - v[2]}
    return {name: ":".join(map(str, value)) if isinstance(value, tuple) else str(value)
            for name, value in features.items()}


@dataclass(frozen=True)
class _Candidate:
    task: Task
    condition: str
    answer: Fraction
    sign: int
    features: frozenset[tuple[str, str]]

    @property
    def branches(self) -> frozenset[tuple[str, str]]:
        return frozenset(pair for pair in self.features if pair[0].startswith("branch."))


def _select(candidates: list[_Candidate], count: int) -> list[_Candidate]:
    answers: set[Fraction] = set()
    signs: set[int] = set()
    features: set[tuple[str, str]] = set()
    models: set[frozenset[tuple[str, str]]] = set()
    strata: set[int] = set()
    remaining = list(candidates)
    selected = []
    for _ in range(count):
        if not remaining:
            raise ContentError("Not enough independent visible conditions in a family")

        def priority(candidate: _Candidate) -> tuple:
            assert candidate.task.generation is not None
            return (
                candidate.answer not in answers,
                candidate.sign not in signs,
                len(candidate.branches - features),
                len(candidate.features - features),
                candidate.features not in models,
                candidate.task.generation.seed // (2**32 // 16) not in strata,
            )

        # max keeps the first candidate on a tie: anchors then ordered strata.
        chosen = max(remaining, key=priority)
        selected.append(chosen)
        remaining.remove(chosen)
        answers.add(chosen.answer)
        signs.add(chosen.sign)
        features.update(chosen.features)
        models.add(chosen.features)
        assert chosen.task.generation is not None
        strata.add(chosen.task.generation.seed // (2**32 // 16))
    return selected


def _coverage(candidates: list[_Candidate]) -> dict[str, list[str]]:
    fields: dict[str, set[str]] = {}
    for candidate in candidates:
        for name, value in candidate.features:
            fields.setdefault(name, set()).add(value)
    return {name: sorted(values) for name, values in sorted(fields.items())}


def _family_samples(family: Family, profile: ProfileSource) -> tuple[list[_Candidate], dict]:
    seeds = candidate_seeds(family.id)
    unique: dict[str, _Candidate] = {}
    for seed in seeds:
        task = _generate(family, seed, profile)
        answer = _fraction(task.answer)
        candidate = _Candidate(task, _condition(task), answer, _sign(answer),
                               frozenset(_model_features(task).items()))
        previous = unique.setdefault(candidate.condition, candidate)
        if previous.answer != answer:
            raise ContentError("Equal visible conditions have inconsistent expected answers")
    candidates = list(unique.values())
    selected = _select(candidates, SAMPLES_PER_FAMILY)
    if len({item.answer for item in selected}) != min(10, len({c.answer for c in candidates})):
        raise ContentError("Static selection failed to maximize distinct exact answers")
    if {item.sign for item in selected} != {item.sign for item in candidates}:
        raise ContentError("Static selection omitted an available answer sign")
    return selected, {
        "family_id": family.id, "slot": family.slot, "skill_ids": list(family.skill_ids),
        "supports_runtime": family.supports_runtime, "lesson_id": f"course-{family.id}",
        "candidate_seed_count": len(seeds), "candidate_condition_count": len(candidates),
        "candidate_answer_count": len({c.answer for c in candidates}),
        "candidate_signs": sorted({c.sign for c in candidates}),
        "seeds": [c.task.generation.seed for c in selected if c.task.generation],
        "answers": [c.task.answer for c in selected],
        "answer_count": len({c.answer for c in selected}),
        "signs": sorted({c.sign for c in selected}),
        "normalized_model_count": len({c.features for c in selected}),
        "candidate_model_count": len({c.features for c in candidates}),
        "model_coverage": _coverage(selected),
        "candidate_model_value_counts": {name: len(values)
                                         for name, values in _coverage(candidates).items()},
    }


def _practice(samples: list[_Candidate], lesson: dict) -> list[str]:
    examples = [lesson["example"], *lesson.get("examples", [])]
    example_numbers = [Counter(_numbers(example["statement"])) for example in examples]
    independent = []
    for sample in samples:
        text = sample.task.statement
        if sample.task.table:
            text += " " + " ".join(cell for row in sample.task.table.rows for cell in row)
        if Counter(_numbers(text)) not in example_numbers:
            independent.append(sample)
    return [candidate.task.id for candidate in _select(independent, 3)]


def _source_digests() -> dict[str, str]:
    return {
        Path(module.__file__).name: hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
        for module in _SOURCE_MODULES
    }


def _worksheet(manifest: dict) -> bytes:
    lines = [
        "# Course review worksheet — unfilled", "",
        "Generated by `python -m app.generators.build --write`.",
        "Copy this worksheet before filling it.",
        "All records are demo material. No human review is asserted or recorded by this build.",
        "Record an independent calculation, domain/unit checks, explanation/figure checks,",
        "reviewer identity and date for each sample.",
        "Review the associated lesson and skill mapping.",
        "Automated selection and arithmetic tests do not complete any of these cells.", "",
    ]
    for family in manifest["families"]:
        lines.extend([
            f"## {family['family_id']}", "",
            f"Slot: {family['slot']}; runtime: {str(family['supports_runtime']).lower()}; "
            f"lesson: `{family['lesson_id']}`.",
            "Practice: " + ", ".join(f"`{item}`" for item in family["practice_task_ids"]),
            "", "Lesson / model restrictions / skill coverage review: __________", "",
            "| Task ID | Seed | Independent calculation / checks | Reviewer / date | Decision |",
            "| --- | ---: | --- | --- | --- |",
        ])
        for seed in family["seeds"]:
            lines.append(f"| `course-{family['family_id']}-{seed}` | {seed} | | | |")
        lines.append("")
    lines.extend(["## Foundations", "", "Review examples, self-checks and advisory links.",
                  "", "| Lesson | Checks | Reviewer / date | Decision |",
                  "| --- | --- | --- | --- |"])
    lines.extend(f"| `{identifier}` | | | |" for identifier in manifest["foundation_lesson_ids"])
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_course() -> dict[str, bytes]:
    """Build all eight artifacts in memory from the explicit legacy source path.

    Returned relative names and UTF-8 bytes are deterministic. No application
    settings, repositories, databases, clock or global random state are used.
    """
    source_digests = _source_digests()
    snapshots = {name: (LEGACY_DIR / name).read_bytes()
                 for name in ("profile.json", "lessons.json", "tasks.json")}
    profile_data, old_lessons, old_tasks = (json.loads(snapshots[name]) for name in snapshots)
    for record in (profile_data, *old_lessons, *old_tasks):
        _data_only(record)
    original = validate_content(profile_data, old_lessons, old_tasks)
    if len(original.tasks) != 65 or len(original.lessons) != 13:
        raise ContentError("Course assembly requires the original 65-task, 13-lesson fixture")
    profile_data["revision"] += ".course-1"
    profile_data["verification_note"] += (
        " Расширение курса — авторский демонстрационный пакет; "
        "независимая предметная рецензия не выполнена."
    )
    profile = _validated_profile(ProfileSource.model_validate(profile_data))
    foundation_lessons = foundations.build_lessons(profile)
    authored = [lesson for shard in _SHARDS for lesson in shard.build_lessons(profile)]
    lesson_by_id = {lesson["id"]: lesson for lesson in authored}
    if len(authored) != 78 or set(lesson_by_id) != {f"course-{family.id}" for family in FAMILIES}:
        raise ContentError("Every registered family needs exactly one authored lesson")
    if len(foundation_lessons) != 8:
        raise ContentError("The course requires eight foundation lessons")
    tasks, lessons, reports = list(old_tasks), list(old_lessons), []
    for family in FAMILIES:
        samples, report = _family_samples(family, profile)
        lesson = lesson_by_id[f"course-{family.id}"]
        slot = next(slot for slot in profile.slots if slot.number == family.slot)
        lesson["slot_id"] = slot.id
        lesson["practice_task_ids"] = _practice(samples, lesson)
        lesson["prerequisite_ids"] = list(dict.fromkeys([
            *lesson.get("prerequisite_ids", []),
            *(item["id"] for item in foundation_lessons if slot.id in item["related_slot_ids"]),
        ]))
        if lesson.get("review_status", "demo") != "demo" or lesson.get("reviewed_by") is not None:
            raise ContentError("Authored course lessons must not claim independent review")
        _data_only(lesson)
        lessons.append(Lesson.model_validate(lesson).model_dump(mode="json"))
        tasks.extend(sample.task.model_dump(mode="json") for sample in samples)
        report["practice_task_ids"] = lesson["practice_task_ids"]
        reports.append(report)
    for lesson in foundation_lessons:
        if lesson.get("review_status", "demo") != "demo" or lesson.get("reviewed_by") is not None:
            raise ContentError("Foundation lessons must not claim independent review")
        _data_only(lesson)
        lessons.append(Lesson.model_validate(lesson).model_dump(mode="json"))
    bundle = validate_content(profile_data, lessons, tasks)
    for slot in bundle.profile.slots:
        covered = {skill for family in FAMILIES if family.slot == slot.number
                   for skill in family.skill_ids}
        if covered != {skill.id for skill in slot.skills}:
            raise ContentError(f"Course family coverage differs from profile slot {slot.id}")
    if _source_digests() != source_digests:
        raise ContentError("Generator sources changed during assembly; rerun in a fresh process")
    manifest = {
        "build_version": BUILD_VERSION, "profile_id": profile.id,
        "profile_revision": profile.revision,
        "review_status": "demo", "reviewed_by": None,
        "task_count": len(tasks), "legacy_task_count": len(old_tasks), "new_task_count": 780,
        "lesson_count": len(lessons), "legacy_lesson_count": len(old_lessons),
        "new_exam_lesson_count": 78, "foundation_lesson_count": 8,
        "runtime_family_count": len(RUNTIME_FAMILIES), "seed_strata": SEED_STRATA,
        "legacy_sha256": {name: hashlib.sha256(value).hexdigest()
                          for name, value in snapshots.items()},
        "generator_source_sha256": source_digests,
        "foundation_lesson_ids": [lesson["id"] for lesson in foundation_lessons],
        "families": reports,
    }
    return {
        "profile.json": _json(profile_data), "lessons.json": _json(lessons),
        "tasks.json": _json(tasks),
        **{f"legacy/{name}": value for name, value in snapshots.items()},
        "review-worksheet.md": _worksheet(manifest), "manifest.json": _json(manifest),
    }


def _artifact_paths(artifacts: dict[str, bytes]) -> list[Path]:
    if set(artifacts) != set(ARTIFACT_NAMES):
        raise ContentError("Only the fixed generated course artifacts may be written")
    if COURSE_DIR.parent != LEGACY_DIR or COURSE_DIR.name != "course":
        raise ContentError("Output must be the generated content/course directory")
    directories = (LEGACY_DIR, COURSE_DIR, COURSE_DIR / "legacy")
    for directory in directories:
        if directory.is_symlink() or directory.is_junction():
            raise ContentError("Generated output directories must not be links or junctions")
        if directory.exists() and not directory.is_dir():
            raise ContentError("Generated output directory is not a directory")
    paths = [COURSE_DIR / name for name in ARTIFACT_NAMES]
    for path in paths:
        if path.is_symlink() or path.is_junction():
            raise ContentError("Generated artifacts must not be symbolic links or junctions")
        if path.exists() and (not path.is_file() or path.stat().st_nlink != 1):
            raise ContentError("Generated artifacts must be regular, unshared files")
    return paths


def write_course() -> tuple[Path, ...]:
    """Validate the complete build and all destinations before any artifact write."""
    artifacts = build_course()
    paths = _artifact_paths(artifacts)
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic per-file replacement prevents a reader observing truncated JSON.
        # All staging files also live under content/course; no database is opened.
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.",
                                         suffix=".building", delete=False) as stream:
            stream.write(artifacts[path.relative_to(COURSE_DIR).as_posix()])
            staging = stream.name
        os.replace(staging, path)
    return tuple(paths)


def check_course() -> tuple[str, ...]:
    """Return missing/stale artifact names without writing anything."""
    artifacts = build_course()
    _artifact_paths(artifacts)
    return tuple(name for name, value in artifacts.items()
                 if not (COURSE_DIR / name).is_file() or (COURSE_DIR / name).read_bytes() != value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="compare materialized files to a build")
    mode.add_argument("--write", action="store_true", help="write content/course generated files")
    args = parser.parse_args()
    if args.check:
        stale = check_course()
        if stale:
            print("Stale or missing course artifacts: " + ", ".join(stale))
            return 1
        print("Course artifacts match the deterministic build.")
    else:
        paths = write_course()
        print(f"Wrote {len(paths)} course artifacts: 845 tasks, 99 lessons; new material is demo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
