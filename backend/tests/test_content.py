"""Проверки статического демобанка без импорта серверного проверяющего кода.

Числовые данные извлекаются из условий и таблиц. Эталоны вычисляются заново
через Fraction и Decimal, а не берутся из решений или серверного генератора.
Это независимый способ вычисления, но не независимая предметная рецензия.
"""

import json
import re
from collections import Counter
from collections.abc import Callable
from datetime import date
from decimal import Decimal, localcontext
from fractions import Fraction
from math import isqrt
from pathlib import Path
from urllib.parse import urlsplit

import pytest

CONTENT_DIR = Path(__file__).resolve().parents[1] / "content"
PROFILE_ID = "ege-math-2027-draft"
PROFILE_REVISION = "2026-11-05.1"
NUMBER = r"[0-9]+(?:,[0-9]+)?"
STABLE_ID = re.compile(r"[a-z]+(?:-[a-z]+)*")


def _object_without_duplicates(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        assert key not in result, f"Повторяющийся ключ JSON: {key}"
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> None:
    raise ValueError(f"Недопустимое значение JSON: {value}")


def _load_json(name: str):
    return json.loads(
        (CONTENT_DIR / name).read_text(encoding="utf-8"),
        object_pairs_hook=_object_without_duplicates,
        parse_float=Decimal,
        parse_constant=_reject_nonfinite_constant,
    )


PROFILE = _load_json("profile.json")
LESSONS = _load_json("lessons.json")
TASKS = _load_json("tasks.json")
SLOTS = {slot["number"]: slot for slot in PROFILE["slots"]}

# Полная обязательная матрица из раздела 4.1 ТЗ, а не только навыки демозадач.
REQUIRED_SKILLS = {
    1: {
        "plane-angles",
        "plane-triangles",
        "plane-quadrilaterals",
        "plane-circles",
        "plane-similarity",
        "plane-lengths",
        "plane-areas",
        "plane-theorem-choice",
    },
    2: {
        "vector-coordinates",
        "vector-length",
        "vector-addition",
        "vector-subtraction",
        "vector-scaling",
        "vector-dot-product",
        "vector-angle",
    },
    3: {
        "solid-prism",
        "solid-pyramid",
        "solid-parallelepiped",
        "solid-cylinder",
        "solid-cone",
        "solid-sphere",
        "solid-volume",
        "solid-surface-area",
        "solid-ratios",
    },
    4: {
        "probability-equiprobable",
        "probability-event",
        "probability-complement",
        "probability-event-boundaries",
    },
    5: {
        "probability-addition",
        "probability-multiplication",
        "probability-independence",
        "probability-conditional",
        "probability-total",
        "probability-event-tree",
        "probability-combinatorics",
    },
    6: {
        "distribution-table",
        "distribution-expectation",
        "distribution-variance",
        "distribution-standard-deviation",
        "distribution-cdf",
        "distribution-density",
        "distribution-uniform",
        "distribution-exponential",
        "distribution-normal",
    },
    7: {
        "equation-rational",
        "equation-irrational",
        "equation-exponential",
        "equation-logarithmic",
        "equation-other-short-answer",
        "equation-domain",
        "equation-root-selection",
    },
    8: {
        "algebra-powers",
        "algebra-roots",
        "algebra-rational-expressions",
        "algebra-logarithms",
        "algebra-trigonometry",
        "algebra-exact-computation",
    },
    9: {
        "calculus-function-graph",
        "calculus-derivative-graph",
        "calculus-tangent",
        "calculus-monotonicity",
        "calculus-extrema",
        "calculus-antiderivative",
        "calculus-integral",
    },
    10: {
        "applied-substitution",
        "applied-isolate-variable",
        "applied-simple-model",
        "applied-units",
        "applied-constraints",
        "applied-plausibility",
    },
    11: {
        "word-motion",
        "word-work-rate",
        "word-mixtures",
        "word-equation-model",
        "word-system-model",
    },
    12: {
        "function-reconstruction",
        "function-values",
        "function-parameters",
        "function-intersections",
        "function-graph-properties",
    },
    13: {
        "finance-percentages",
        "finance-period-changes",
        "finance-credit",
        "finance-deposits",
        "finance-payments",
        "finance-personal-family-budget",
        "finance-other-models",
    },
}

SLOT_TITLES = {
    1: "Планиметрия",
    2: "Векторы и координаты",
    3: "Стереометрия",
    4: "Вероятность: базовые модели",
    5: "Вероятность: составные модели",
    6: "Случайные величины и распределения",
    7: "Уравнения",
    8: "Вычисления и преобразования",
    9: "Производная и математический анализ",
    10: "Прикладные зависимости и формулы",
    11: "Текстовые задачи",
    12: "Функции и графики",
    13: "Моделирование и финансовые задачи",
}

FAMILY_COUNTS = {
    "right-triangle-area": (1, 5),
    "vector-dot-product": (2, 5),
    "prism-volume": (3, 5),
    "probability-complement-count": (4, 5),
    "probability-independent-both": (5, 5),
    "distribution-expectation": (6, 3),
    "distribution-variance": (6, 2),
    "logarithmic-shift": (7, 5),
    "difference-squares-quotient": (8, 5),
    "quadratic-tangent-slope": (9, 5),
    "kinetic-energy-speed": (10, 5),
    "motion-catch-up": (11, 5),
    "linear-function-two-points": (12, 5),
    "deposit-simple-interest": (13, 3),
    "sequential-discounts": (13, 2),
}

FAMILY_SKILLS = {
    "right-triangle-area": {
        "plane-triangles",
        "plane-lengths",
        "plane-areas",
        "plane-theorem-choice",
    },
    "vector-dot-product": {"vector-coordinates", "vector-dot-product"},
    "prism-volume": {"solid-prism", "solid-volume"},
    "probability-complement-count": {
        "probability-equiprobable",
        "probability-event",
        "probability-complement",
    },
    "probability-independent-both": {
        "probability-multiplication",
        "probability-independence",
    },
    "distribution-expectation": {"distribution-table", "distribution-expectation"},
    "distribution-variance": {
        "distribution-table",
        "distribution-expectation",
        "distribution-variance",
    },
    "logarithmic-shift": {
        "equation-logarithmic",
        "equation-domain",
        "equation-root-selection",
    },
    "difference-squares-quotient": {
        "algebra-rational-expressions",
        "algebra-exact-computation",
    },
    "quadratic-tangent-slope": {"calculus-tangent"},
    "kinetic-energy-speed": {
        "applied-substitution",
        "applied-isolate-variable",
        "applied-units",
        "applied-constraints",
        "applied-plausibility",
    },
    "motion-catch-up": {"word-motion", "word-equation-model"},
    "linear-function-two-points": {
        "function-reconstruction",
        "function-values",
        "function-parameters",
    },
    "deposit-simple-interest": {
        "finance-percentages",
        "finance-period-changes",
        "finance-deposits",
    },
    "sequential-discounts": {"finance-percentages", "finance-period-changes"},
}


def _nonempty_text(value: str) -> None:
    assert isinstance(value, str)
    assert value.strip()
    assert value == value.strip()
    assert not any(ord(character) < 32 for character in value)


def _fraction(text: str) -> Fraction:
    return Fraction(text.replace("−", "-").replace(",", "."))


def _exam_number(text: str) -> Fraction:
    _nonempty_text(text)
    assert len(text) <= 64
    assert re.fullmatch(r"-?[0-9]+(?:[,.][0-9]+)?", text)
    decimal = Decimal(text.replace(",", "."))
    assert decimal.is_finite()
    result = Fraction(decimal)
    denominator = result.denominator
    for prime in (2, 5):
        while denominator % prime == 0:
            denominator //= prime
    assert denominator == 1
    return result


def _capture(pattern: str, text: str) -> tuple[str, ...]:
    match = re.fullmatch(pattern, text)
    assert match is not None, f"Условие не соответствует проверяемой модели: {text}"
    return match.groups()


def _exact_square_root(value: Fraction) -> Fraction:
    assert value >= 0
    numerator = isqrt(value.numerator)
    denominator = isqrt(value.denominator)
    assert numerator * numerator == value.numerator
    assert denominator * denominator == value.denominator
    return Fraction(numerator, denominator)


def _right_triangle_area(task: dict) -> Fraction:
    c, a = map(
        _fraction,
        _capture(
            rf"В прямоугольном треугольнике гипотенуза равна ({NUMBER}) см, "
            rf"один из катетов равен ({NUMBER}) см\. Найдите площадь треугольника "
            r"в квадратных сантиметрах\.",
            task["statement"],
        ),
    )
    assert c > a > 0
    b = _exact_square_root(c * c - a * a)
    assert b > 0
    assert a + b > c and a + c > b and b + c > a
    semiperimeter = (a + b + c) / 2
    # Формула Герона даёт дополнительную проверку площади без использования эталона.
    area_squared = semiperimeter * (semiperimeter - a) * (semiperimeter - b)
    area_squared *= semiperimeter - c
    area = _exact_square_root(area_squared)
    assert area == a * b / 2
    return area


def _vector_dot_product(task: dict) -> Fraction:
    ax, ay, bx, by = map(
        _fraction,
        _capture(
            r"Даны векторы a = \((−?[0-9]+); (−?[0-9]+)\) и "
            r"b = \((−?[0-9]+); (−?[0-9]+)\)\. "
            r"Найдите скалярное произведение a · b\.",
            task["statement"],
        ),
    )
    assert ax * ax + ay * ay > 0
    assert bx * bx + by * by > 0
    return ax * bx + ay * by


def _prism_volume(task: dict) -> Fraction:
    area, height = map(
        _fraction,
        _capture(
            rf"Площадь основания прямой призмы равна ({NUMBER}) см², "
            rf"а высота равна ({NUMBER}) см\. Найдите объём призмы "
            r"в кубических сантиметрах\.",
            task["statement"],
        ),
    )
    assert area > 0 and height > 0
    return area * height


def _probability_complement(task: dict) -> Fraction:
    total_text, red_text = _capture(
        r"В мешке ([0-9]+) одинаковых на ощупь жетонов, из них ([0-9]+) красных, "
        r"остальные синие\. Один жетон выбирают равновероятно\. "
        r"Найдите вероятность того, что он не красный\.",
        task["statement"],
    )
    total, red = int(total_text), int(red_text)
    assert 0 <= red <= total and total > 0
    return Fraction(total - red, total)


def _probability_independent_both(task: dict) -> Fraction:
    first, second = map(
        _fraction,
        _capture(
            rf"Вероятность срабатывания первого датчика равна ({NUMBER}), "
            rf"второго — ({NUMBER})\. Датчики срабатывают независимо\. "
            r"Найдите вероятность того, что сработают оба датчика\.",
            task["statement"],
        ),
    )
    assert 0 <= first <= 1 and 0 <= second <= 1
    result = first * second
    assert 0 <= result <= min(first, second)
    return result


def _distribution(task: dict, question: str) -> list[tuple[Fraction, Fraction]]:
    _capture(
        r"Случайная величина X — [^.]+\. Её распределение дано в таблице\. "
        rf"Найдите {question} X\.",
        task["statement"],
    )
    assert task["table"]["headers"] == ["Значение X", "Вероятность"]
    rows = [tuple(map(_fraction, row)) for row in task["table"]["rows"]]
    assert len(rows) >= 2
    assert len({value for value, _ in rows}) == len(rows)
    assert all(value >= 0 and value.denominator == 1 for value, _ in rows)
    assert all(0 <= probability <= 1 for _, probability in rows)
    assert sum((probability for _, probability in rows), Fraction()) == 1
    return rows


def _distribution_expectation(task: dict) -> Fraction:
    rows = _distribution(task, "математическое ожидание")
    expectation = sum((value * probability for value, probability in rows), Fraction())
    values = [value for value, _ in rows]
    assert min(values) <= expectation <= max(values)
    return expectation


def _distribution_variance(task: dict) -> Fraction:
    rows = _distribution(task, "дисперсию")
    expectation = sum((value * probability for value, probability in rows), Fraction())
    # Основной расчёт здесь идёт через отклонения, а не через формулу из решения.
    variance = sum(
        ((value - expectation) ** 2 * probability for value, probability in rows),
        Fraction(),
    )
    pairwise = (
        sum(
            ((x - y) ** 2 * px * py for x, px in rows for y, py in rows),
            Fraction(),
        )
        / 2
    )
    assert variance == pairwise and variance >= 0
    return variance


def _logarithmic_shift(task: dict) -> Fraction:
    base_text, shift_text, exponent_text = _capture(
        r"Решите уравнение log([₂₃₅₇])\(x − ([0-9]+)\) = (−?[0-9]+)\.",
        task["statement"],
    )
    base = int(base_text.translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")))
    shift = int(shift_text)
    exponent = int(exponent_text.replace("−", "-"))
    assert base > 0 and base != 1
    root = Fraction(shift) + Fraction(base) ** exponent
    assert root > shift
    assert root - shift == Fraction(base) ** exponent
    assert task["formula"] == rf"\log_{base}(x-{shift})={exponent}"
    return root


def _difference_squares_quotient(task: dict) -> Fraction:
    square_text, shift_text, x_text = _capture(
        r"Найдите значение выражения \(x² − ([0-9]+)\)/\(x − ([0-9]+)\) "
        r"при x = (−?[0-9]+)\.",
        task["statement"],
    )
    square, shift, x = map(_fraction, (square_text, shift_text, x_text))
    assert square == shift * shift and x != shift
    assert task["formula"] == rf"\frac{{x^2-{square}}}{{x-{shift}}},\qquad x={x}"
    # Прямая подстановка проверяет результат независимо от сокращения в решении.
    return (x * x - square) / (x - shift)


def _quadratic_tangent_slope(task: dict) -> Fraction:
    expression, x_text = _capture(
        r"Дана функция f\(x\) = (.+)\. Найдите угловой коэффициент касательной "
        r"к её графику в точке с абсциссой x₀ = (−?[0-9]+)\.",
        task["statement"],
    )
    a_text, b_sign, b_text, c_sign, c_text = _capture(
        r"(−?[0-9]*)x² ([+−]) ([0-9]*)x ([+−]) ([0-9]+)",
        expression,
    )
    a = _fraction("−1" if a_text == "−" else a_text or "1")
    b = _fraction(b_text or "1") * (-1 if b_sign == "−" else 1)
    c = _fraction(c_text) * (-1 if c_sign == "−" else 1)
    x = _fraction(x_text)
    assert a != 0

    def polynomial(value: Fraction) -> Fraction:
        return a * value * value + b * value + c

    # Для квадратичного многочлена симметричная разность даёт производную точно.
    # Для произвольной функции это было бы лишь приближением.
    slope = (polynomial(x + 1) - polynomial(x - 1)) / 2
    assert slope == 2 * a * x + b
    latex = expression.replace(" ", "").replace("−", "-").replace("²", "^2")
    assert task["formula"] == rf"f(x)={latex},\qquad x_0={x}"
    return slope


def _kinetic_energy_speed(task: dict) -> Fraction:
    mass, energy = map(
        _fraction,
        _capture(
            r"В модели кинетическая энергия тела вычисляется по формуле E = mv²/2, "
            r"где E измеряется в джоулях, m — в килограммах, v — в м/с\. "
            rf"Масса тела равна ({NUMBER}) кг, энергия равна ({NUMBER}) Дж\. "
            r"Найдите модуль скорости тела в м/с\.",
            task["statement"],
        ),
    )
    assert mass > 0 and energy >= 0
    speed = _exact_square_root(2 * energy / mass)
    assert speed >= 0 and mass * speed * speed / 2 == energy
    assert task["formula"] == r"E=\frac{mv^2}{2}"
    return speed


def _motion_catch_up(task: dict) -> Fraction:
    slow, gap, fast = map(
        _fraction,
        _capture(
            rf"Пешеход идёт со скоростью ({NUMBER}) км/ч\. В начальный момент "
            rf"велосипедист находится на той же дороге на ({NUMBER}) км позади пешехода "
            rf"и начинает ехать вслед за ним со скоростью ({NUMBER}) км/ч\. "
            r"Оба движутся в одном направлении с постоянными скоростями без остановок\. "
            r"Через сколько часов после этого момента велосипедист догонит пешехода\?",
            task["statement"],
        ),
    )
    assert fast > slow > 0 and gap > 0
    hours = gap / (fast - slow)
    assert hours > 0 and fast * hours == gap + slow * hours
    return hours


def _linear_function_two_points(task: dict) -> Fraction:
    x1, y1, x2, y2, target = map(
        _fraction,
        _capture(
            r"График линейной функции f\(x\) = kx \+ b проходит через точки "
            r"A\((−?[0-9]+); (−?[0-9]+)\) и B\((−?[0-9]+); (−?[0-9]+)\)\. "
            r"Найдите f\((−?[0-9]+)\)\. Координаты точек заданы точно; рисунок не требуется\.",
            task["statement"],
        ),
    )
    assert x1 != x2
    assert task["formula"] == "f(x)=kx+b"

    def interpolate(value: Fraction) -> Fraction:
        return (y1 * (x2 - value) + y2 * (value - x1)) / (x2 - x1)

    # Интерполяция проверяет ответ без чтения коэффициентов из готового решения.
    assert interpolate(x1) == y1 and interpolate(x2) == y2
    return interpolate(target)


def _deposit_simple_interest(task: dict) -> Fraction:
    principal_text, rate_text, years_text, repeated_rate, repeated_years = _capture(
        rf"В учебной модели на вклад внесли ({NUMBER}) рублей под ({NUMBER})% годовых "
        r"на ([0-9]+) года\. Проценты простые: за каждый полный год начисляют "
        rf"({NUMBER})% только от первоначальной суммы; проценты не капитализируются\. "
        r"Пополнений, снятий, комиссий и налогов нет\. Найдите общую сумму вклада "
        r"и начисленных процентов через ([0-9]+) года в рублях\.",
        task["statement"],
    )
    assert rate_text == repeated_rate and years_text == repeated_years
    years = int(years_text)
    assert years > 0
    with localcontext() as context:
        context.prec = 50
        principal = Decimal(principal_text.replace(",", "."))
        rate = Decimal(rate_text.replace(",", ".")) / Decimal(100)
        assert principal > 0 and 0 < rate < 1
        total = principal
        # Каждый период проверяется отдельно; база начисления не капитализируется.
        for _ in range(years):
            total += principal * rate
    assert total > principal
    return Fraction(total)


def _sequential_discounts(task: dict) -> Fraction:
    price_text, first_text, second_text = _capture(
        rf"Товар стоил ({NUMBER}) рублей\. В первый день его цену снизили на "
        rf"({NUMBER})%\. Во второй день новую цену снизили ещё на ({NUMBER})%\. "
        r"Других изменений цены нет\. Сколько рублей стоит товар после второго снижения\?",
        task["statement"],
    )
    with localcontext() as context:
        context.prec = 50
        price = Decimal(price_text.replace(",", "."))
        first = Decimal(first_text.replace(",", ".")) / Decimal(100)
        second = Decimal(second_text.replace(",", ".")) / Decimal(100)
        assert price > 0 and 0 < first < 1 and 0 < second < 1
        after_first = price - price * first
        after_second = after_first - after_first * second
    assert 0 < after_second < after_first < price
    return Fraction(after_second)


FAMILY_CHECKS: dict[str, Callable[[dict], Fraction]] = {
    "right-triangle-area": _right_triangle_area,
    "vector-dot-product": _vector_dot_product,
    "prism-volume": _prism_volume,
    "probability-complement-count": _probability_complement,
    "probability-independent-both": _probability_independent_both,
    "distribution-expectation": _distribution_expectation,
    "distribution-variance": _distribution_variance,
    "logarithmic-shift": _logarithmic_shift,
    "difference-squares-quotient": _difference_squares_quotient,
    "quadratic-tangent-slope": _quadratic_tangent_slope,
    "kinetic-energy-speed": _kinetic_energy_speed,
    "motion-catch-up": _motion_catch_up,
    "linear-function-two-points": _linear_function_two_points,
    "deposit-simple-interest": _deposit_simple_interest,
    "sequential-discounts": _sequential_discounts,
}


def test_profile_source_schema_and_honest_verification_note():
    assert set(PROFILE) == {
        "id",
        "year",
        "title",
        "status",
        "revision",
        "verified_at",
        "verification_note",
        "source_urls",
        "slots",
    }
    assert PROFILE["id"] == PROFILE_ID
    assert PROFILE["revision"] == PROFILE_REVISION
    assert PROFILE["year"] == 2027 and type(PROFILE["year"]) is int
    assert PROFILE["status"] == "draft"
    assert "проект" in PROFILE["title"].lower()
    assert date.fromisoformat(PROFILE["verified_at"]) == date(2026, 11, 5)
    note = PROFILE["verification_note"]
    assert "technical-spec.md от 2026-11-05" in note
    assert "перенесены" in note
    assert "ФИПИ независимо повторно не проверялись" in note
    assert len(PROFILE["slots"]) == 13
    assert [slot["number"] for slot in PROFILE["slots"]] == list(range(1, 14))
    assert len({slot["id"] for slot in PROFILE["slots"]}) == 13
    assert len(PROFILE["source_urls"]) == 3
    for url in PROFILE["source_urls"]:
        parsed = urlsplit(url)
        assert parsed.scheme == "https"
        assert parsed.hostname in {"fipi.ru", "doc.fipi.ru"}


@pytest.mark.parametrize("slot", PROFILE["slots"], ids=lambda slot: slot["id"])
def test_slots_keep_full_mandatory_matrix(slot):
    assert set(slot) == {"number", "id", "title", "level", "summary", "skills", "lesson_id"}
    assert type(slot["number"]) is int
    assert STABLE_ID.fullmatch(slot["id"])
    assert slot["title"] == SLOT_TITLES[slot["number"]]
    expected_level = "Б" if slot["number"] in {1, 2, 3, 4, 7, 8, 9} else "П"
    assert slot["level"] == expected_level
    _nonempty_text(slot["summary"])
    skill_ids = [skill["id"] for skill in slot["skills"]]
    assert len(skill_ids) == len(set(skill_ids))
    assert set(skill_ids) == REQUIRED_SKILLS[slot["number"]]
    for skill in slot["skills"]:
        assert set(skill) == {"id", "title"}
        assert STABLE_ID.fullmatch(skill["id"])
        assert "slot" not in skill["id"]
        _nonempty_text(skill["title"])


def test_exact_bank_size_families_and_revisioned_identifiers():
    assert isinstance(TASKS, list) and len(TASKS) == 65
    assert Counter(task["slot"] for task in TASKS) == dict.fromkeys(range(1, 14), 5)
    assert len({task["id"] for task in TASKS}) == 65
    assert len({(task["id"], task["revision"]) for task in TASKS}) == 65
    assert len({task["statement"] for task in TASKS}) == 65
    assert set(FAMILY_CHECKS) == set(FAMILY_COUNTS) == set(FAMILY_SKILLS)
    actual_counts = Counter(task["family_id"] for task in TASKS)
    assert actual_counts == {family: count for family, (_, count) in FAMILY_COUNTS.items()}
    for family, (slot, count) in FAMILY_COUNTS.items():
        members = [task for task in TASKS if task["family_id"] == family]
        assert {task["slot"] for task in members} == {slot}
        assert {task["id"] for task in members} == {
            f"{family}-{letter}" for letter in "abcde"[:count]
        }
    assert sum(len(skills) for skills in REQUIRED_SKILLS.values()) == 87


@pytest.mark.parametrize("task", TASKS, ids=lambda task: task["id"])
def test_task_schema_skill_references_and_demo_metadata(task):
    assert set(task) == {
        "id",
        "revision",
        "slot",
        "topic",
        "title",
        "statement",
        "formula",
        "table",
        "skill_ids",
        "family_id",
        "estimated_seconds",
        "review_status",
        "hint_count",
        "answer",
        "hints",
        "solution",
        "source",
        "profile_id",
        "difficulty",
        "rounding",
    }
    assert STABLE_ID.fullmatch(task["id"])
    assert STABLE_ID.fullmatch(task["family_id"])
    assert task["revision"] == "1"
    assert task["profile_id"] == PROFILE_ID
    assert type(task["slot"]) is int and task["slot"] in SLOTS
    assert task["topic"] == SLOTS[task["slot"]]["title"]
    for field in ("title", "statement"):
        _nonempty_text(task[field])
    assert type(task["estimated_seconds"]) is int and task["estimated_seconds"] > 0
    assert type(task["difficulty"]) is int and task["difficulty"] in {1, 2, 3}
    assert task["review_status"] == "demo" and task["rounding"] is None
    assert type(task["hint_count"]) is int and task["hint_count"] == 3
    assert isinstance(task["hints"], list) and len(task["hints"]) == 3
    assert len(set(task["hints"])) == 3
    assert isinstance(task["solution"], list) and len(task["solution"]) >= 3
    for text in [*task["hints"], *task["solution"]]:
        _nonempty_text(text)
    assert task["solution"][-1] == f"Ответ: {task['answer']}."
    _exam_number(task["answer"])
    assert isinstance(task["skill_ids"], list) and task["skill_ids"]
    assert len(task["skill_ids"]) == len(set(task["skill_ids"]))
    assert set(task["skill_ids"]) <= REQUIRED_SKILLS[task["slot"]]
    assert set(task["skill_ids"]) == FAMILY_SKILLS[task["family_id"]]
    assert set(task["source"]) == {"author", "origin", "rights", "reviewed_by"}
    assert task["source"]["reviewed_by"] is None
    for field in ("author", "origin", "rights"):
        _nonempty_text(task["source"][field])
    assert "ИИ" in task["source"]["author"]
    assert "с помощью ИИ" in task["source"]["origin"]
    assert "независимая предметная проверка не выполнена" in task["source"]["origin"]
    assert "внешняя лицензия и исключительные права не заявляются" in task["source"]["rights"]
    if task["formula"] is not None:
        _nonempty_text(task["formula"])
    else:
        assert task["slot"] not in {7, 8, 9, 10, 12}
    if task["table"] is not None:
        assert task["slot"] == 6
        table = task["table"]
        assert set(table) == {"headers", "rows"}
        assert isinstance(table["headers"], list) and table["headers"]
        assert isinstance(table["rows"], list) and table["rows"]
        for header in table["headers"]:
            _nonempty_text(header)
        for row in table["rows"]:
            assert isinstance(row, list) and len(row) == len(table["headers"])
            for cell in row:
                _nonempty_text(cell)
    else:
        assert task["slot"] != 6


@pytest.mark.parametrize("task", TASKS, ids=lambda task: task["id"])
def test_every_authored_answer_with_independent_exact_arithmetic(task):
    expected = FAMILY_CHECKS[task["family_id"]](task)
    assert isinstance(expected, Fraction)
    assert _exam_number(task["answer"]) == expected, task["id"]


def test_lessons_have_one_entry_per_slot_and_honest_partial_coverage():
    assert isinstance(LESSONS, list) and len(LESSONS) == 13
    assert len({lesson["id"] for lesson in LESSONS}) == 13
    assert Counter(lesson["slot"] for lesson in LESSONS) == dict.fromkeys(range(1, 14), 1)
    covered = {skill for task in TASKS for skill in task["skill_ids"]}
    assert len(covered) == 35
    assert len(covered) < sum(len(skills) for skills in REQUIRED_SKILLS.values())


@pytest.mark.parametrize("lesson", LESSONS, ids=lambda lesson: lesson["id"])
def test_lesson_schema_examples_and_introductory_scope(lesson):
    assert set(lesson) == {
        "id",
        "title",
        "slot",
        "minutes",
        "skill_ids",
        "sections",
        "example",
        "takeaway",
    }
    assert STABLE_ID.fullmatch(lesson["id"])
    assert type(lesson["slot"]) is int and lesson["slot"] in SLOTS
    assert lesson["id"] == SLOTS[lesson["slot"]]["lesson_id"]
    assert lesson["title"].startswith("Вводный урок:")
    assert type(lesson["minutes"]) is int and 1 <= lesson["minutes"] <= 3
    assert isinstance(lesson["skill_ids"], list) and lesson["skill_ids"]
    assert len(lesson["skill_ids"]) == len(set(lesson["skill_ids"]))
    assert set(lesson["skill_ids"]) < REQUIRED_SKILLS[lesson["slot"]]
    actual_practice_skills = {
        skill for task in TASKS if task["slot"] == lesson["slot"] for skill in task["skill_ids"]
    }
    assert set(lesson["skill_ids"]) == actual_practice_skills
    assert isinstance(lesson["sections"], list) and len(lesson["sections"]) >= 2
    assert any(section["formula"] for section in lesson["sections"])
    for section in lesson["sections"]:
        assert set(section) == {"heading", "body", "formula"}
        _nonempty_text(section["heading"])
        _nonempty_text(section["body"])
        if section["formula"] is not None:
            _nonempty_text(section["formula"])
    assert set(lesson["example"]) == {"statement", "steps", "answer"}
    _nonempty_text(lesson["example"]["statement"])
    assert isinstance(lesson["example"]["steps"], list)
    assert len(lesson["example"]["steps"]) >= 3
    for step in lesson["example"]["steps"]:
        _nonempty_text(step)
    _exam_number(lesson["example"]["answer"])
    _nonempty_text(lesson["takeaway"])


# Числа и формулировки разобранных примеров зафиксированы отдельно от JSON-эталонов.
# Значения ниже получены точной арифметикой по этим данным, не серверной проверкой.
EXAMPLE_CASES = {
    1: (
        "Гипотенуза прямоугольного треугольника равна 20 см, один катет — 12 см. "
        "Найдите площадь в квадратных сантиметрах.",
        Fraction(12) * _exact_square_root(Fraction(20**2 - 12**2)) / 2,
    ),
    2: (
        "Даны векторы a = (1; −2) и b = (3; 4). Найдите их скалярное произведение.",
        Fraction(1 * 3 + (-2) * 4),
    ),
    3: (
        "Площадь основания прямой призмы равна 9 см², высота — 4 см. "
        "Найдите объём в кубических сантиметрах.",
        Fraction(9 * 4),
    ),
    4: (
        "Из 10 жетонов 3 белые, остальные зелёные. Один жетон выбирают равновероятно. "
        "Найдите вероятность выбрать не белый жетон.",
        Fraction(10 - 3, 10),
    ),
    5: (
        "Два датчика срабатывают независимо с вероятностями 0,8 и 0,5. "
        "Найдите вероятность срабатывания обоих.",
        Fraction(8, 10) * Fraction(5, 10),
    ),
    6: (
        "X принимает значения 0 и 4 с вероятностями 0,5 и 0,5. Найдите дисперсию X.",
        Fraction((0 - 2) ** 2, 2) + Fraction((4 - 2) ** 2, 2),
    ),
    7: (
        "Решите уравнение log₃(x − 4) = 2.",
        Fraction(4) + Fraction(3) ** 2,
    ),
    8: (
        "Найдите значение (x² − 49)/(x − 7) при x = 10.",
        Fraction(10**2 - 49, 10 - 7),
    ),
    9: (
        "Найдите угловой коэффициент касательной к графику f(x) = x² + 2x + 3 при x₀ = 2.",
        Fraction((3**2 + 2 * 3 + 3) - (1**2 + 2 * 1 + 3), 2),
    ),
    10: (
        "По формуле E = mv²/2 найдите неотрицательную скорость тела массой 2 кг "
        "с энергией 16 Дж. Ответ дайте в м/с.",
        _exact_square_root(Fraction(2 * 16, 2)),
    ),
    11: (
        "Пешеход движется со скоростью 4 км/ч. Велосипедист едет вслед со скоростью "
        "10 км/ч, начальный отрыв пешехода — 9 км. Через сколько часов велосипедист "
        "догонит пешехода?",
        Fraction(9, 10 - 4),
    ),
    12: (
        "График линейной функции проходит через A(0; 1) и B(2; 7). Найдите f(4).",
        Fraction(1 * (2 - 4) + 7 * (4 - 0), 2 - 0),
    ),
    13: (
        "На вклад внесли 10000 рублей под 5% годовых на 2 года. Проценты простые, "
        "без пополнений, снятий, комиссий и налогов. Найдите итоговую сумму в рублях.",
        Fraction(10000) + 2 * Fraction(10000 * 5, 100),
    ),
}


@pytest.mark.parametrize("lesson", LESSONS, ids=lambda lesson: lesson["id"])
def test_worked_example_answer_from_separate_arithmetic(lesson):
    statement, expected = EXAMPLE_CASES[lesson["slot"]]
    assert lesson["example"]["statement"] == statement
    assert _exam_number(lesson["example"]["answer"]) == expected
