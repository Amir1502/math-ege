"""Bounded data validation and the bridge to registered, server-owned generators."""

import copy
import hashlib
import json
import math
import re
from typing import Any

from pydantic import ValidationError

from app.content import ContentBundle, ContentError, Task
from app.editor.schemas import Kind, TemplatePayload
from app.errors import ApiError
from app.markup import MARKUP
from app.schemas import Lesson, ProfileSource

MAX_PAYLOAD_BYTES = 131_072
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_COMMAND = re.compile(r"\\([A-Za-z]+)")
_MATH_COMMANDS = frozenset(
    [
        "frac",
        "dfrac",
        "tfrac",
        "sqrt",
        "cdot",
        "times",
        "div",
        "pm",
        "mp",
        "le",
        "leq",
        "ge",
        "geq",
        "ne",
        "neq",
        "approx",
        "equiv",
        "sim",
        "simeq",
        "lt",
        "gt",
        "in",
        "notin",
        "subset",
        "subseteq",
        "supset",
        "supseteq",
        "cup",
        "cap",
        "setminus",
        "emptyset",
        "varnothing",
        "infty",
        "alpha",
        "beta",
        "gamma",
        "delta",
        "epsilon",
        "varepsilon",
        "zeta",
        "eta",
        "theta",
        "vartheta",
        "iota",
        "kappa",
        "lambda",
        "mu",
        "nu",
        "xi",
        "pi",
        "varpi",
        "rho",
        "varrho",
        "sigma",
        "varsigma",
        "tau",
        "upsilon",
        "phi",
        "varphi",
        "chi",
        "psi",
        "omega",
        "Gamma",
        "Delta",
        "Theta",
        "Lambda",
        "Xi",
        "Pi",
        "Sigma",
        "Upsilon",
        "Phi",
        "Psi",
        "Omega",
        "sin",
        "cos",
        "tan",
        "cot",
        "tg",
        "ctg",
        "sec",
        "csc",
        "arcsin",
        "arccos",
        "arctan",
        "sinh",
        "cosh",
        "tanh",
        "log",
        "ln",
        "lg",
        "exp",
        "min",
        "max",
        "lim",
        "sum",
        "prod",
        "int",
        "iint",
        "oint",
        "limits",
        "nolimits",
        "overline",
        "underline",
        "vec",
        "overrightarrow",
        "hat",
        "bar",
        "dot",
        "ddot",
        "left",
        "right",
        "middle",
        "big",
        "Big",
        "bigg",
        "Bigg",
        "bigl",
        "bigr",
        "Bigl",
        "Bigr",
        "biggl",
        "biggr",
        "Biggl",
        "Biggr",
        "text",
        "textrm",
        "textnormal",
        "textbf",
        "textit",
        "mathrm",
        "mathit",
        "mathbf",
        "mathbb",
        "mathcal",
        "mathsf",
        "mathtt",
        "operatorname",
        "displaystyle",
        "textstyle",
        "scriptstyle",
        "scriptscriptstyle",
        "begin",
        "end",
        "quad",
        "qquad",
        "hspace",
        "vspace",
        "phantom",
        "hphantom",
        "vphantom",
        "strut",
        "ldots",
        "cdots",
        "vdots",
        "ddots",
        "dots",
        "colon",
        "mid",
        "vert",
        "Vert",
        "lvert",
        "rvert",
        "lVert",
        "rVert",
        "langle",
        "rangle",
        "lbrace",
        "rbrace",
        "lceil",
        "rceil",
        "lfloor",
        "rfloor",
        "degree",
        "angle",
        "triangle",
        "parallel",
        "perp",
        "to",
        "rightarrow",
        "leftarrow",
        "leftrightarrow",
        "Rightarrow",
        "Leftarrow",
        "Leftrightarrow",
        "Longrightarrow",
        "Longleftrightarrow",
        "iff",
        "forall",
        "exists",
        "neg",
        "not",
        "land",
        "lor",
        "circ",
        "bullet",
        "therefore",
        "because",
        "binom",
        "dbinom",
        "tbinom",
        "underbrace",
        "overbrace",
        "underset",
        "overset",
        "substack",
        "cases",
        "det",
        "gcd",
        "Pr",
    ]
)
_ENV = re.compile(r"\\(?:begin|end)\s*\{([^}]*)\}")
_ENVIRONMENTS = {"aligned", "gathered", "array", "matrix", "pmatrix", "bmatrix", "cases"}


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def data_only(value: Any) -> None:
    """No executable formats, arbitrary TeX macros, unbounded trees or non-JSON values."""
    count = 0

    def walk(item: Any, depth: int) -> None:
        nonlocal count
        count += 1
        if depth > 16 or count > 12_000:
            raise ApiError(422, "invalid_content", "Слишком сложная структура JSON.", "payload")
        if isinstance(item, str):
            if len(item) > 16_000 or MARKUP.search(item):
                raise ApiError(
                    422,
                    "unsafe_content",
                    "HTML, SVG и слишком длинные строки запрещены.",
                    "payload",
                )
            if any(match not in _MATH_COMMANDS for match in _COMMAND.findall(item)):
                raise ApiError(
                    422,
                    "unsafe_formula",
                    "Формула содержит неподдерживаемую команду LaTeX.",
                    "payload",
                )
            if any(env not in _ENVIRONMENTS for env in _ENV.findall(item)):
                raise ApiError(422, "unsafe_formula", "Окружение LaTeX не разрешено.", "payload")
        elif isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str) or key in {"__proto__", "constructor", "prototype"}:
                    raise ApiError(422, "invalid_content", "Недопустимое поле JSON.", "payload")
                walk(child, depth + 1)
        elif isinstance(item, list):
            if len(item) > 1200:
                raise ApiError(422, "invalid_content", "Слишком длинный список.", "payload")
            for child in item:
                walk(child, depth + 1)
        elif item is not None and type(item) not in {bool, int, float}:
            raise ApiError(422, "invalid_content", "Нужны только значения JSON.", "payload")
        elif isinstance(item, float) and not math.isfinite(item):
            raise ApiError(422, "invalid_content", "Число должно быть конечным.", "payload")

    walk(value, 0)
    if (
        len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))
        > MAX_PAYLOAD_BYTES
    ):
        raise ApiError(422, "invalid_content", "Запись превышает 128 КиБ.", "payload")


def validation_error(exc: ValidationError) -> ApiError:
    details = []
    for error in exc.errors(include_input=False, include_context=False, include_url=False)[:8]:
        path = ".".join(str(part) for part in error["loc"])
        details.append(f"{path or 'payload'}: {error['msg']}")
    return ApiError(422, "invalid_content", "Проверьте данные: " + "; ".join(details), "payload")


def editable_payload(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Export a draft, never an imported assertion of authorship or review."""
    result = copy.deepcopy(payload)
    if kind != "template":
        result.pop("revision", None)
    if kind in {"task", "lesson"}:
        result.pop("review_status", None)
    if kind == "task":
        result["source"].pop("author", None)
        result["source"].pop("reviewed_by", None)
    if kind == "lesson":
        result.pop("author_id", None)
        result.pop("reviewed_by", None)
    return result


def validate_payload(
    kind: Kind,
    payload: dict[str, Any],
    *,
    author_id: str,
    revision_id: str,
) -> dict[str, Any]:
    data_only(payload)
    result = copy.deepcopy(payload)
    managed = {"author_id", "reviewer_id", "reviewed_by", "published_at", "status"}
    if kind == "profile":
        managed.remove("status")
    if kind != "template":
        managed.add("revision")
    if kind in {"task", "lesson"}:
        managed.add("review_status")
    if managed & result.keys():
        raise ApiError(
            422,
            "managed_field",
            "Автор, проверка и редакция задаются сервером.",
            "payload",
        )
    if not isinstance(result.get("id"), str) or not _ID.fullmatch(result["id"]):
        raise ApiError(422, "invalid_content", "Нужен стабильный id без пробелов и слешей.", "id")
    if kind != "template":
        result["revision"] = f"ed-{revision_id}"
    if kind in {"task", "lesson"}:
        if kind == "lesson" and result.get("kind") == "foundation":
            if (
                result.get("slot_id") is not None
                or result.get("slot") != 0
                or not result.get("related_slot_ids")
            ):
                raise ApiError(
                    422,
                    "slot_mapping_required",
                    "Для базового урока нужны slot=0, slot_id=null и связанные related_slot_ids.",
                    "related_slot_ids",
                )
        elif not result.get("slot_id"):
            raise ApiError(422, "slot_mapping_required", "Укажите стабильный slot_id.", "slot_id")
        result["review_status"] = "demo"
    if kind == "task":
        source = result.get("source")
        if not isinstance(source, dict) or {"author", "reviewed_by"} & source.keys():
            raise ApiError(
                422,
                "managed_field",
                "В source укажите только origin и rights.",
                "source",
            )
        result["source"] = {**source, "author": author_id, "reviewed_by": None}
    if kind == "lesson":
        result.update(author_id=author_id, reviewed_by=None)
    model = {"task": Task, "lesson": Lesson, "profile": ProfileSource, "template": TemplatePayload}
    try:
        parsed = model[kind].model_validate(result)
    except ValidationError as exc:
        raise validation_error(exc) from exc
    canonical = parsed.model_dump(mode="json")
    if not canonical["title"].strip() or len(canonical["title"]) > 300:
        raise ApiError(422, "invalid_content", "Название: от 1 до 300 символов.", "title")
    if kind == "task":
        if not all(canonical["source"][key].strip() for key in ("origin", "rights")):
            raise ApiError(422, "invalid_content", "Укажите источник и права.", "source")
        if canonical.get("generation"):
            registered_family(canonical["generation"]["template_id"])
    if kind == "template":
        registered_family(canonical["generator_id"])
    return canonical


def registered_families() -> dict[str, Any]:
    # Imported lazily to keep the content repository independent of generator startup.
    from app import generators

    families = getattr(generators, "FAMILIES", None)
    if families is None:
        return {}
    values = families.values() if isinstance(families, dict) else families
    return {family.id: family for family in values if family.supports_runtime}


def registered_family(identifier: str) -> Any:
    family = registered_families().get(identifier)
    if family is None:
        raise ApiError(
            422,
            "unregistered_generator",
            "Генератор не зарегистрирован для выполнения на сервере.",
            "generation",
        )
    return family


def generate_sample(template: dict[str, Any], seed: int, profile: ProfileSource) -> Task:
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ApiError(422, "invalid_seed", "Seed: целое число от 0 до 4294967295.", "seed")
    family = registered_family(template["generator_id"])
    if template["profile_id"] != profile.id or template["family_id"] != family.id:
        raise ApiError(422, "template_mapping", "Не совпадают профиль и семейство шаблона.")
    position = next((slot for slot in profile.slots if slot.id == template["slot_id"]), None)
    if (
        position is None
        or position.number != family.slot
        or set(template["skill_ids"]) != set(family.skill_ids)
    ):
        raise ApiError(
            422, "template_mapping", "Нужна явная привязка генератора к позиции и навыкам."
        )
    try:
        raw = family.generate(seed, profile)
        data_only(raw)
        task = Task.model_validate(raw)
    except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
        raise ApiError(422, "generator_failed", "Генератор не прошёл проверку результата.") from exc
    if (
        task.generation is None
        or task.generation.seed != seed
        or task.generation.template_id != family.id
        or task.generation.template_version != template["generator_version"]
        or task.family_id != family.id
        or task.profile_id != profile.id
        or task.slot_id != position.id
        or task.slot != position.number
        or set(task.skill_ids) != set(template["skill_ids"])
    ):
        raise ApiError(422, "generator_version", "Версия или привязка результата не совпадает.")
    return task


def validate_generation(task: Task, profile: ProfileSource) -> None:
    if task.generation is None:
        return
    template = {
        "generator_id": task.generation.template_id,
        "generator_version": task.generation.template_version,
        "family_id": task.family_id,
        "profile_id": task.profile_id,
        "slot_id": task.slot_id,
        "skill_ids": task.skill_ids,
    }
    generated = generate_sample(template, task.generation.seed, profile)
    # These are the mathematical snapshot fields. Identity and editorial provenance differ.
    fields = (
        "statement",
        "answer",
        "formula",
        "table",
        "figure",
        "rounding",
        "hints",
        "solution",
    )
    if any(getattr(generated, field) != getattr(task, field) for field in fields):
        raise ApiError(
            422,
            "generation_mismatch",
            "Снимок не воспроизводится по генератору, версии и seed. "
            "Для самостоятельной редакции удалите generation.",
            "generation",
        )


def validate_links(bundle: ContentBundle) -> None:
    lessons = {lesson.id: lesson for lesson in bundle.lessons}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in visiting:
            raise ContentError("Цикл в связях предварительных уроков.")
        if identifier in visited:
            return
        if identifier not in lessons:
            raise ContentError("Неизвестный предварительный урок.")
        visiting.add(identifier)
        for prerequisite in lessons[identifier].prerequisite_ids:
            visit(prerequisite)
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in lessons:
        visit(identifier)
