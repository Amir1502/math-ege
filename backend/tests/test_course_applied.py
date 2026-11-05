"""Independent condition/figure oracles for the authored slots 10–13 shard.

No generator internals, seed-to-parameter formula, or application answer checker
is used to calculate an expected answer. Money is checked as a cash-flow ledger.
"""

import json
import math
import re
from collections import Counter
from fractions import Fraction
from pathlib import Path

import pytest

from app.generators.applied_finance import FAMILIES, build_lessons
from app.schemas import ProfileSource

MAX_SEED = 2**32 - 1
NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:,[0-9]+)?\Z")
RUSSIAN_WORD = re.compile(r"[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*")
RUNTIME_IDS = {
    "heat-balance", "stopping-distance", "catch-up-motion", "joint-pumps",
    "line-reconstruction", "parabola-vertex", "capitalized-deposit",
    "equal-principal-credit",
}


@pytest.fixture(scope="module")
def profile():
    path = Path(__file__).resolve().parents[1] / "content" / "profile.json"
    return ProfileSource.model_validate_json(path.read_text(encoding="utf-8"))


def number(text):
    assert isinstance(text, str) and NUMBER.fullmatch(text), text
    return Fraction(text.replace(",", "."))


def inputs(task):
    table = task["table"]
    assert table["headers"] == ["Величина", "Значение", "Единица"]
    assert all(len(row) == 3 for row in table["rows"])
    assert len({row[0] for row in table["rows"]}) == len(table["rows"])
    return {name: number(value) for name, value, _unit in table["rows"]}


def units(task, expected):
    actual = {name: unit for name, _value, unit in task["table"]["rows"]}
    assert actual == expected


def exact_sqrt(value):
    value = Fraction(value)
    top, bottom = math.isqrt(value.numerator), math.isqrt(value.denominator)
    assert top * top == value.numerator and bottom * bottom == value.denominator
    return Fraction(top, bottom)


def point(value):
    # str(float) is used only for the bounded visual coordinate representation.
    return Fraction(str(value["x"])), Fraction(str(value["y"]))


def marked_points(task, fallback):
    if task.get("figure") is None:
        return fallback
    actual = [point(circle["center"]) for circle in task["figure"]["circles"]]
    assert actual == fallback, "The accessible numerical data must match the picture"
    return actual


def affine(points):
    (x1, y1), (x2, y2) = points[0], points[-1]
    assert x1 != x2
    slope = (y2 - y1) / (x2 - x1)
    return slope, y1 - slope * x1


def oracle(task):
    """Solve the published condition, including physical and financial constraints."""
    p = inputs(task)
    family = task["family_id"]
    if family == "heat-balance":
        units(task, {"Масса воды": "г", "Удельная теплоёмкость": "Дж/(кг·°C)",
                     "Начальная температура": "°C", "Конечная температура": "°C"})
        assert p["Масса воды"] > 0 and p["Удельная теплоёмкость"] > 0
        assert 0 < p["Начальная температура"] < p["Конечная температура"] < 100
        joules = (p["Масса воды"] / 1000 * p["Удельная теплоёмкость"]
                  * (p["Конечная температура"] - p["Начальная температура"]))
        return joules / 1000
    if family == "pressure-force":
        units(task, {"Давление": "кПа", "Площадь": "см²"})
        assert all(value > 0 for value in p.values())
        area_meters = p["Площадь"] / 10000
        force = p["Давление"] * 1000 * area_meters
        assert force / area_meters == p["Давление"] * 1000
        return force
    if family == "tank-net-flow":
        units(task, {"Начальный объём": "л", "Приток": "л/мин", "Отток": "л/мин",
                     "Требуемый объём": "л", "Вместимость": "л"})
        assert 0 < p["Начальный объём"] < p["Требуемый объём"] < p["Вместимость"]
        assert p["Приток"] > p["Отток"] > 0
        time = ((p["Требуемый объём"] - p["Начальный объём"])
                / (p["Приток"] - p["Отток"]))
        assert time > 0
        assert (p["Начальный объём"] + time * p["Приток"]
                == p["Требуемый объём"] + time * p["Отток"])
        return time
    if family == "resistance-temperature":
        units(task, {"Опорное сопротивление": "Ом", "Опорная температура": "°C",
                     "Коэффициент": "1/°C", "Измеренное сопротивление": "Ом"})
        assert all(value > 0 for value in p.values())
        change = ((p["Измеренное сопротивление"] - p["Опорное сопротивление"])
                  / (p["Опорное сопротивление"] * p["Коэффициент"]))
        temperature = p["Опорная температура"] + change
        assert p["Опорная температура"] < temperature <= 100
        return temperature
    if family == "stopping-distance":
        units(task, {"Время реакции": "с", "Замедление": "м/с²", "Свободный путь": "м"})
        assert all(value > 0 for value in p.values())
        t, a, distance = p["Время реакции"], p["Замедление"], p["Свободный путь"]
        speed = exact_sqrt(a * a * t * t + 2 * a * distance) - a * t
        assert speed > 0 and speed * t + speed * speed / (2 * a) == distance
        larger = speed + Fraction(1, 10)
        assert larger * t + larger * larger / (2 * a) > distance
        assert -a * t - exact_sqrt(a * a * t * t + 2 * a * distance) < 0
        return speed * Fraction(18, 5)
    if family == "catch-up-motion":
        units(task, {"Скорость первого": "км/ч", "Скорость второго": "км/ч",
                     "Задержка": "мин"})
        slow, fast = p["Скорость первого"], p["Скорость второго"]
        delay = p["Задержка"] / 60
        assert fast > slow > 0 and delay > 0
        time = slow * delay / (fast - slow)
        assert time > 0 and fast * time == slow * (time + delay)
        return time
    if family == "river-speed-system":
        units(task, {"Путь по течению": "км", "Время по течению": "ч",
                     "Путь против течения": "км", "Время против течения": "ч"})
        assert all(value > 0 for value in p.values())
        down = p["Путь по течению"] / p["Время по течению"]
        up = p["Путь против течения"] / p["Время против течения"]
        own, current = (down + up) / 2, (down - up) / 2
        assert own > current > 0
        assert (own + current) * p["Время по течению"] == p["Путь по течению"]
        assert (own - current) * p["Время против течения"] == p["Путь против течения"]
        return current
    if family == "joint-pumps":
        units(task, {"Первый насос отдельно": "ч", "Второй насос отдельно": "ч"})
        first, second = p["Первый насос отдельно"], p["Второй насос отдельно"]
        assert first > 0 and second > 0
        time = 1 / (1 / first + 1 / second)
        assert 0 < time < min(first, second) and time / first + time / second == 1
        return time
    if family == "production-deadline":
        units(task, {"Объём заказа": "шт.", "Прирост выработки": "шт./день",
                     "Сокращение срока": "дней"})
        count, increase, days = p.values()
        assert all(value > 0 and value.denominator == 1 for value in p.values())
        rate = (exact_sqrt(increase**2 + 4 * count * increase / days) - increase) / 2
        assert rate > 0 and count / rate - count / (rate + increase) == days
        assert rate.denominator == 1 and (count / rate).denominator == 1
        return rate
    if family == "solution-dilution":
        units(task, {"Исходная масса": "кг", "Исходная концентрация": "%",
                     "Требуемая концентрация": "%"})
        mass = p["Исходная масса"]
        before, after = p["Исходная концентрация"], p["Требуемая концентрация"]
        assert mass > 0 and 0 < after < before < 100
        water = mass * (before - after) / after
        assert water > 0 and mass * before == (mass + water) * after
        return water
    if family == "alloy-balance":
        units(task, {"Масса сплава": "кг", "Первый сплав": "%", "Второй сплав": "%",
                     "Требуемое содержание": "%"})
        total = p["Масса сплава"]
        low, high, target = p["Первый сплав"], p["Второй сплав"], p["Требуемое содержание"]
        assert total > 0 and 0 < low < target < high < 100
        first = total * (high - target) / (high - low)
        second = total - first
        assert first > 0 and second > 0 and first * low + second * high == total * target
        return first
    if family == "line-reconstruction":
        a, b = marked_points(task, [(p["Абсцисса A"], p["Ордината A"]),
                                    (p["Абсцисса B"], p["Ордината B"])])
        slope, intercept = affine([a, b])
        if task.get("figure"):
            for coordinate in task["figure"]["lines"][0]["points"]:
                x, y = point(coordinate)
                assert y == slope * x + intercept
        return slope * p["Аргумент"] + intercept
    if family == "parabola-vertex":
        vertex, known = marked_points(task, [
            (p["Абсцисса вершины"], p["Ордината вершины"]),
            (p["Абсцисса P"], p["Ордината P"]),
        ])
        h, k = vertex
        x, y = known
        assert x != h
        coefficient = (y - k) / (x - h)**2
        assert coefficient != 0
        if task.get("figure"):
            for coordinate in task["figure"]["lines"][0]["points"]:
                px, py = point(coordinate)
                assert py == coefficient * (px - h)**2 + k
        return coefficient * (p["Аргумент"] - h)**2 + k
    if family == "reciprocal-parameter":
        ((x, y),) = marked_points(task, [(p["Абсцисса A"], p["Ордината A"])])
        assert x != 0 and y != 0
        coefficient = x * y
        if task.get("figure"):
            for coordinate in task["figure"]["lines"][0]["points"]:
                px, py = point(coordinate)
                assert px != 0 and px * py == coefficient
        return coefficient
    if family == "exponential-data":
        zero, one = marked_points(task, [(Fraction(0), p["Значение при нуле"]),
                                         (Fraction(1), p["Значение при единице"])])
        scale, factor = zero[1], one[1] / zero[1]
        assert scale > 0 and factor > 0 and factor != 1
        exponent = p["Аргумент"]
        assert exponent.denominator == 1
        result = scale
        for _ in range(int(exponent)):
            result *= factor
        return result
    if family == "line-intersection":
        rows = [[(Fraction(0), p["Первая при нуле"]),
                 (Fraction(1), p["Первая при единице"])],
                [(Fraction(0), p["Вторая при нуле"]),
                 (Fraction(1), p["Вторая при единице"])]]
        if task.get("figure"):
            picture = [[point(pt) for pt in line["points"]]
                       for line in task["figure"]["lines"]]
            assert [affine(row) for row in picture] == [affine(row) for row in rows]
            rows = picture
        (m, b), (n, c) = (affine(row) for row in rows)
        assert m != n
        x = (c - b) / (m - n)
        assert m * x + b == n * x + c
        return x
    if family == "polyline-maximum":
        vertices = [(p[f"Абсцисса {letter}"], p[f"Ордината {letter}"])
                    for letter in "ABCD"]
        if task.get("figure"):
            actual = [point(pt) for pt in task["figure"]["lines"][0]["points"]]
            assert actual == vertices
            vertices = actual
        left, right = p["Левая граница"], p["Правая граница"]
        assert vertices[0][0] < left < right < vertices[-1][0]
        candidates = []
        for a, b in zip(vertices, vertices[1:], strict=False):
            assert a[0] < b[0]
            lo, hi = max(a[0], left), min(b[0], right)
            if lo <= hi:
                slope, intercept = affine([a, b])
                candidates.extend((slope * lo + intercept, slope * hi + intercept))
        return max(candidates)
    if family == "successive-percentages":
        units(task, {"Начальная цена": "руб.", "Повышение": "%", "Скидка": "%"})
        cost, rise, discount = p["Начальная цена"], p["Повышение"], p["Скидка"]
        assert cost > 0 and 0 < rise < 100 and 0 < discount < 100
        raised = cost + cost * rise / 100
        saved = raised * discount / 100
        assert 0 < saved < raised
        return raised - saved
    if family == "capitalized-deposit":
        units(task, {"Первоначальный вклад": "руб.", "Годовая ставка": "%",
                     "Срок": "лет"})
        capital, rate, term = p["Первоначальный вклад"], p["Годовая ставка"], p["Срок"]
        assert capital > 0 and 0 < rate < 100 and term.denominator == 1 and term > 0
        interest = []
        balance = capital
        for _ in range(int(term)):
            added = balance * rate / 100
            assert added > 0 and (added * 100).denominator == 1
            interest.append(added)
            balance += added
        assert balance == capital + sum(interest)
        return balance
    if family == "paid-interest-deposit":
        units(task, {"Первоначальный вклад": "руб.", "Годовая ставка": "%",
                     "Срок": "кварталов"})
        capital, rate, term = p["Первоначальный вклад"], p["Годовая ставка"], p["Срок"]
        assert capital > 0 and 0 < rate < 100 and term.denominator == 1 and term > 0
        receipts = []
        balance = capital
        for _ in range(int(term)):
            received = balance * rate / 400
            receipts.append(received)
            assert balance == capital and (received * 100).denominator == 1
        receipts.append(balance)  # Principal returned after the last interest payment.
        balance -= capital
        assert balance == 0 and sum(receipts) - capital > 0
        return sum(receipts) - capital
    if family == "equal-principal-credit":
        units(task, {"Сумма кредита": "руб.", "Годовая ставка": "%", "Срок": "лет"})
        capital, rate, term = p["Сумма кредита"], p["Годовая ставка"], p["Срок"]
        assert capital > 0 and 0 < rate < 100 and term > 1 and term.denominator == 1
        debt, payments, interests = capital, [], []
        principal_part = capital / term
        for _ in range(int(term)):
            before_interest = debt
            interest = debt * rate / 100
            debt += interest
            payment = principal_part + interest
            debt -= payment
            assert 0 <= debt < before_interest
            assert (payment * 100).denominator == 1
            payments.append(payment)
            interests.append(interest)
        assert debt == 0 and sum(payments) == capital + sum(interests)
        assert all(a > b for a, b in zip(payments, payments[1:], strict=False))
        return sum(payments)
    if family == "equal-payment-credit":
        units(task, {"Сумма кредита": "руб.", "Годовая ставка": "%", "Срок": "лет"})
        capital, rate, term = p["Сумма кредита"], p["Годовая ставка"], p["Срок"]
        assert capital > 0 and 0 < rate < 100 and term == 2
        factor = 1 + rate / 100
        # Present values give a separate equation for two equal payments.
        payment = capital / (1 / factor + 1 / factor**2)
        debt, interest_total = capital, Fraction(0)
        for period in range(2):
            interest = debt * rate / 100
            interest_total += interest
            debt += interest - payment
            assert debt > 0 if period == 0 else debt == 0
            assert (interest * 100).denominator == 1
        assert (payment * 100).denominator == 1
        assert 2 * payment == capital + interest_total
        return payment
    if family == "family-budget":
        units(task, {"Доход": "руб.", "Жильё": "руб.", "Питание": "руб.",
                     "Транспорт": "руб.", "Доля в резерв": "%"})
        income = p["Доход"]
        expenses = p["Жильё"] + p["Питание"] + p["Транспорт"]
        assert all(value > 0 for value in p.values()) and 0 < p["Доля в резерв"] < 100
        reserve = income * p["Доля в резерв"] / 100
        disposable = income - expenses - reserve
        assert disposable > 0 and disposable + reserve + expenses == income
        return disposable
    if family == "tariff-threshold":
        units(task, {"Первый тариф": "руб./кВт·ч", "Плата второго": "руб./месяц",
                     "Второй тариф": "руб./кВт·ч"})
        first, fixed, second = p["Первый тариф"], p["Плата второго"], p["Второй тариф"]
        assert first > second > 0 and fixed > 0
        boundary = fixed / (first - second)
        count = boundary.numerator // boundary.denominator + 1
        assert fixed + second * count < first * count
        assert fixed + second * (count - 1) >= first * (count - 1)
        return Fraction(count)
    raise AssertionError(f"No independent oracle for {family}")


def assert_figure(figure):
    assert set(figure) == {
        "description", "x_min", "x_max", "y_min", "y_max", "axes", "lines", "circles",
        "labels",
    }
    assert len(figure["description"]) >= 40
    assert "<" not in figure["description"] and ">" not in figure["description"]
    assert figure["axes"] is True
    for axis in "xy":
        low, high = figure[f"{axis}_min"], figure[f"{axis}_max"]
        assert -10000 <= low < high <= 10000
    coordinates = []
    for line in figure["lines"]:
        assert set(line) <= {"points", "dashed"}
        assert 2 <= len(line["points"]) <= 201
        coordinates.extend(line["points"])
    for circle in figure["circles"]:
        assert set(circle) == {"center", "radius"}
        assert 0 < circle["radius"] <= 10000
        coordinates.append(circle["center"])
    for label in figure["labels"]:
        assert set(label) == {"x", "y", "text"}
        assert label["text"] and "<" not in label["text"]
        coordinates.append({"x": label["x"], "y": label["y"]})
    for coordinate in coordinates:
        assert set(coordinate) == {"x", "y"}
        for axis in "xy":
            value = coordinate[axis]
            assert type(value) in {int, float} and math.isfinite(value)
            assert figure[f"{axis}_min"] <= value <= figure[f"{axis}_max"]


def assert_task(task, family, seed, profile):
    expected = oracle(task)
    assert number(task["answer"]) == expected
    denominator = Fraction(expected).denominator
    for divisor in (2, 5):
        while denominator % divisor == 0:
            denominator //= divisor
    assert denominator == 1, "The answer must terminate without rounding"
    assert len(task["answer"]) <= 64
    assert task["id"] == f"course-{family.id}-{seed}"
    assert task["profile_id"] == profile.id
    assert task["slot_id"] == next(slot.id for slot in profile.slots if slot.number == family.slot)
    assert task["slot"] == family.slot and task["family_id"] == family.id
    assert task["skill_ids"] == list(family.skill_ids)
    assert task["rounding"] is None and task["review_status"] == "demo"
    assert task["source"]["reviewed_by"] is None
    assert task["generation"] == {
        "template_id": family.id, "template_version": "1", "seed": seed,
    }
    assert len(task["hints"]) == len(set(task["hints"])) == 3
    assert all(len(text) >= 20 for text in task["hints"])
    assert len(task["solution"]) >= 3
    assert task["answer"] in task["solution"][-1]
    if family.slot == 12:
        assert task["figure"] is not None
        assert_figure(task["figure"])
    else:
        assert task["figure"] is None
    json.dumps(task, ensure_ascii=False, allow_nan=False)


CASES = [
    pytest.param(family, seed, id=f"{family.id}-{seed}")
    for family in FAMILIES
    for seed in [*range(1000 if family.supports_runtime else 10), MAX_SEED]
]


@pytest.mark.parametrize(("family", "seed"), CASES)
def test_condition_oracle_and_invariants(family, seed, profile):
    task = family.generate(seed, profile)
    assert_task(task, family, seed, profile)
    assert family.generate(seed, profile) == task


@pytest.mark.parametrize("family", FAMILIES, ids=lambda family: family.id)
def test_ten_distinct_conditions(family, profile):
    conditions = [
        json.dumps({key: family.generate(seed, profile)[key]
                    for key in ("statement", "table", "figure")},
                   sort_keys=True, ensure_ascii=False)
        for seed in range(10)
    ]
    assert len(set(conditions)) == 10


def test_registry_covers_the_stable_profile_skills(profile):
    assert len({family.id for family in FAMILIES}) == len(FAMILIES) == 24
    assert Counter(family.slot for family in FAMILIES) == {10: 5, 11: 6, 12: 6, 13: 7}
    assert {family.id for family in FAMILIES if family.supports_runtime} == RUNTIME_IDS
    assert Counter(family.slot for family in FAMILIES if family.supports_runtime) == {
        10: 2, 11: 2, 12: 2, 13: 2,
    }
    for family in FAMILIES:
        assert re.fullmatch(r"[a-z]+(?:-[a-z]+)*", family.id)
    for slot in profile.slots:
        if 10 <= slot.number <= 13:
            actual = {skill for family in FAMILIES if family.slot == slot.number
                      for skill in family.skill_ids}
            assert actual == {skill.id for skill in slot.skills}


def example_task(example, family):
    text, data = example["statement"].split("\nДанные:\n", maxsplit=1)
    rows = []
    for line in data.splitlines():
        match = re.fullmatch(r"(.+) = (-?[0-9]+(?:,[0-9]+)?) \((.+)\)", line)
        assert match, line
        rows.append(list(match.groups()))
    return {"family_id": family.id, "statement": text, "answer": example["answer"],
            "table": {"headers": ["Величина", "Значение", "Единица"], "rows": rows},
            "figure": None}


def test_lessons_are_substantive_and_worked_examples_are_independently_correct(profile):
    lessons = build_lessons(profile)
    assert len(lessons) == len(FAMILIES)
    assert lessons == build_lessons(profile)
    for family, lesson in zip(FAMILIES, lessons, strict=True):
        assert lesson["id"] == f"course-{family.id}"
        assert lesson["slot"] == family.slot
        assert lesson["skill_ids"] == list(family.skill_ids)
        assert lesson["family_ids"] == [family.id]
        assert lesson["practice_task_ids"] == [f"course-{family.id}-{i}" for i in range(3)]
        assert 3 <= lesson["minutes"] <= 7
        body = " ".join(section["body"] for section in lesson["sections"])
        assert 350 <= len(RUSSIAN_WORD.findall(body)) <= 600, family.id
        whole = " ".join([body, lesson["title"], lesson["takeaway"],
                          lesson["example"]["statement"], *lesson["example"]["steps"]])
        assert len(RUSSIAN_WORD.findall(whole)) <= 600, family.id
        assert len(lesson["sections"]) >= 3
        assert all(set(section) == {"heading", "body", "formula"}
                   for section in lesson["sections"])
        example = example_task(lesson["example"], family)
        assert number(example["answer"]) == oracle(example)
        assert len(lesson["example"]["steps"]) >= 3
        for seed in range(3):
            assert inputs(example) != inputs(family.generate(seed, profile))
    json.dumps(lessons, ensure_ascii=False, allow_nan=False)


def test_resistance_lesson_distinguishes_temperature_and_resistance_errors(profile):
    family = next(family for family in FAMILIES if family.id == "resistance-temperature")
    p = inputs(family.generate(0, profile))
    base = p["Опорное сопротивление"]
    reference = p["Опорная температура"]
    alpha = p["Коэффициент"]
    measured = p["Измеренное сопротивление"]

    without_reference = (measured - base) / (base * alpha)
    temperature = reference + without_reference
    wrong_resistance = base + base * alpha * (without_reference - reference)
    checked_resistance = base + base * alpha * (temperature - reference)
    assert (without_reference, temperature) == (10, 30)
    assert (wrong_resistance, checked_resistance, measured) == (48, 52, 52)
    assert temperature - without_reference == reference == 20
    assert measured - wrong_resistance == base * alpha * reference == 4

    lesson = next(lesson for lesson in build_lessons(profile)
                  if lesson["id"] == "course-resistance-temperature")
    body = " ".join(section["body"] for section in lesson["sections"])
    # Bind the independently calculated counterexample to the published diagnostic.
    assert re.search(r"температура[^.]*на T₀ градусов\.", body)
    assert re.search(r"сопротивление[^.]*на R₀αT₀ Ом\.", body)


@pytest.mark.parametrize("family", FAMILIES, ids=lambda family: family.id)
@pytest.mark.parametrize("seed", [-1, 2**32, True, "1", Fraction(1, 2)])
def test_reject_invalid_seed_before_building_a_model(family, seed, profile):
    with pytest.raises(ValueError, match="Seed"):
        family.generate(seed, profile)
