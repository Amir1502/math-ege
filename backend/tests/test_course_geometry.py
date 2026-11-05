"""Independent mathematics from published conditions, never generator model state.

The oracle accepts only the family identifier, statement and public table. Exact
Fraction arithmetic, integer square roots, geometric constructions and exhaustive
small sample spaces determine expectations. Schema validation is a separate check.
"""

import json
import re
from collections import Counter
from fractions import Fraction
from itertools import combinations, permutations, product
from math import isqrt
from pathlib import Path

import pytest

from app.content import Task, public_task
from app.generators.geometry_probability import FAMILIES, build_lessons
from app.schemas import Lesson, ProfileSource

RUNTIME = tuple(family for family in FAMILIES if family.supports_runtime)
STATIC_ONLY = tuple(family for family in FAMILIES if not family.supports_runtime)
BY_ID = {family.id: family for family in FAMILIES}
MAX_SEED = 2**32 - 1
# Ten baseline seeds plus 990 deterministic seeds spread across all 32 bits.
RUNTIME_SEEDS = (*range(10), *((index * 2654435761) % 2**32 for index in range(10, 1000)))


@pytest.fixture(scope="module")
def profile():
    path = Path(__file__).resolve().parents[1] / "content" / "profile.json"
    return ProfileSource.model_validate_json(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def lessons(profile):
    return {lesson["family_ids"][0]: lesson for lesson in build_lessons(profile)}


def _fraction(text):
    assert isinstance(text, str)
    assert re.fullmatch(r"-?\d+(?:[,.]\d+)?", text), text
    return Fraction(text.replace(",", "."))


def _numbers(statement):
    return tuple(
        _fraction(token.replace("−", "-"))
        for token in re.findall(r"[-−]?\d+(?:[,.]\d+)?", statement)
    )


def _integers(statement):
    values = _numbers(statement)
    assert all(value.denominator == 1 for value in values)
    return tuple(int(value) for value in values)


def _distribution(probabilities):
    assert probabilities
    assert all(0 <= probability <= 1 for probability in probabilities)
    assert sum(probabilities) == 1


def _polygon_area(points):
    pairs = zip(points, [*points[1:], points[0]], strict=True)
    return abs(Fraction(sum(x * v - u * y for (x, y), (u, v) in pairs), 2))


def _angle_degrees(ax, ay, bx, by):
    norm_a, norm_b = ax * ax + ay * ay, bx * bx + by * by
    assert norm_a > 0 and norm_b > 0
    dot, cross = ax * bx + ay * by, ax * by - ay * bx
    assert dot * dot + cross * cross == norm_a * norm_b
    if dot == 0:
        return 90
    if cross == 0:
        return 0 if dot > 0 else 180
    # Equal absolute cross/dot products give |tan(phi)| = 1, exactly.
    assert cross * cross == dot * dot
    return 45 if dot > 0 else 135


def _pair_probability(total, marked):
    assert 0 <= marked <= total and total >= 2
    all_pairs = list(combinations(range(total), 2))
    histogram = Counter(sum(card < marked for card in pair) for pair in all_pairs)
    _distribution([Fraction(histogram[count], len(all_pairs)) for count in range(3)])
    return Fraction(histogram[2], len(all_pairs))


def _expected(family_id, statement, table):
    """Solve solely from learner-visible input, including its domain restrictions."""
    match family_id:
        case "triangle-exterior-angle":
            alpha, exterior = _integers(statement)
            beta, gamma = exterior - alpha, 180 - exterior
            assert min(alpha, beta, gamma) > 0
            assert alpha + beta + gamma == 180
            assert "смежный" in statement
            return beta
        case "right-triangle-area":
            leg, hypotenuse = _integers(statement)
            assert 0 < leg < hypotenuse
            other_squared = hypotenuse**2 - leg**2
            other = isqrt(other_squared)
            assert other > 0 and other * other == other_squared
            assert leg + other > hypotenuse
            assert leg + hypotenuse > other and other + hypotenuse > leg
            return _polygon_area([(0, 0), (leg, 0), (0, other)])
        case "trapezoid-area":
            small, large, height = _integers(statement)
            assert 0 < small < large and height > 0
            # A concrete convex trapezoid; shoelace, not the generator's formula.
            return _polygon_area([(0, 0), (large, 0), (small, height), (0, height)])
        case "cyclic-quadrilateral-angle":
            (alpha,) = _integers(statement)
            assert 0 < alpha < 180
            assert "вписан" in statement and "Выпуклый" in statement
            # Complementary arcs BD together make a full circle.
            arc_without_a = 2 * alpha
            arc_without_c = 360 - arc_without_a
            assert min(arc_without_a, arc_without_c) > 0
            return Fraction(arc_without_c, 2)
        case "similar-triangles-area":
            ab, ad, full_area = _integers(statement)
            assert 0 < ad < ab and full_area > 0
            assert "DE параллельна BC" in statement
            # Construct ABC with A=(0,0), B=(AB,0), C=(0,h).
            height = Fraction(2 * full_area, ab)
            small_height = height * Fraction(ad, ab)
            assert 0 < small_height < height
            assert _polygon_area([(0, 0), (ab, 0), (0, height)]) == full_area
            return _polygon_area([(0, 0), (ad, 0), (0, small_height)])
        case "intersecting-chords":
            ae, eb, ce = _integers(statement)
            assert min(ae, eb, ce) > 0
            ed = Fraction(ae * eb, ce)
            # Prove existence using perpendicular chords through the origin.
            cx, cy = Fraction(eb - ae, 2), Fraction(ce - ed, 2)
            radius_squared = ae * eb + cx * cx + cy * cy
            assert radius_squared > cx * cx + cy * cy  # E lies inside the circle.
            for x, y in [(-ae, 0), (eb, 0), (0, ce), (0, -ed)]:
                assert (x - cx) ** 2 + (y - cy) ** 2 == radius_squared
            return ed
        case "displacement-length":
            ax, ay, bx, by = _integers(statement)
            squared = (bx - ax) ** 2 + (by - ay) ** 2
            length = isqrt(squared)
            assert length > 0 and length * length == squared
            assert max(abs(bx - ax), abs(by - ay)) <= length
            return length
        case "vector-sum-length":
            ax, ay, bx, by = _integers(statement)
            squared = (ax + bx) ** 2 + (ay + by) ** 2
            result = isqrt(squared)
            assert result * result == squared
            return result
        case "vector-scaled-difference":
            _, ay, _, by, factor = _integers(statement)
            assert factor > 0
            return ay - factor * by
        case "vector-dot-product":
            ax, ay, bx, by = _integers(statement)
            # Polarization gives the product without the generator's direct sum.
            squared_sum = (ax + bx) ** 2 + (ay + by) ** 2
            squared_a, squared_b = ax * ax + ay * ay, bx * bx + by * by
            return Fraction(squared_sum - squared_a - squared_b, 2)
        case "vector-angle":
            return _angle_degrees(*_integers(statement))
        case "right-prism-volume":
            a, b, height = _integers(statement)
            assert min(a, b, height) > 0
            assert "прямоугольный треугольник" in statement and "см³" in statement
            return _polygon_area([(0, 0), (a, 0), (0, b)]) * height
        case "rectangular-box-surface":
            sides = _integers(statement)
            assert len(sides) == 3 and min(sides) > 0
            assert "полной поверхности" in statement and "см²" in statement
            # The six ordered dimension pairs enumerate the six faces.
            return sum(first * second for first, second in permutations(sides, 2))
        case "square-pyramid-volume":
            side, height = _integers(statement)
            assert min(side, height) > 0
            assert "Перпендикуляр" in statement and "см³" in statement
            return Fraction(side * side * height, 3)
        case "cylinder-volume-coefficient":
            radius, height = _integers(statement)
            assert min(radius, height) > 0
            assert "Радиус" in statement and "V = kπ см³" in statement
            return radius * radius * height
        case "cone-surface-coefficient":
            radius, height = _integers(statement)
            assert min(radius, height) > 0
            slant = isqrt(radius * radius + height * height)
            assert slant * slant == radius * radius + height * height
            assert slant > max(radius, height)
            assert "включая основание" in statement and "S = kπ см²" in statement
            return radius * radius + radius * slant
        case "sphere-volume-coefficient":
            (radius,) = _integers(statement)
            assert radius > 0
            assert "Радиус шара" in statement and "V = kπ см³" in statement
            return Fraction(4 * radius**3, 3)
        case "solid-similarity-volume":
            small, large, volume = _integers(statement)
            assert 0 < small < large and volume > 0
            assert "подобны" in statement and "см³" in statement
            result = Fraction(volume * large**3, small**3)
            assert result > volume
            return result
        case "urn-favorable-count":
            red, blue = _integers(statement)
            assert min(red, blue) > 0
            probability = Fraction(red, red + blue)
            _distribution([probability, Fraction(blue, red + blue)])
            return probability
        case "integer-event-boundaries":
            start, total, lower, upper = _integers(statement)
            assert start == 1 and 1 <= lower < upper <= total
            assert "больше" in statement and "не превосходит" in statement
            # Enumerate real card numbers: protects both boundary conventions.
            count = sum(lower < number <= upper for number in range(1, total + 1))
            result = Fraction(count, total)
            _distribution([result, Fraction(total - count, total)])
            return result
        case "complement-quality":
            (defective,) = _numbers(statement)
            assert 0 < defective < 1
            assert "третьего исхода нет" in statement
            result = Fraction(defective.denominator - defective.numerator, defective.denominator)
            _distribution([result, defective])
            return result
        case "coin-pattern-enumeration":
            tosses, heads = _integers(statement)
            assert 3 <= tosses <= 6 and 0 <= heads <= tosses
            assert "независимо" in statement and "ровно" in statement
            outcomes = list(product((0, 1), repeat=tosses))
            histogram = Counter(sum(outcome) for outcome in outcomes)
            _distribution([Fraction(histogram[k], len(outcomes)) for k in range(tosses + 1)])
            return Fraction(histogram[heads], len(outcomes))
        case "spinner-sector":
            (angle,) = _integers(statement)
            assert 0 < angle < 360
            assert "границе равна нулю" in statement
            result = Fraction(angle, 360)
            _distribution([result, Fraction(360 - angle, 360)])
            return result
        case "independent-at-least-one":
            first, second = _numbers(statement)
            assert 0 < first < 1 and 0 < second < 1
            assert "независимо" in statement and "хотя бы один" in statement
            _distribution([
                first * second, first * (1 - second),
                (1 - first) * second, (1 - first) * (1 - second),
            ])
            result = first + second - first * second  # Inclusion/exclusion oracle.
            assert max(first, second) <= result <= 1
            return result
        case "conditional-without-replacement":
            total, red = _integers(statement)
            assert 2 <= red < total
            assert "без возвращения" in statement and "условную" in statement
            # All ordered pairs from the ORIGINAL box; restrict to known first-red.
            conditions = successes = 0
            for first, second in permutations(range(total), 2):
                if first < red:
                    conditions += 1
                    successes += second < red
            assert conditions > 0
            result = Fraction(successes, conditions)
            _distribution([result, Fraction(conditions - successes, conditions)])
            assert result < Fraction(red, total)  # Demonstrates actual dependence.
            return result
        case "overlapping-event-union":
            total, a, b, both = _integers(statement)
            assert 0 < both <= min(a, b)
            only_a, only_b, neither = a - both, b - both, total - a - b + both
            assert min(only_a, only_b, neither) >= 0
            _distribution([Fraction(count, total) for count in (only_a, only_b, both, neither)])
            return 1 - Fraction(neither, total)
        case "total-probability-routing":
            assert not _numbers(statement)
            assert table["headers"] == [
                "Станок", "Доля продукции в партии", "Вероятность брака на этом станке",
            ]
            assert [row[0] for row in table["rows"]] == ["А", "Б"]
            branches = [(_fraction(row[1]), _fraction(row[2])) for row in table["rows"]]
            _distribution([weight for weight, _ in branches])
            for _, defective in branches:
                assert 0 < defective < 1
            leaves = [weight * chance for weight, d in branches for chance in (d, 1 - d)]
            _distribution(leaves)
            result = sum(weight * defective for weight, defective in branches)
            assert min(d for _, d in branches) <= result <= max(d for _, d in branches)
            return result
        case "event-tree-exactly-one":
            p, q, r = _numbers(statement)
            assert all(0 < value < 1 for value in (p, q, r))
            assert q != r  # The dependent-tree family must actually exercise dependence.
            assert "Обе попытки выполняются" in statement
            leaves = [p * q, p * (1 - q), (1 - p) * r, (1 - p) * (1 - r)]
            _distribution(leaves)
            return 1 - leaves[0] - leaves[3]  # Exclude zero and two successes.
        case "combinatorial-subset":
            total, marked = _integers(statement)
            assert "неупорядоченные пары равновероятны" in statement
            return _pair_probability(total, marked)
        case _:
            raise AssertionError(f"No independently authored oracle for {family_id}")


def _check_figure(task):
    figure = task["figure"]
    if figure is None:
        return
    assert set(figure) == {
        "description", "x_min", "x_max", "y_min", "y_max", "axes", "lines", "circles", "labels",
    }
    assert figure["axes"] is False
    assert -10000 <= figure["x_min"] < figure["x_max"] <= 10000
    assert -10000 <= figure["y_min"] < figure["y_max"] <= 10000
    for line in figure["lines"]:
        assert set(line) <= {"points", "dashed"} and len(line["points"]) >= 2
        for point in line["points"]:
            assert set(point) == {"x", "y"}
            assert figure["x_min"] <= point["x"] <= figure["x_max"]
            assert figure["y_min"] <= point["y"] <= figure["y_max"]
    for label in figure["labels"]:
        assert set(label) == {"x", "y", "text"}
        assert figure["x_min"] <= label["x"] <= figure["x_max"]
        assert figure["y_min"] <= label["y"] <= figure["y_max"]
    assert figure["circles"] == []
    assert not re.search(r"<\s*/?\s*(?:svg|html)\b", json.dumps(figure), re.IGNORECASE)
    # This shard's diagram is a true-to-model right triangle, not a decorative sketch.
    assert task["family_id"] == "right-triangle-area"
    leg, hypotenuse = _integers(task["statement"])
    a, b, c, closing = figure["lines"][0]["points"]
    assert a == closing == {"x": 0, "y": 0}
    assert b == {"x": leg, "y": 0} and c["x"] == 0 and c["y"] > 0
    assert leg * leg + c["y"] * c["y"] == hypotenuse * hypotenuse
    assert {label["text"] for label in figure["labels"]} == {"A", "B", "C"}


def _check_task(family, seed, profile):
    task = family.generate(seed, profile)
    expected = _expected(family.id, task["statement"], task["table"])
    assert _fraction(task["answer"]) == expected
    assert task == family.generate(seed, profile), "A seed must reproduce the entire snapshot"
    assert task["id"] == f"course-{family.id}-{seed}"
    assert task["family_id"] == family.id and task["slot"] == family.slot
    slot = next(slot for slot in profile.slots if slot.number == family.slot)
    assert task["slot_id"] == slot.id and task["profile_id"] == profile.id
    assert task["skill_ids"] == list(family.skill_ids)
    assert task["review_status"] == "demo" and task["source"]["reviewed_by"] is None
    assert task["generation"] == {
        "template_id": family.id, "template_version": "1", "seed": seed,
    }
    assert task["rounding"] is None
    assert len(task["hints"]) == task["hint_count"] == 3
    assert len(set(task["hints"])) == 3
    assert all(text.strip() for text in [*task["hints"], *task["solution"]])
    assert 1 <= task["difficulty"] <= 3 and task["estimated_seconds"] > 0
    if family.slot in (4, 5):
        assert 0 <= expected <= 1
    _check_figure(task)
    Task.model_validate(task)  # Shape/format validation, not the mathematical oracle.
    return task


@pytest.mark.parametrize("family", RUNTIME, ids=lambda family: family.id)
@pytest.mark.parametrize("seed", RUNTIME_SEEDS)
def test_runtime_condition_oracles(family, seed, profile):
    _check_task(family, seed, profile)


@pytest.mark.parametrize("family", STATIC_ONLY, ids=lambda family: family.id)
@pytest.mark.parametrize("seed", range(10))
def test_static_family_condition_oracles(family, seed, profile):
    _check_task(family, seed, profile)


@pytest.mark.parametrize("family", FAMILIES, ids=lambda family: family.id)
def test_unsigned_seed_upper_boundary(family, profile):
    _check_task(family, MAX_SEED, profile)


@pytest.mark.parametrize("family", FAMILIES, ids=lambda family: family.id)
@pytest.mark.parametrize("bad_seed", [-1, 2**32, True, 1.5, "1", None])
def test_invalid_seed_rejected(family, bad_seed, profile):
    with pytest.raises(ValueError, match="unsigned 32-bit"):
        family.generate(bad_seed, profile)


@pytest.mark.parametrize("family", FAMILIES, ids=lambda family: family.id)
def test_ten_distinct_published_conditions(family, profile):
    """Numeric uniqueness alone does not establish branch or answer-sign diversity."""
    fingerprints = set()
    answers = set()
    for seed in range(10):
        task = family.generate(seed, profile)
        fingerprints.add(json.dumps([task["statement"], task["table"]], ensure_ascii=False))
        answers.add(task["answer"])
    assert len(fingerprints) == 10
    assert len(answers) >= 2, "The starter practice must not teach a constant-answer shortcut"


@pytest.mark.parametrize(
    "family",
    [family for family in FAMILIES if "plane-theorem-choice" in family.skill_ids],
    ids=lambda family: family.id,
)
@pytest.mark.parametrize("seed", range(10))
def test_initial_theorem_choice_task_defers_solving_formula(family, seed, profile, lessons):
    task = family.generate(seed, profile)
    exercise = public_task(Task.model_validate(task)).model_dump()
    assert exercise["formula"] is None
    assert {"answer", "hints", "solution"}.isdisjoint(exercise)
    assert exercise["hint_count"] == 3
    assert exercise["review_status"] == "demo" and task["source"]["reviewed_by"] is None
    assert task["hints"][1].strip()
    assert any(section["formula"] for section in lessons[family.id]["sections"])
    expected = _expected(family.id, exercise["statement"], exercise["table"])
    assert _fraction(task["answer"]) == expected


def test_skill_coverage_and_two_supported_templates_per_slot(profile):
    assert len(RUNTIME_SEEDS) == len(set(RUNTIME_SEEDS)) == 1000
    assert 0 in RUNTIME_SEEDS and MAX_SEED not in RUNTIME_SEEDS
    assert len(BY_ID) == len(FAMILIES) == 29
    assert Counter(family.slot for family in FAMILIES) == {1: 6, 2: 5, 3: 7, 4: 5, 5: 6}
    assert Counter(family.slot for family in RUNTIME) == dict.fromkeys(range(1, 6), 2)
    assert all(re.fullmatch(r"[a-z]+(?:-[a-z]+)*", family.id) for family in FAMILIES)
    for slot in profile.slots[:5]:
        taught = {
            skill for family in FAMILIES if family.slot == slot.number for skill in family.skill_ids
        }
        assert taught == {skill.id for skill in slot.skills}
    angles = {BY_ID["vector-angle"].generate(seed, profile)["answer"] for seed in range(10)}
    assert angles == {"0", "45", "90", "135", "180"}


@pytest.mark.parametrize("family", FAMILIES, ids=lambda family: family.id)
def test_substantive_lessons_and_independent_practice(family, lessons, profile):
    lesson = lessons[family.id]
    parsed = Lesson.model_validate(lesson)
    assert parsed.id == f"course-{family.id}"
    assert parsed.slot == family.slot and parsed.skill_ids == list(family.skill_ids)
    assert parsed.slot_id == next(slot.id for slot in profile.slots if slot.number == family.slot)
    assert 3 <= parsed.minutes <= 7
    assert parsed.review_status == "demo" and parsed.reviewed_by is None
    assert parsed.family_ids == [family.id]
    assert parsed.practice_task_ids == [f"course-{family.id}-{seed}" for seed in range(3)]
    assert len(parsed.sections) == 4
    assert len({section.heading for section in parsed.sections}) == 4
    text = " ".join(section.body for section in parsed.sections)
    text += " " + parsed.example.statement + " " + " ".join(parsed.example.steps)
    text += " " + parsed.takeaway
    assert 350 <= len(re.findall(r"[^\W\d_]+", text)) <= 600
    assert not re.search(r"TODO|TBD|заглушк|lorem ipsum", text, re.IGNORECASE)
    for seed in range(3):
        practice = family.generate(seed, profile)
        assert practice["statement"] != parsed.example.statement
        assert practice["id"] == parsed.practice_task_ids[seed]
    assert len(parsed.example.steps) >= 3
    _fraction(parsed.example.answer)


# These literal conditions are deliberately separate from generated seed 0, 1, 2.
# Re-derivation uses hand-selected numbers and independent elementary identities.
EXAMPLES = [
    ("triangle-exterior-angle", (47, 119), 119 - 47),
    ("right-triangle-area", (15, 17), Fraction(15 * isqrt(17**2 - 15**2), 2)),
    ("trapezoid-area", (7, 13, 6), _polygon_area([(0, 0), (13, 0), (7, 6), (0, 6)])),
    ("cyclic-quadrilateral-angle", (113,), Fraction(360 - 2 * 113, 2)),
    ("similar-triangles-area", (15, 9, 125), 125 * Fraction(9, 15) ** 2),
    ("intersecting-chords", (9, 4, 6), Fraction(9 * 4, 6)),
    ("displacement-length", (-2, 5, 10, -4), isqrt((10 + 2)**2 + (-4 - 5)**2)),
    ("vector-sum-length", (7, -3, -2, 15), isqrt((7 - 2)**2 + (-3 + 15)**2)),
    ("vector-scaled-difference", (5, 7, -2, 3, 4), 7 - 4 * 3),
    ("vector-dot-product", (-4, 6, 3, 5), ((-4) * 3) + (6 * 5)),
    ("vector-angle", (3, 1, 2, 4), _angle_degrees(3, 1, 2, 4)),
    ("right-prism-volume", (5, 8, 9), Fraction(5 * 8 * 9, 2)),
    ("rectangular-box-surface", (4, 6, 9), 2 * 4 * 6 + 2 * 4 * 9 + 2 * 6 * 9),
    ("square-pyramid-volume", (6, 10), Fraction(6 * 6 * 10, 3)),
    ("cylinder-volume-coefficient", (5, 7), 5 * 5 * 7),
    ("cone-surface-coefficient", (5, 12), 5 * 5 + 5 * isqrt(5**2 + 12**2)),
    ("sphere-volume-coefficient", (Fraction(9, 2),), Fraction(4, 3) * Fraction(9, 2)**3),
    ("solid-similarity-volume", (4, 10, 32), 32 * Fraction(10, 4)**3),
    ("urn-favorable-count", (7, 18), Fraction(7, 7 + 18)),
    (
        "integer-event-boundaries", (1, 80, 17, 43),
        Fraction(sum(17 < i <= 43 for i in range(1, 81)), 80),
    ),
    ("complement-quality", (Fraction(37, 1000),), 1 - Fraction(37, 1000)),
    (
        "coin-pattern-enumeration", (),
        Fraction(sum(sum(outcome) == 2 for outcome in product((0, 1), repeat=3)), 8),
    ),
    ("spinner-sector", (126,), Fraction(126, 360)),
    (
        "independent-at-least-one", (Fraction(65, 100), Fraction(8, 10)),
        Fraction(65, 100) + Fraction(8, 10) - Fraction(65, 100) * Fraction(8, 10),
    ),
    ("conditional-without-replacement", (26, 11), Fraction(11 * 10, 11 * 25)),
    ("overlapping-event-union", (80, 37, 29, 14), Fraction(37 + 29 - 14, 80)),
    (
        "total-probability-routing",
        (Fraction(3, 10), Fraction(7, 10), Fraction(2, 100), Fraction(6, 100)),
        Fraction(3, 10) * Fraction(2, 100) + Fraction(7, 10) * Fraction(6, 100),
    ),
    (
        "event-tree-exactly-one", (Fraction(6, 10), Fraction(7, 10), Fraction(2, 10)),
        1 - Fraction(6, 10) * Fraction(7, 10) - Fraction(4, 10) * Fraction(8, 10),
    ),
    ("combinatorial-subset", (10, 9), _pair_probability(10, 9)),
]


@pytest.mark.parametrize("family_id,numbers,expected", EXAMPLES, ids=[row[0] for row in EXAMPLES])
def test_worked_examples_against_independent_literals(family_id, numbers, expected, lessons):
    example = lessons[family_id]["example"]
    assert _numbers(example["statement"]) == numbers
    if family_id == "coin-pattern-enumeration":
        assert "бросают три раза" in example["statement"]
        assert "ровно двух орлов" in example["statement"]
    assert _fraction(example["answer"]) == expected


def test_tree_normalization_does_not_validate_branch_conditions(lessons):
    example = lessons["event-tree-exactly-one"]["example"]
    p, q, r = _numbers(example["statement"])
    expected = _expected("event-tree-exactly-one", example["statement"], None)
    assert expected == _fraction(example["answer"]) == Fraction(26, 100)

    # Swap the conditional probabilities AND their complements between parent branches.
    swapped = [p * r, p * (1 - r), (1 - p) * q, (1 - p) * (1 - q)]
    _distribution(swapped)
    wrong = swapped[1] + swapped[2]
    assert wrong == 1 - swapped[0] - swapped[3] == Fraction(76, 100)
    assert wrong != expected
    # Reconstructing each branch's conditional probability exposes the wrong assignment.
    assert swapped[0] / p != q
    assert swapped[2] / (1 - p) != r


def test_every_family_has_a_literal_example_oracle():
    assert {row[0] for row in EXAMPLES} == set(BY_ID)


def test_lessons_return_detached_content(profile):
    before = build_lessons(profile)
    changed = build_lessons(profile)
    changed[0]["sections"][0]["body"] = "edited locally"
    changed[0]["example"]["steps"].append("local extra step")
    changed[0]["skill_ids"].clear()
    changed[0]["practice_task_ids"].clear()
    assert build_lessons(profile) == before


def test_missing_profile_skill_is_rejected(profile):
    changed = profile.model_copy(deep=True)
    changed.slots[0].skills = []
    with pytest.raises(ValueError, match="profile"):
        build_lessons(changed)


def test_task_and_lesson_bind_to_supplied_profile(profile):
    changed = profile.model_copy(deep=True)
    changed.id = "geometry-candidate-profile"
    changed.slots[0].id = "geometry-stable-position"
    task = BY_ID["right-triangle-area"].generate(57, changed)
    assert task["profile_id"] == changed.id
    assert task["slot_id"] == changed.slots[0].id
    lesson = next(item for item in build_lessons(changed) if item["slot"] == 1)
    assert lesson["slot_id"] == changed.slots[0].id
