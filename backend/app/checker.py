"""Strict numeric input and exact rational comparison, without implicit rounding.

The parser accepts only the grammar in FR-12. Its output is independent of HTTP,
storage, task content, and locale. A rounding requirement belongs to the task:
the expected answer must already be the explicitly rounded exact value.
"""

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

AnswerMode = Literal["training", "exam"]
MAX_ANSWER_LENGTH = 64
_DECIMAL = re.compile(r"-?[0-9]+(?:,[0-9]+)?\Z")
_FRACTION = re.compile(r"-?[0-9]+/[0-9]+\Z")


class AnswerFormatError(ValueError):
    """A rejected format is not a mathematical attempt."""

    def __init__(self, message: str, code: str = "invalid_answer_format") -> None:
        super().__init__(message)
        self.code = code
        self.field = "answer"


@dataclass(frozen=True, slots=True)
class ParsedAnswer:
    value: Fraction
    normalized_answer: str


@dataclass(frozen=True, slots=True)
class CheckResult:
    correct: bool
    normalized_answer: str
    expected_answer: str


def format_fraction(value: Fraction) -> str:
    """Render a reduced rational as a finite decimal, or a reduced fraction.

    Only integer arithmetic is used. Non-terminating training fractions retain
    their fraction form rather than being rounded to an invented decimal.
    """
    if value == 0:
        return "0"
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        return f"{value.numerator}/{value.denominator}"
    places = max(twos, fives)
    scaled = abs(value.numerator) * 2 ** (places - twos) * 5 ** (places - fives)
    sign = "-" if value < 0 else ""
    if places == 0:
        return f"{sign}{scaled}"
    digits = str(scaled).zfill(places + 1)
    fractional = digits[-places:].rstrip("0")
    whole = digits[:-places]
    return f"{sign}{whole},{fractional}" if fractional else f"{sign}{whole}"


def parse_answer(raw: str, mode: AnswerMode = "training") -> ParsedAnswer:
    """Parse at most 64 raw characters according to the explicit mode grammar."""
    if mode not in ("training", "exam"):
        raise ValueError("mode must be 'training' or 'exam'")
    if not isinstance(raw, str):
        raise AnswerFormatError("Ответ должен передаваться строкой.")
    if len(raw) > MAX_ANSWER_LENGTH:
        raise AnswerFormatError("Ответ должен содержать не более 64 символов.")
    text = raw.strip().replace("−", "-").replace(".", ",")
    if not text:
        raise AnswerFormatError("Введите ответ. Пустое поле не равно нулю.")
    if _DECIMAL.fullmatch(text):
        negative = text.startswith("-")
        unsigned = text.removeprefix("-")
        whole, separator, fractional = unsigned.partition(",")
        numerator = int(whole + fractional)
        value = Fraction(-numerator if negative else numerator, 10 ** len(fractional))
        if not separator:
            value = Fraction(-numerator if negative else numerator)
    elif mode == "training" and _FRACTION.fullmatch(text):
        numerator_text, denominator_text = text.split("/")
        denominator = int(denominator_text)
        if denominator == 0:
            raise AnswerFormatError("Знаменатель дроби должен быть положительным и не равным нулю.")
        value = Fraction(int(numerator_text), denominator)
    else:
        suffix = " В обучении также допустима дробь a/b с положительным знаменателем."
        raise AnswerFormatError(
            "Введите целое число или конечную десятичную дробь без пробелов, знака плюс, "
            "выражений и единиц измерения." + (suffix if mode == "training" else "")
        )
    return ParsedAnswer(value=value, normalized_answer=format_fraction(value))


def check_answer(
    raw: str, expected: str, mode: AnswerMode = "training"
) -> CheckResult:
    """Compare exact values; never round the student's input or use tolerance."""
    parsed = parse_answer(raw, mode)
    reference = parse_answer(expected, "exam")
    return CheckResult(
        correct=parsed.value == reference.value,
        normalized_answer=parsed.normalized_answer,
        expected_answer=reference.normalized_answer,
    )
