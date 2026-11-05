"""Checks at the public lesson boundary; no claim of human subject review."""

import ast
import json
import operator
import re
from fractions import Fraction
from graphlib import TopologicalSorter
from math import isqrt
from pathlib import Path

import pytest

from app.editor.validation import data_only
from app.schemas import Lesson, ProfileSource

PROFILE_PATH = Path(__file__).resolve().parents[1] / "content" / "profile.json"
PROFILE = ProfileSource.model_validate_json(PROFILE_PATH.read_text(encoding="utf-8"))
EXPECTED_IDS = {
    "base-fractions",
    "base-negative-numbers",
    "base-percentages",
    "base-powers",
    "base-roots",
    "base-algebra-expressions",
    "base-coordinates",
    "base-linear-equations",
}


def lessons():
    from app.generators.foundations import build_lessons

    return build_lessons(PROFILE)


def example_for(lesson_id, index):
    lesson = next(lesson for lesson in lessons() if lesson["id"] == lesson_id)
    return [lesson["example"], *lesson["examples"]][index]


def fraction(text):
    return Fraction(text.replace("−", "-").replace(",", "."))


def capture_numbers(pattern, text):
    match = re.fullmatch(pattern, text)
    assert match is not None, text
    return tuple(fraction(value) for value in match.groups())


def literal_arithmetic(text):
    """Independently evaluate displayed arithmetic, with exact roots and no eval."""
    text = re.sub(r"√([0-9]+)", r"sqrt(\1)", text).replace("√(", "sqrt(")
    text = text.replace("−", "-").replace("·", "*").replace(":", "/").replace("^", "**")
    operations = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
    }

    def value(node):
        if isinstance(node, ast.Constant) and type(node.value) is int:
            return Fraction(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            result = value(node.operand)
            return -result if isinstance(node.op, ast.USub) else result
        if isinstance(node, ast.BinOp):
            left, right = value(node.left), value(node.right)
            if isinstance(node.op, ast.Pow):
                assert right.denominator == 1
                return left ** int(right)
            assert type(node.op) in operations
            return operations[type(node.op)](left, right)
        if isinstance(node, ast.Call):
            assert isinstance(node.func, ast.Name) and node.func.id == "sqrt"
            assert len(node.args) == 1 and not node.keywords
            radicand = value(node.args[0])
            assert radicand >= 0
            root = Fraction(isqrt(radicand.numerator), isqrt(radicand.denominator))
            assert root * root == radicand, "This example must have an exact rational root"
            return root
        raise AssertionError(f"Unsupported arithmetic in worked example: {text}")

    return value(ast.parse(text, mode="eval").body)


def test_build_lessons_provides_eight_substantive_foundations():
    result = lessons()
    assert isinstance(result, list)
    assert len(result) == 8
    assert {lesson["id"] for lesson in result} == EXPECTED_IDS
    for lesson in result:
        body = " ".join(section["body"] for section in lesson["sections"])
        words = re.findall(r"[А-Яа-яЁё]+(?:[-‑][А-Яа-яЁё]+)*", body)
        assert 200 <= len(words) <= 450, (lesson["id"], len(words))
        assert 3 <= lesson["minutes"] <= 7
        assert 1 <= len([lesson["example"], *lesson["examples"]]) <= 2
        assert all(section["heading"].strip() and section["body"].strip()
                   for section in lesson["sections"])
        assert any("Типичная ошибка" in section["heading"] for section in lesson["sections"])
        assert any("Самопроверка" in section["heading"] for section in lesson["sections"])
        assert any(section["formula"] for section in lesson["sections"])
        assert lesson["takeaway"].strip()


@pytest.mark.parametrize("lesson_id", sorted(EXPECTED_IDS))
def test_foundation_payloads_validate_as_lessons_and_bounded_text(lesson_id):
    lesson = next(lesson for lesson in lessons() if lesson["id"] == lesson_id)
    parsed = Lesson.model_validate(lesson)
    encoded = json.dumps(lesson, ensure_ascii=False, allow_nan=False)
    assert Lesson.model_validate_json(encoded) == parsed
    data_only(lesson)
    for example in [lesson["example"], *lesson["examples"]]:
        assert example["statement"].strip() and example["answer"].strip()
        assert len(example["steps"]) >= 2
        assert all(step.strip() for step in example["steps"])


def test_foundations_are_unreviewed_prerequisites_with_real_exam_links():
    profile_slots = {slot.id: slot for slot in PROFILE.slots}
    profile_skills = {skill.id for slot in PROFILE.slots for skill in slot.skills}
    for lesson in lessons():
        assert lesson["kind"] == "foundation"
        assert lesson["slot"] == 0 and lesson["slot_id"] is None
        assert lesson["skill_ids"] == [lesson["id"].replace("base-", "foundation-", 1)]
        assert not profile_skills.intersection(lesson["skill_ids"])
        assert lesson["family_ids"] == []
        assert lesson["practice_task_ids"] == []
        assert lesson["review_status"] == "demo"
        assert lesson["author_id"] == "ai-project"
        assert lesson["reviewed_by"] is None
        related = lesson["related_slot_ids"]
        assert related and len(related) == len(set(related))
        assert set(related) <= profile_slots.keys()
        body = " ".join(section["body"] for section in lesson["sections"])
        for slot_id in related:
            assert profile_slots[slot_id].title in body


def test_prerequisites_form_an_acyclic_graph_of_foundation_lessons():
    graph = {lesson["id"]: lesson["prerequisite_ids"] for lesson in lessons()}
    for lesson_id, prerequisites in graph.items():
        assert len(prerequisites) == len(set(prerequisites))
        assert set(prerequisites) <= EXPECTED_IDS - {lesson_id}
    order = list(TopologicalSorter(graph).static_order())
    assert set(order) == EXPECTED_IDS
    assert graph["base-fractions"] == graph["base-negative-numbers"] == []
    assert "base-fractions" in graph["base-percentages"]
    assert "base-powers" in graph["base-roots"]
    assert "base-negative-numbers" in graph["base-coordinates"]
    assert "base-algebra-expressions" in graph["base-linear-equations"]


def test_build_lessons_requires_stable_related_slot_ids():
    from app.generators.foundations import build_lessons

    changed = PROFILE.model_dump(mode="json")
    for slot in changed["slots"]:
        if slot["id"] == "word-problems":
            slot["id"] = "different-topic-at-the-same-number"
    profile = ProfileSource.model_validate(changed)
    with pytest.raises(ValueError, match="word-problems"):
        build_lessons(profile)


def test_profile_renumbering_and_unrelated_slots_do_not_change_foundations():
    from app.generators.foundations import build_lessons

    changed = PROFILE.model_dump(mode="json")
    changed["slots"] = [slot for slot in reversed(changed["slots"])
                        if slot["id"] != "solid-geometry"]
    for number, slot in enumerate(changed["slots"], start=101):
        slot["number"] = number
    assert build_lessons(ProfileSource.model_validate(changed)) == lessons()


def test_builds_are_repeatable_and_nested_material_is_not_shared():
    before_profile = PROFILE.model_dump(mode="json")
    untouched = lessons()
    edited = lessons()
    edited[0]["sections"][0]["body"] = "Изменённая копия."
    edited[0]["example"]["steps"].clear()
    edited[0]["examples"][0]["answer"] = "999"
    edited[0]["related_slot_ids"].clear()
    edited[0]["skill_ids"].append("different-skill")
    edited[-1]["prerequisite_ids"].clear()
    assert lessons() == untouched
    assert PROFILE.model_dump(mode="json") == before_profile


@pytest.mark.parametrize("lesson_id", [
    "base-fractions", "base-negative-numbers", "base-powers", "base-roots",
])
@pytest.mark.parametrize("index", [0, 1])
def test_numeric_example_answers_come_from_displayed_literal_arithmetic(lesson_id, index):
    example = example_for(lesson_id, index)
    match = re.fullmatch(
        r"Вычислите ([^.]+)\.(?: Запишите ответ несократимой дробью\.)?",
        example["statement"],
    )
    assert match is not None
    expected = literal_arithmetic(match[1])
    assert fraction(example["answer"]) == expected


def test_successive_percentage_example_uses_the_changed_base():
    example = example_for("base-percentages", 0)
    original, increase, decrease = capture_numbers(
        r"Цена набора ([0-9]+) рублей\. Её повысили на ([0-9]+)%, "
        r"а затем новую цену снизили на ([0-9]+)%\. Найдите итоговую цену в рублях\.",
        example["statement"],
    )
    assert original > 0 and increase > 0 and 0 < decrease < 100
    after_increase = original + original * increase / 100
    expected = after_increase - after_increase * decrease / 100
    assert fraction(example["answer"]) == expected
    assert expected != original  # Equal rates do not undo the change of base.


def test_reverse_percentage_example_reconstructs_the_original_price():
    example = example_for("base-percentages", 1)
    discount, remaining = capture_numbers(
        r"После скидки ([0-9]+)% билет стоит ([0-9]+) рублей\. "
        r"Сколько рублей он стоил до скидки\?", example["statement"],
    )
    assert remaining > 0 and 0 < discount < 100
    # Recover the price of one percentage point before recovering the whole.
    one_percent = remaining / (100 - discount)
    expected = 100 * one_percent
    assert fraction(example["answer"]) == expected
    assert expected - expected * discount / 100 == remaining


def test_expression_example_is_checked_in_its_original_parentheses():
    example = example_for("base-algebra-expressions", 0)
    a, b, c, d, x = capture_numbers(
        r"Найдите значение ([0-9]+)\(x − ([0-9]+)\) − ([0-9]+)\(x \+ ([0-9]+)\) "
        r"при x = (−?[0-9]+)\.", example["statement"],
    )
    expected = a * (x - b) - c * (x + d)
    assert fraction(example["answer"]) == expected


def test_fractional_substitution_example_divides_the_whole_numerator():
    example = example_for("base-algebra-expressions", 1)
    coefficient, constant, denominator, x = capture_numbers(
        r"Найдите значение \(([0-9]+)x \+ ([0-9]+)\)/([0-9]+) "
        r"при x = ([0-9]+/[0-9]+)\.", example["statement"],
    )
    assert denominator != 0
    expected = (coefficient * x + constant) / denominator
    assert fraction(example["answer"]) == expected


def test_coordinate_pair_uses_each_axis_scale_and_preserves_order():
    example = example_for("base-coordinates", 0)
    x_scale, y_scale, left_cells, up_cells = capture_numbers(
        r"На координатной плоскости одна клетка по оси x равна ([0-9]+), "
        r"а по оси y равна ([0-9]+)\. Точка A находится на ([0-9]+) клетки левее "
        r"и на ([0-9]+) клетку выше начала координат\. "
        r"Запишите координаты A в виде \(x; y\)\.", example["statement"],
    )
    assert x_scale > 0 and y_scale > 0
    expected = (-x_scale * left_cells, y_scale * up_cells)
    actual = capture_numbers(r"\((−?-?[0-9]+); (−?-?[0-9]+)\)", example["answer"])
    assert actual == expected


def test_coordinate_change_is_end_minus_start_on_the_requested_axis():
    example = example_for("base-coordinates", 1)
    ax, ay, bx, by = capture_numbers(
        r"Даны точки A\((−?[0-9]+); (−?[0-9]+)\) и B\((−?[0-9]+); (−?[0-9]+)\)\. "
        r"Найдите изменение координаты x при переходе из A в B\.", example["statement"],
    )
    expected = bx - ax
    assert expected != by - ay
    assert fraction(example["answer"]) == expected


def test_linear_equation_example_has_one_root_of_the_original_equality():
    example = example_for("base-linear-equations", 0)
    a, b, c, d = capture_numbers(
        r"Решите уравнение ([0-9]+)\(x − ([0-9]+)\) = ([0-9]+)x \+ ([0-9]+)\.",
        example["statement"],
    )
    assert a != c
    expected = (a * b + d) / (a - c)
    assert fraction(example["answer"]) == expected
    assert a * (expected - b) == c * expected + d


def test_fractional_linear_equation_example_restores_both_sides():
    example = example_for("base-linear-equations", 1)
    denominator, subtrahend, right = capture_numbers(
        r"Решите уравнение x/([0-9]+) − ([0-9]+) = ([0-9]+)\.", example["statement"],
    )
    assert denominator != 0
    expected = denominator * (right + subtrahend)
    assert fraction(example["answer"]) == expected
    assert expected / denominator - subtrahend == right
