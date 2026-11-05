"""Public-output mathematical checks, not an independent methodological review."""

import json
import re
from collections import Counter
from fractions import Fraction
from math import isfinite, isqrt
from pathlib import Path

import pytest

from app.schemas import ProfileSource

PROFILE_PATH = Path(__file__).resolve().parents[1] / "content" / "profile.json"
PROFILE = ProfileSource.model_validate_json(PROFILE_PATH.read_text(encoding="utf-8"))


def fraction(text):
    return Fraction(str(text).replace("−", "-").replace(",", "."))


def families():
    from app.generators.algebra_analysis import FAMILIES

    return {family.id: family for family in FAMILIES}


def capture(pattern, text):
    match = re.fullmatch(pattern, text)
    assert match is not None, text
    return tuple(fraction(value) for value in match.groups())


def distribution_rows(task):
    assert task["table"]["headers"] == ["Значение X", "Вероятность"]
    rows = [(fraction(x), fraction(p)) for x, p in task["table"]["rows"]]
    assert len({x for x, _ in rows}) == len(rows)
    assert all(x >= 0 and 0 < p < 1 for x, p in rows)
    assert sum(p for _, p in rows) == 1
    return rows


def mean_oracle(task):
    rows = distribution_rows(task)
    # A 100-trial exact frequency population is independent of the generator's sum.
    population = [x for x, p in rows for _ in range(int(100 * p))]
    assert len(population) == 100
    return sum(population) / len(population)


def variance_oracle(task):
    rows = distribution_rows(task)
    # Pairwise distances avoid the generator's second-moment subtraction.
    result = sum((x - y) ** 2 * p * q for x, p in rows for y, q in rows) / 2
    assert result >= 0
    return result


def test_weighted_mean_from_visible_distribution():
    family = families()["distribution-weighted-mean"]
    task = family.generate(0, PROFILE)
    assert "математическое ожидание" in task["statement"]
    assert task["table"]["headers"] == ["Значение X", "Вероятность"]
    rows = [(fraction(x), fraction(p)) for x, p in task["table"]["rows"]]
    assert rows == [(2, Fraction(1, 5)), (4, Fraction(3, 10)), (7, Fraction(1, 2))]
    assert fraction(task["answer"]) == Fraction(51, 10)
    assert sum(p for _, p in rows) == 1
    assert json.loads(json.dumps(task, ensure_ascii=False)) == task


def test_variance_literal_and_public_pairwise_oracle():
    task = families()["distribution-weighted-variance"].generate(0, PROFILE)
    assert fraction(task["answer"]) == Fraction(409, 100)
    assert fraction(task["answer"]) == variance_oracle(task)


def distribution_oracle(task):
    family_id = task["family_id"]
    statement = task["statement"]
    if family_id == "distribution-weighted-mean":
        assert "математическое ожидание" in statement
        return mean_oracle(task)
    if family_id == "distribution-weighted-variance":
        assert "дисперсию" in statement
        return variance_oracle(task)
    if family_id == "distribution-missing-probability":
        assert "пропущенную вероятность" in statement
        assert task["table"]["headers"] == ["Значение X", "Вероятность"]
        cells = [p for _, p in task["table"]["rows"]]
        assert cells.count("p") == 1
        known = [fraction(p) for p in cells if p != "p"]
        assert all(0 < p < 1 for p in known) and sum(known) < 1
        return 1 - sum(known)
    if family_id == "distribution-two-point-deviation":
        assert "стандартное отклонение" in statement
        variance = variance_oracle(task)
        result = Fraction(isqrt(variance.numerator), isqrt(variance.denominator))
        assert result**2 == variance
        return result
    if family_id == "distribution-step-cdf":
        (threshold,) = capture(
            r"Распределение X дано в таблице\. Функция распределения определена как "
            r"F\(t\) = P\(X ≤ t\)\. Найдите F\(([0-9]+)\)\.", statement,
        )
        rows = distribution_rows(task)
        assert threshold in {x for x, _ in rows}
        return 1 - sum(p for x, p in rows if x > threshold)
    if family_id == "distribution-linear-density":
        (right,) = capture(
            r"Плотность непрерывной случайной величины равна f\(x\) = c·x при "
            r"0 ≤ x ≤ ([0-9]+) и равна нулю вне этого отрезка\. Найдите c\.", statement,
        )
        assert right > 0
        coefficient = Fraction(2, right**2)
        # Density is nonnegative and its triangular area is exactly one.
        assert coefficient > 0 and right * (coefficient * right) / 2 == 1
        return coefficient
    if family_id == "distribution-uniform-interval":
        left, right, start, end = capture(
            r"X равномерно распределена на отрезке \[([0-9]+); ([0-9]+)\]\. "
            r"Найдите P\(([0-9]+) ≤ X ≤ ([0-9]+)\)\.", statement,
        )
        assert left < start < end < right
        cdf_start = (start - left) / (right - left)
        cdf_end = (end - left) / (right - left)
        return cdf_end - cdf_start
    if family_id == "distribution-exponential-survival":
        rate, logarithm, divisor = capture(
            r"Время ожидания T имеет показательное распределение с интенсивностью "
            r"λ = ([0-9]+) мин⁻¹\. Найдите P\(T > ln\(([0-9]+)\)/([0-9]+)\), "
            r"где время измерено в минутах\.", statement,
        )
        assert rate > 0 and logarithm > 1 and rate == divisor
        return Fraction(1, logarithm)
    assert family_id == "distribution-normal-symmetry"
    center, left, right, central, threshold = capture(
        r"X имеет нормальное распределение с математическим ожиданием μ = ([0-9]+)\. "
        r"Известно точное значение P\(([0-9]+) < X < ([0-9]+)\) = ([0-9,]+)\. "
        r"Найдите P\(X ≥ ([0-9]+)\)\.", statement,
    )
    assert center - left == right - center > 0 and threshold == right
    assert 0 < central < 1
    # Symmetry gives equal complementary tails, with no numerical normal CDF.
    return (1 - central) / 2


@pytest.mark.parametrize("seed", range(10))
def test_distribution_families_from_visible_conditions(seed):
    members = [family for family in families().values() if family.slot == 6]
    assert len(members) == 9
    for family in members:
        task = family.generate(seed, PROFILE)
        assert fraction(task["answer"]) == distribution_oracle(task)


def equation_oracle(task):
    statement = task["statement"]
    family_id = task["family_id"]
    if family_id == "rational-excluded-root":
        total, product, excluded = capture(
            r"Решите уравнение \(x² − ([0-9]+)x \+ ([0-9]+)\)/"
            r"\(x − ([0-9]+)\) = 0\.", statement,
        )
        discriminant = total**2 - 4 * product
        root = isqrt(discriminant.numerator)
        assert discriminant.denominator == 1 and root**2 == discriminant
        candidates = [(total - root) / 2, (total + root) / 2]
        assert excluded in candidates
        valid = [x for x in candidates if x != excluded]
        assert len(valid) == 1
        (x,) = valid
        assert (x * x - total * x + product) / (x - excluded) == 0
        return x
    if family_id == "radical-extraneous-root":
        constant, shift = capture(
            r"Решите уравнение √\(x \+ ([0-9]+)\) = x − ([0-9]+)\.", statement,
        )
        # Complete the square in the displayed equation, then check both candidates.
        discriminant = 4 * shift + 1 + 4 * constant
        root = isqrt(discriminant.numerator)
        assert root**2 == discriminant
        candidates = [(2 * shift + 1 - root) / 2, (2 * shift + 1 + root) / 2]
        valid = [x for x in candidates if x + constant >= 0 and x - shift >= 0]
        rejected = [x for x in candidates if x - shift < 0]
        assert len(valid) == len(rejected) == 1
        (x,) = valid
        assert (x - shift)**2 == x + constant
        assert (rejected[0] - shift)**2 == rejected[0] + constant
        return x
    if family_id == "exponential-common-base":
        base, shift, other, exponent = capture(
            r"Решите уравнение ([0-9]+)\^\(2x − ([0-9]+)\) = "
            r"([0-9]+)\^([0-9]+)\.", statement,
        )
        assert base > 1 and other == base**2
        right = other ** int(exponent)
        # Enumerate half-integer candidates and compare the original powers exactly.
        valid = [Fraction(i, 2) for i in range(101) if base ** (i - int(shift)) == right]
        assert len(valid) == 1
        return valid[0]
    if family_id == "logarithmic-product-domain":
        base, shift, other_base, other_shift, final_base, number = capture(
            r"Решите уравнение log_([0-9]+)\(x − ([0-9]+)\) \+ "
            r"log_([0-9]+)\(x \+ ([0-9]+)\) = log_([0-9]+)\(([0-9]+)\)\.",
            statement,
        )
        assert base == other_base == final_base and base > 1 and shift == other_shift
        assert number > 0
        square = number + shift**2
        root = Fraction(isqrt(square.numerator))
        assert root**2 == square
        candidates = [root, -root]
        valid = [x for x in candidates if x - shift > 0 and x + shift > 0]
        assert len(valid) == 1
        assert (valid[0] - shift) * (valid[0] + shift) == number
        return valid[0]
    assert family_id == "absolute-value-selected-root"
    shift, distance = capture(
        r"Решите уравнение \|x − ([0-9]+)\| = ([0-9]+)\. "
        r"В ответе укажите меньший корень\.", statement,
    )
    assert distance > 0
    candidates = [shift + distance, shift - distance]
    assert all(abs(x - shift) == distance for x in candidates)
    return min(candidates)


def test_radical_equation_rejects_a_root_created_by_squaring():
    task = families()["radical-extraneous-root"].generate(0, PROFILE)
    assert task["statement"] == "Решите уравнение √(x + 5) = x − 1."
    assert fraction(task["answer"]) == 4
    assert equation_oracle(task) == 4  # x = -1 satisfies the squared equation only.


@pytest.mark.parametrize("seed", range(10))
def test_equation_families_check_the_original_domain(seed):
    members = [family for family in families().values() if family.slot == 7]
    assert len(members) == 5
    for family in members:
        task = family.generate(seed, PROFILE)
        assert fraction(task["answer"]) == equation_oracle(task)


def transformation_oracle(task):
    statement = task["statement"]
    family_id = task["family_id"]
    if family_id == "power-product-quotient":
        base, positive, repeated, negative, divisor = capture(
            r"Вычислите \(([0-9]+)\^([0-9]+) · ([0-9]+)\^\((-?[0-9]+)\)\)"
            r"/([0-9]+)\.", statement,
        )
        assert base == repeated == divisor and base > 0 and negative < 0
        return base ** int(positive) * repeated ** int(negative) / divisor
    if family_id == "radical-conjugates":
        radicand, shift, repeated, other_shift = capture(
            r"Вычислите \(√([0-9]+) \+ ([0-9]+)\)\(√([0-9]+) − ([0-9]+)\)\.",
            statement,
        )
        assert radicand == repeated and shift == other_shift
        assert radicand > 0 and isqrt(int(radicand))**2 != radicand
        # Multiply in Q[sqrt(n)]; the coefficient of sqrt(n) must cancel.
        rational_part = radicand - shift * other_shift
        radical_part = shift - other_shift
        assert radical_part == 0
        return rational_part
    if family_id == "rational-removable-factor":
        square, shift, value = capture(
            r"Найдите значение \(x² − ([0-9]+)\)/\(x − ([0-9]+)\) при x = ([0-9]+)\.",
            statement,
        )
        assert shift**2 == square and value != shift
        return (value**2 - square) / (value - shift)
    if family_id == "logarithm-difference":
        base, first, other_base, second = capture(
            r"Вычислите log_([0-9]+)\(([0-9]+)\) − log_([0-9]+)\(([0-9]+)\)\.",
            statement,
        )
        assert base == other_base and base > 1 and first > 0 and second > 0
        power = first / second
        exponent = 0
        while power > 1:
            power /= base
            exponent += 1
        assert power == 1
        return Fraction(exponent)
    assert family_id == "trigonometric-double-angle"
    coefficient, numerator, denominator = capture(
        r"Найдите ([0-9]+)·sin\(2α\), если sin α = ([0-9]+)/([0-9]+) "
        r"и π/2 < α < π\.", statement,
    )
    sine = numerator / denominator
    assert 0 < sine < 1
    cos_squared = 1 - sine**2
    cosine = -Fraction(isqrt(cos_squared.numerator), isqrt(cos_squared.denominator))
    assert cosine**2 == cos_squared
    return coefficient * 2 * sine * cosine


def test_rational_transformation_literal_from_original_expression():
    task = families()["rational-removable-factor"].generate(0, PROFILE)
    assert task["statement"] == "Найдите значение (x² − 1)/(x − 1) при x = 2."
    assert transformation_oracle(task) == fraction(task["answer"]) == 3


@pytest.mark.parametrize("seed", range(10))
def test_transformations_have_exact_real_domain_answers(seed):
    members = [family for family in families().values() if family.slot == 8]
    assert len(members) == 5
    for family in members:
        task = family.generate(seed, PROFILE)
        assert fraction(task["answer"]) == transformation_oracle(task)


def figure_points(line):
    return [(fraction(point["x"]), fraction(point["y"])) for point in line["points"]]


def interpolate(points, argument):
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        assert x0 < x1
        if x0 <= argument <= x1:
            return (y0 * (x1 - argument) + y1 * (argument - x0)) / (x1 - x0)
    raise AssertionError(f"Argument {argument} is outside the plotted line")


def check_figure(task):
    figure = task["figure"]
    assert set(figure) == {
        "description", "x_min", "x_max", "y_min", "y_max", "axes", "lines", "circles", "labels",
    }
    assert figure["description"] == task["statement"]
    assert figure["axes"] is True and figure["circles"] == []
    for key in ("x_min", "x_max", "y_min", "y_max"):
        assert type(figure[key]) in (int, float)
        assert isfinite(figure[key]) and -10000 <= figure[key] <= 10000
    assert figure["x_min"] < figure["x_max"] and figure["y_min"] < figure["y_max"]
    points = []
    for line in figure["lines"]:
        assert set(line) <= {"points", "dashed"}
        assert 2 <= len(line["points"]) <= 201
        assert type(line.get("dashed", False)) is bool
        for point in line["points"]:
            assert set(point) == {"x", "y"}
        points.extend(line["points"])
    for label in figure["labels"]:
        assert set(label) == {"x", "y", "text"} and label["text"].strip()
    points.extend(figure["labels"])
    for point in points:
        assert type(point["x"]) in (int, float) and type(point["y"]) in (int, float)
        assert figure["x_min"] <= point["x"] <= figure["x_max"]
        assert figure["y_min"] <= point["y"] <= figure["y_max"]
    assert not re.search(r"<|>|\b(?:svg|script)\b", json.dumps(figure, ensure_ascii=False))


def visible_vertices(task):
    vertices = re.findall(r"([ABCD])\((-?[0-9]+(?:,[0-9]+)?); (-?[0-9]+(?:,[0-9]+)?)\)",
                          task["statement"])
    assert len(vertices) >= 2
    labels = {label["text"]: label for label in task["figure"]["labels"]}
    points = []
    for name, x, y in vertices:
        point = (fraction(x), fraction(y))
        assert point == (fraction(labels[name]["x"]), fraction(labels[name]["y"]))
        points.append(point)
    return points


def calculus_oracle(task):
    family_id = task["family_id"]
    statement = task["statement"]
    if family_id == "antiderivative-initial-value":
        slope, intercept, initial, target = capture(
            r"F — первообразная функции f\(x\) = ([0-9]+)x \+ ([0-9]+)\. "
            r"Известно F\(0\) = ([0-9]+)\. Найдите F\(([0-9]+)\)\.", statement,
        )
        assert slope > 0 and target > 0
        # The exact trapezoidal area of the original affine f gives F(t) - F(0).
        area = (intercept + slope * target + intercept) * target / 2
        return initial + area
    check_figure(task)
    vertices = visible_vertices(task)
    if family_id == "tangent-from-two-points":
        (a, ya), (b, yb) = vertices
        tangent = next(line for line in task["figure"]["lines"] if line.get("dashed"))
        points = figure_points(tangent)
        assert interpolate(points, a) == ya and interpolate(points, b) == yb
        slope = (yb - ya) / (b - a)
        match = re.search(r"Найдите f′\((-?[0-9]+)\)", statement)
        assert match is not None
        contact = fraction(match[1])
        curve = next(line for line in task["figure"]["lines"] if not line.get("dashed"))
        samples = dict(figure_points(curve))
        assert samples[contact] == interpolate(points, contact)
        assert (samples[contact + 1] - samples[contact - 1]) / 2 == slope
        assert all(y >= interpolate(points, x) for x, y in samples.items())
        return slope
    points = figure_points(task["figure"]["lines"][0])
    assert points == vertices
    if family_id == "piecewise-function-value":
        match = re.search(r"Найдите f\(([0-9]+)\)", statement)
        assert match is not None
        argument = fraction(match[1])
        assert argument not in {x for x, _ in points}
        return interpolate(points, argument)
    if family_id == "derivative-positive-length":
        assert "график производной f′" in statement and "возрастания f" in statement
        match = re.search(r"возрастания f на \((-?[0-9]+); (-?[0-9]+)\)", statement)
        assert match is not None
        assert (fraction(match[1]), fraction(match[2])) == (points[0][0], points[-1][0])
        total = Fraction()
        for (left, y_left), (right, y_right) in zip(points, points[1:], strict=False):
            if y_left > 0 and y_right > 0:
                total += right - left
            elif y_left * y_right < 0:
                zero = left - y_left * (right - left) / (y_right - y_left)
                assert left < zero < right and interpolate(points, zero) == 0
                total += right - zero if y_right > 0 else zero - left
        assert 0 < total < points[-1][0] - points[0][0]
        return total
    if family_id == "derivative-turning-point":
        assert "график производной f′" in statement and "точки минимума f" in statement
        (left, y_left), (right, y_right) = points
        match = re.search(r"На интервале \((-?[0-9]+); (-?[0-9]+)\)", statement)
        assert match is not None
        assert (fraction(match[1]), fraction(match[2])) == (left, right)
        assert y_left < 0 < y_right
        zero = (left * y_right - right * y_left) / (y_right - y_left)
        assert left < zero < right and interpolate(points, zero) == 0
        assert interpolate(points, (left + zero) / 2) < 0
        assert interpolate(points, (right + zero) / 2) > 0
        return zero
    assert family_id == "integral-signed-areas"
    assert "определённый интеграл" in statement
    match = re.search(r"интеграл ∫ от ([0-9]+) до ([0-9]+) f\(x\) dx", statement)
    assert match is not None
    assert (fraction(match[1]), fraction(match[2])) == (points[0][0], points[-1][0])
    assert min(y for _, y in points) < 0 < max(y for _, y in points)
    return sum((b - a) * (ya + yb) / 2
               for (a, ya), (b, yb) in zip(points, points[1:], strict=False))


def test_tangent_derivative_comes_from_the_visible_line():
    task = families()["tangent-from-two-points"].generate(0, PROFILE)
    assert "A(-7; 0), B(-3; 2)" in task["statement"]
    assert calculus_oracle(task) == fraction(task["answer"]) == Fraction(1, 2)


@pytest.mark.parametrize("seed", range(10))
def test_calculus_figures_domains_and_signed_integrals(seed):
    members = [family for family in families().values() if family.slot == 9]
    assert len(members) == 6
    for family in members:
        task = family.generate(seed, PROFILE)
        assert fraction(task["answer"]) == calculus_oracle(task)


RUNTIME_IDS = (
    "distribution-weighted-mean", "distribution-weighted-variance",
    "rational-excluded-root", "radical-extraneous-root",
    "power-product-quotient", "rational-removable-factor",
    "tangent-from-two-points", "derivative-turning-point",
)
MAX_SEED = 2**32 - 1
# Multiplication by an odd number is a permutation of the unsigned 32-bit domain.
RUNTIME_SEEDS = tuple((index * 2654435761) & MAX_SEED for index in range(1000)) + (MAX_SEED,)
ORACLES = {6: distribution_oracle, 7: equation_oracle,
           8: transformation_oracle, 9: calculus_oracle}


def check_task_contract(task, family, seed):
    assert task["generation"] == {
        "template_id": family.id, "template_version": "1", "seed": seed,
    }
    assert task["id"] == f"course-{family.id}-{seed}"
    assert task["family_id"] == family.id and task["slot"] == family.slot
    assert task["skill_ids"] == list(family.skill_ids)
    assert task["profile_id"] == PROFILE.id
    assert task["review_status"] == "demo" and task["source"]["reviewed_by"] is None
    assert task["rounding"] is None
    assert re.fullmatch(r"-?[0-9]+(?:,[0-9]+)?", task["answer"])
    assert len(task["answer"]) <= 64
    assert len(set(task["hints"])) == task["hint_count"] == 3
    assert all(text.strip() for text in [task["statement"], *task["hints"], *task["solution"]])
    assert len(task["solution"]) >= 3
    assert json.loads(json.dumps(task, ensure_ascii=False, allow_nan=False)) == task


def test_manifest_covers_actual_profile_matrix_and_exact_runtime_quota():
    from app.generators.algebra_analysis import FAMILIES

    assert isinstance(FAMILIES, tuple) and len(FAMILIES) == len(families()) == 25
    assert Counter(family.slot for family in FAMILIES) == {6: 9, 7: 5, 8: 5, 9: 6}
    assert {family.id for family in FAMILIES if family.supports_runtime} == set(RUNTIME_IDS)
    assert Counter(family.slot for family in FAMILIES if family.supports_runtime) == {
        6: 2, 7: 2, 8: 2, 9: 2,
    }
    for slot in PROFILE.slots:
        if slot.number not in ORACLES:
            continue
        expected = {skill.id for skill in slot.skills}
        actual = {skill for family in FAMILIES if family.slot == slot.number
                  for skill in family.skill_ids}
        assert actual == expected
    assert sum(len(slot.skills) for slot in PROFILE.slots if slot.number in ORACLES) == 29
    for family in FAMILIES:
        assert re.fullmatch(r"[a-z]+(?:-[a-z]+)*", family.id)
        assert len(family.skill_ids) == len(set(family.skill_ids))


@pytest.mark.parametrize("family_id", RUNTIME_IDS)
def test_runtime_templates_on_a_thousand_distinct_seeds_and_upper_boundary(family_id):
    assert len(set(RUNTIME_SEEDS)) == 1001 and 0 in RUNTIME_SEEDS and MAX_SEED in RUNTIME_SEEDS
    family = families()[family_id]
    for seed in RUNTIME_SEEDS:
        task = family.generate(seed, PROFILE)
        check_task_contract(task, family, seed)
        assert fraction(task["answer"]) == ORACLES[family.slot](task), (family_id, seed)
        assert family.generate(seed, PROFILE) == task, (family_id, seed)


@pytest.mark.parametrize("slot", (6, 7, 8, 9))
def test_ten_distinct_visible_models_per_family_and_static_boundaries(slot):
    for family in families().values():
        if family.slot != slot:
            continue
        models = set()
        for seed in (*range(10), MAX_SEED):
            task = family.generate(seed, PROFILE)
            check_task_contract(task, family, seed)
            assert fraction(task["answer"]) == ORACLES[slot](task)
            if seed < 10:
                model = {key: task[key] for key in ("statement", "formula", "table", "figure")}
                models.add(json.dumps(model, ensure_ascii=False, sort_keys=True))
        assert len(models) == 10, family.id


@pytest.mark.parametrize("invalid_seed", (-1, 2**32, True, 1.5, "0", None))
def test_every_public_generator_rejects_invalid_seeds(invalid_seed):
    for family in families().values():
        with pytest.raises(ValueError, match="unsigned 32-bit"):
            family.generate(invalid_seed, PROFILE)


def test_weighted_mean_has_authored_theory_and_separate_practice():
    from app.generators.algebra_analysis import build_lessons

    lesson = next(item for item in build_lessons(PROFILE)
                  if item["id"] == "course-distribution-weighted-mean")
    assert lesson["example"]["statement"] == (
        "X принимает значения 0, 3 и 8 с вероятностями 0,25, 0,5 и 0,25. Найдите M(X)."
    )
    assert fraction(lesson["example"]["answer"]) == Fraction(7, 2)
    text = " ".join(section["body"] for section in lesson["sections"])
    text += " " + lesson["example"]["statement"] + " " + " ".join(lesson["example"]["steps"])
    assert 350 <= len(re.findall(r"[А-Яа-яЁё]+", text)) <= 600
    assert lesson["practice_task_ids"] == [f"course-distribution-weighted-mean-{i}"
                                           for i in range(3)]


# Hand-worked exact examples, kept independently of generator parameters/checker code.
# These automated oracles do not constitute independent human subject review.
WORKED_ORACLES = {
    "distribution-missing-probability": (
        "X принимает только значения 1, 4 и 9 с вероятностями 0,15, p и 0,35. Найдите p.",
        Fraction(1, 2),
    ),
    "distribution-weighted-mean": (
        "X принимает значения 0, 3 и 8 с вероятностями 0,25, 0,5 и 0,25. Найдите M(X).",
        Fraction(7, 2),
    ),
    "distribution-weighted-variance": (
        "X принимает значения 1, 3 и 5 с вероятностями 0,25, 0,5 и 0,25. Найдите D(X).", 2,
    ),
    "distribution-two-point-deviation": (
        "X принимает значения 4 и 12, каждое с вероятностью 0,5. Найдите σ(X).", 4,
    ),
    "distribution-step-cdf": (
        "X принимает значения 1, 4 и 9 с вероятностями 0,2, 0,5 и 0,3. "
        "При F(t) = P(X ≤ t) найдите F(4).", Fraction(7, 10),
    ),
    "distribution-linear-density": (
        "Плотность равна c·x на [0; 5] и нулю вне этого отрезка. Найдите c.", Fraction(2, 25),
    ),
    "distribution-uniform-interval": (
        "X равномерно распределена на [10; 50]. Найдите P(18 ≤ X ≤ 34).", Fraction(2, 5),
    ),
    "distribution-exponential-survival": (
        "T имеет показательное распределение с λ = 3 мин⁻¹. "
        "Найдите P(T > ln(8)/3).", Fraction(1, 8),
    ),
    "distribution-normal-symmetry": (
        "X нормально распределена с μ = 40. Известно точное значение "
        "P(34 < X < 46) = 0,76. Найдите P(X ≥ 46).", Fraction(3, 25),
    ),
    "rational-excluded-root": (
        "Решите уравнение (x² − 11x + 24)/(x − 3) = 0.", 8,
    ),
    "radical-extraneous-root": ("Решите уравнение √(x + 11) = x − 1.", 5),
    "exponential-common-base": ("Решите уравнение 3^(2x − 5) = 9^2.", Fraction(9, 2)),
    "logarithmic-product-domain": (
        "Решите уравнение log_2(x − 6) + log_2(x + 6) = log_2(64).", 10,
    ),
    "absolute-value-selected-root": (
        "Решите уравнение |x − 12| = 5. Укажите меньший корень.", 7,
    ),
    "power-product-quotient": ("Вычислите (7^6 · 7^(-3))/7.", 49),
    "radical-conjugates": ("Вычислите (√37 + 4)(√37 − 4).", 21),
    "rational-removable-factor": (
        "Найдите значение (x² − 49)/(x − 7) при x = 11.", 18,
    ),
    "logarithm-difference": ("Вычислите log_3(405) − log_3(5).", 4),
    "trigonometric-double-angle": (
        "Найдите 169·sin(2α), если sin α = 5/13 и π/2 < α < π.", -120,
    ),
    "piecewise-function-value": (
        "График f — ломаная с вершинами A(2; 1), B(8; 7), C(12; 3). Найдите f(5).", 4,
    ),
    "derivative-positive-length": (
        "График f′ — ломаная A(0; -3), B(4; 3), C(8; -3), D(12; 3). "
        "Найдите суммарную длину промежутков возрастания f на (0; 12).", 6,
    ),
    "tangent-from-two-points": (
        "Касательная к графику f при x = 0 проходит через A(-2; 7) и B(2; 1). "
        "Найдите f′(0).", Fraction(-3, 2),
    ),
    "derivative-turning-point": (
        "График f′ на (1; 7) — отрезок от A(1; -4) до B(7; 8). "
        "Найдите абсциссу точки минимума f.", 3,
    ),
    "antiderivative-initial-value": (
        "F — первообразная f(x) = 4x + 3. Известно F(0) = 5. Найдите F(2).", 19,
    ),
    "integral-signed-areas": (
        "График f — ломаная A(0; -2), B(4; 0), C(8; 3), D(12; 0). "
        "Найдите интеграл от 0 до 12 функции f.", 8,
    ),
}


def visible_numbers(statement, table=None):
    if table:
        statement += " " + " ".join(cell for row in table["rows"] for cell in row)
    return sorted(fraction(number) for number in
                  re.findall(r"-?[0-9]+(?:,[0-9]+)?", statement.replace("−", "-")))


def test_all_family_lessons_have_substantive_theory_and_literal_worked_oracles():
    from app.generators.algebra_analysis import build_lessons

    lessons = build_lessons(PROFILE)
    assert len(lessons) == len(WORKED_ORACLES) == len(families())
    assert {lesson["id"] for lesson in lessons} == {f"course-{key}" for key in families()}
    for lesson in lessons:
        assert set(lesson) == {
            "id", "title", "slot", "minutes", "skill_ids", "sections", "example", "takeaway",
            "family_ids", "practice_task_ids",
        }
        family_id = lesson["id"].removeprefix("course-")
        family = families()[family_id]
        assert lesson["slot"] == family.slot
        assert lesson["family_ids"] == [family.id]
        assert lesson["skill_ids"] == list(family.skill_ids)
        assert 3 <= lesson["minutes"] <= 7
        assert lesson["practice_task_ids"] == [f"course-{family.id}-{seed}" for seed in range(3)]
        for section in lesson["sections"]:
            assert set(section) == {"heading", "body", "formula"}
            assert section["heading"].strip() and section["body"].strip()
            assert section["formula"] is None or isinstance(section["formula"], str)
        statement, expected = WORKED_ORACLES[family_id]
        assert lesson["example"]["statement"] == statement
        assert fraction(lesson["example"]["answer"]) == expected, family_id
        assert len(lesson["example"]["steps"]) >= 3
        text = " ".join(section["body"] for section in lesson["sections"])
        text += " " + statement + " " + " ".join(lesson["example"]["steps"])
        count = len(re.findall(r"[А-Яа-яЁё]+", text))
        assert 350 <= count <= 600, (family_id, count)
        practice = [family.generate(seed, PROFILE) for seed in range(3)]
        assert all(task["statement"] != statement for task in practice), family_id
        # Rephrasing the same numerical problem is not a separate worked example.
        assert all(visible_numbers(task["statement"], task["table"]) != visible_numbers(statement)
                   for task in practice), family_id
        assert len({json.dumps({key: task[key] for key in ("statement", "table", "figure")},
                               ensure_ascii=False, sort_keys=True) for task in practice}) == 3


def test_lesson_outputs_are_fresh_snapshots():
    from app.generators.algebra_analysis import build_lessons

    first = build_lessons(PROFILE)
    expected = build_lessons(PROFILE)
    first[0]["sections"][0]["body"] = "Changed by a caller"
    first[0]["example"]["steps"].append("Changed by a caller")
    first[0]["practice_task_ids"].clear()
    assert build_lessons(PROFILE) == expected


def test_tangent_template_includes_negative_derivatives():
    task = families()["tangent-from-two-points"].generate(17, PROFILE)
    assert fraction(task["answer"]) == calculus_oracle(task) == Fraction(-1, 2)


def test_logarithm_formulas_preserve_multidigit_bases_and_visible_arguments():
    task = families()["logarithm-difference"].generate(8, PROFILE)
    assert task["statement"] == "Вычислите log_10(1100) − log_10(11)."
    assert task["formula"] == r"\log_{10}(1100)-\log_{10}(11)"
    assert transformation_oracle(task) == fraction(task["answer"]) == 2
    task = families()["logarithmic-product-domain"].generate(0, PROFILE)
    assert task["formula"] == r"\log_{2}(x-1)+\log_{2}(x+1)=\log_{2}(8)"
    assert equation_oracle(task) == fraction(task["answer"]) == 3


def test_shard_loads_through_the_real_content_contract_with_its_practice_links():
    from app.content import validate_content
    from app.generators.algebra_analysis import build_lessons

    content_dir = PROFILE_PATH.parent
    initial_lessons = json.loads((content_dir / "lessons.json").read_text(encoding="utf-8"))
    initial_tasks = json.loads((content_dir / "tasks.json").read_text(encoding="utf-8"))
    lessons = build_lessons(PROFILE)
    tasks = [family.generate(seed, PROFILE) for family in families().values() for seed in range(10)]
    bundle = validate_content(
        PROFILE.model_dump(), initial_lessons + lessons, initial_tasks + tasks,
    )
    authored_ids = {lesson["id"] for lesson in lessons}
    assert len(tasks) == 250 and len(authored_ids) == 25
    assert authored_ids <= {lesson.id for lesson in bundle.lessons}
    for lesson in bundle.lessons:
        if lesson.id in authored_ids:
            assert lesson.reviewed_by is None and lesson.review_status == "demo"
            assert len(lesson.practice_task_ids) == 3
    assert all(task.source.reviewed_by is None for task in bundle.tasks
               if task.family_id in families())
