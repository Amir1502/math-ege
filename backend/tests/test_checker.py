"""Independent numeric examples from the answer grammar and worked arithmetic."""

from fractions import Fraction

import pytest

from app.checker import AnswerFormatError, check_answer, parse_answer


@pytest.mark.parametrize("raw", ["0.5", "0,50", "000,500", "1/2"])
def test_equal_representations(raw):
    result = check_answer(raw, "0,5", mode="training")
    assert result.correct is True
    assert result.normalized_answer == "0,5"


@pytest.mark.parametrize(
    ("raw", "normalized", "numerator", "denominator"),
    [
        ("0", "0", 0, 1),
        ("-0", "0", 0, 1),
        ("−0", "0", 0, 1),
        ("-000.000", "0", 0, 1),
        ("000", "0", 0, 1),
        ("1", "1", 1, 1),
        ("-1", "-1", -1, 1),
        ("−17", "-17", -17, 1),
        ("259200", "259200", 259200, 1),
        ("0002,50", "2,5", 5, 2),
        ("2.50", "2,5", 5, 2),
        ("0.125", "0,125", 1, 8),
        ("-0,1250", "-0,125", -1, 8),
        ("−00010.0500", "-10,05", -201, 20),
        ("\t 2,5 \r\n", "2,5", 5, 2),
        ("\u00a0−2.5\u00a0", "-2,5", -5, 2),
        ("\u20070,500\u202f", "0,5", 1, 2),
        ("1/2", "0,5", 1, 2),
        ("2/4", "0,5", 1, 2),
        ("-2/4", "-0,5", -1, 2),
        ("−0002/0004", "-0,5", -1, 2),
        ("0/7", "0", 0, 1),
        ("-0/7", "0", 0, 1),
        ("4/2", "2", 2, 1),
        ("1/3", "1/3", 1, 3),
        ("2/6", "1/3", 1, 3),
        ("-10/6", "-5/3", -5, 3),
        ("1/40", "0,025", 1, 40),
        ("7/8", "0,875", 7, 8),
        ("1/1000000000000000000000000", "0,000000000000000000000001", 1,
         1000000000000000000000000),
        ("9007199254740993", "9007199254740993", 9007199254740993, 1),
        ("9999999999999999999999999999999999999999999999999999999999999999",
         "9999999999999999999999999999999999999999999999999999999999999999",
         9999999999999999999999999999999999999999999999999999999999999999, 1),
        ("0,00000000000000000000000000000000000000000000000000000000000001",
         "0,00000000000000000000000000000000000000000000000000000000000001", 1,
         100000000000000000000000000000000000000000000000000000000000000),
    ],
)
def test_parser_has_exact_value_and_canonical_text(raw, normalized, numerator, denominator):
    parsed = parse_answer(raw, mode="training")
    assert parsed.normalized_answer == normalized
    assert parsed.value == Fraction(numerator, denominator)


@pytest.mark.parametrize(
    "raw",
    [
        "", " ", "\t\r\n", "1/0", "1/00", "0/0", "1/-2", "-1/-2", "1/−2",
        "1/+2", "1/", "/2", "1/2/3", "1.5/2", "1/2.5", "1,5/2", "1 /2", "1/ 2",
        "NaN", "nan", "Infinity", "inf", "-Infinity", "2+3", "2-3", "2*3", "2^3",
        "2**3", "sqrt(4)", "(2)", "2 кг", "2kg", "1 000", "1\u00a0000",
        "1\u202f000", "1\u2007000", "1\t000", "1\n000", "+1", "＋1", ",5", ".5",
        "1,", "1.", "1,2,3", "1.2.3", "1,2.3", "1.2,3", "--1", "−-1", "–1",
        "—1", "1-", "1e3", "1E+3", "0x10", "１２", "١٢", "²", "1\x00",
        "1\u200b", "1\ufeff", "1/２", "1／2", "1\\2", "-", "0" * 65,
        " " + "9" * 64, "9" * 64 + " ",
    ],
)
def test_invalid_formats_never_parse(raw):
    with pytest.raises(AnswerFormatError) as caught:
        parse_answer(raw, mode="training")
    assert caught.value.code == "invalid_answer_format"
    assert caught.value.field == "answer"
    assert str(caught.value)


@pytest.mark.parametrize("raw", ["1/2", "2/4", "0/7", "1/3", "-1/2", "−1/2"])
def test_exam_rejects_all_fraction_forms(raw):
    with pytest.raises(AnswerFormatError):
        parse_answer(raw, mode="exam")


@pytest.mark.parametrize(
    ("raw", "expected", "correct"),
    [
        ("0", "0", True),
        ("0", "1", False),
        ("-0.00", "0", True),
        ("2,50", "2.5", True),
        ("−2.5", "-2,5", True),
        ("1/2", "0,5", True),
        ("3/6", "0,5", True),
        ("1/3", "0,33", False),
        ("0,333", "0,33", False),
        ("0,334", "0,33", False),
        ("0,330", "0,33", True),
        ("1,2345", "1,23", False),
        ("1,2300", "1,23", True),
        ("9007199254740993", "9007199254740992", False),
        ("9007199254740993", "9007199254740993", True),
        ("9007199254740992,01", "9007199254740992,02", False),
        ("9999999999999999999999999999999999999999999999999999999999999999",
         "9999999999999999999999999999999999999999999999999999999999999998", False),
        ("0,00000000000000000000000000000000000000000000000000000000000001",
         "0", False),
        ("1000000000000000000000000000000/2", "500000000000000000000000000000", True),
    ],
)
def test_comparison_has_no_float_tolerance_or_implicit_rounding(raw, expected, correct):
    result = check_answer(raw, expected, mode="training")
    assert result.correct is correct


@pytest.mark.parametrize("raw", ["0.5", "0,50", "−0002,50", "259200"])
def test_exam_accepts_numeric_grammar_and_normalization(raw):
    result = parse_answer(raw, mode="exam")
    assert result.normalized_answer in {"0,5", "-2,5", "259200"}


@pytest.mark.parametrize("raw", [None, 0, 0.5, True, [], {}])
def test_non_string_input_is_not_silently_coerced(raw):
    with pytest.raises(AnswerFormatError):
        parse_answer(raw, mode="training")


def test_unknown_mode_is_a_programming_error():
    with pytest.raises(ValueError, match="mode must"):
        parse_answer("0", mode="unknown")
