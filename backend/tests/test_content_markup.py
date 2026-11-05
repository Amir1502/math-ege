import pytest

from app.content import ContentError, validate_content
from app.editor.validation import data_only
from app.errors import ApiError
from tests.test_content_extensions import package


@pytest.mark.parametrize("formula", [
    r"\overrightarrow{AB}=(3;4)",
    r"x>0\Longrightarrow x^2>0",
    r"x=1\Longleftrightarrow x-1=0",
    r"x=1\iff x-1=0",
    r"B+ax<ax\quad\Longleftrightarrow\quad x>10",
])
def test_supported_course_math_is_data_only(content_dir, formula):
    profile, lessons, tasks = package(content_dir)
    tasks[0]["formula"] = formula
    data_only(tasks[0])
    assert validate_content(profile, lessons, tasks).tasks[0].formula == formula


@pytest.mark.parametrize("markup", [
    "<script>alert(1)</script>",
    "<svg onload='run()'></svg>",
    "<img src=x onerror=run() />",
    "<b>Условие</b>",
    "<custom-widget data-x='1'>Текст</custom-widget>",
    "<!-- comment -->",
    "<!doctype html>",
])
def test_content_and_editor_reject_markup(content_dir, markup):
    profile, lessons, tasks = package(content_dir)
    tasks[0]["statement"] = markup
    with pytest.raises(ContentError):
        validate_content(profile, lessons, tasks)
    with pytest.raises(ApiError) as error:
        data_only(tasks[0])
    assert error.value.code == "unsafe_content"


@pytest.mark.parametrize("formula", [
    r"\href{javascript:run()}{x}",
    r"\htmlStyle{color:red}{x}",
    r"\includegraphics{https://example.invalid/x}",
    r"\def\x{1}",
    r"\begin{document}x\end{document}",
])
def test_math_allowlist_remains_closed(formula):
    with pytest.raises(ApiError) as error:
        data_only({"formula": formula})
    assert error.value.code == "unsafe_formula"
