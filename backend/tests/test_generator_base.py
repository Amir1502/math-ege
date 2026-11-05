from fractions import Fraction

import pytest

from app.generators.base import decimal_text, make_task


@pytest.mark.parametrize(
    ("value", "expected"),
    [(Fraction(1, 8), "0,125"), (Fraction(-7, 20), "-0,35"), (0, "0"), (200, "200")],
)
def test_exact_finite_decimal_output(value, expected):
    assert decimal_text(value) == expected


def test_nonterminating_answer_is_not_silently_rounded():
    with pytest.raises(ValueError, match="finite"):
        decimal_text(Fraction(1, 3))


def test_generated_task_retains_reproducible_unreviewed_provenance(content):
    task = make_task(
        content.profile, 1, "rectangle-area", 42, title="Площадь прямоугольника",
        statement="Стороны прямоугольника равны 3 и 4. Найдите площадь.",
        answer=12, skills=["plane-areas"],
        hints=["Нужна площадь.", "Умножьте стороны.", "Вычислите 3 · 4."],
        solution=["S = 3 · 4 = 12."],
    )
    assert task["answer"] == "12"
    assert task["review_status"] == "demo"
    assert task["source"]["reviewed_by"] is None
    assert task["generation"] == {
        "template_id": "rectangle-area", "template_version": "1", "seed": 42,
    }
    assert task["slot_id"] == content.profile.slots[0].id
    assert task["id"] == "course-rectangle-area-42"


def test_generation_requires_known_profile_skills(content):
    with pytest.raises(ValueError, match="skill"):
        make_task(
            content.profile, 1, "rectangle-area", 0, title="Площадь",
            statement="Найдите площадь.", answer=12, skills=["invented-skill"],
            hints=["Раз", "Два", "Три"], solution=["12"],
        )
