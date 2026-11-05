"""Explicit server-owned generators and reproducible, unreviewed snapshots.

``generate`` is the runtime allowlist. ``reproduce`` also accepts static-only
families for builds and editorial verification; it does not enable their issuance.
"""

from collections import Counter
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit

from app.content import ContentError, Task
from app.generators import algebra_analysis, applied_finance, geometry_probability
from app.generators.base import Family
from app.schemas import ProfileSource

FAMILIES: tuple[Family, ...] = (
    geometry_probability.FAMILIES + algebra_analysis.FAMILIES + applied_finance.FAMILIES
)
RUNTIME_FAMILIES: tuple[Family, ...] = tuple(
    family for family in FAMILIES if family.supports_runtime
)
FAMILY_BY_ID = MappingProxyType({family.id: family for family in FAMILIES})
_RUNTIME_BY_ID = MappingProxyType({family.id: family for family in RUNTIME_FAMILIES})
MAX_SEED = 2**32 - 1

if len(FAMILY_BY_ID) != 78 or len(FAMILIES) != 78:
    raise RuntimeError("The course requires 78 uniquely registered families")
if Counter(family.slot for family in RUNTIME_FAMILIES) != dict.fromkeys(range(1, 14), 2):
    raise RuntimeError("The course requires exactly two runtime families per slot")


def _seed(seed: int) -> None:
    if type(seed) is not int or not 0 <= seed <= MAX_SEED:
        raise ValueError("Seed must be an unsigned 32-bit integer")


def _data_only(value: Any) -> None:
    # The editor imports the registry lazily too; neither module executes imports
    # or expressions supplied by a content record.
    from app.editor.validation import data_only
    from app.errors import ApiError

    try:
        data_only(value)
    except ApiError as exc:
        raise ContentError("Content is not safe bounded JSON") from exc


def _validated_profile(profile: ProfileSource) -> ProfileSource:
    if not isinstance(profile, ProfileSource):
        raise ContentError("A validated ProfileSource is required")
    # Revalidate a dict, because Pydantic normally trusts existing model instances
    # even after an in-place mutation of a nested list.
    raw = profile.model_dump(mode="python", warnings=False)
    _data_only(raw)
    parsed = ProfileSource.model_validate(raw)
    if len({slot.number for slot in parsed.slots}) != len(parsed.slots):
        raise ContentError("Profile slot numbers must be unique")
    if len({slot.id for slot in parsed.slots}) != len(parsed.slots):
        raise ContentError("Profile slot identifiers must be unique")
    for slot in parsed.slots:
        if len({skill.id for skill in slot.skills}) != len(slot.skills):
            raise ContentError("Profile skill identifiers must be unique within a slot")
    for url in parsed.source_urls:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ContentError("Profile source URLs must use HTTP or HTTPS")
    return parsed


def _generate(family: Family, seed: int, profile: ProfileSource) -> Task:
    """Internal build path: the supplied profile has already been revalidated."""
    _seed(seed)
    slot = next((slot for slot in profile.slots if slot.number == family.slot), None)
    if slot is None or not set(family.skill_ids) <= {skill.id for skill in slot.skills}:
        raise ContentError("Generator requires its registered profile slot and skills")
    try:
        raw = family.generate(seed, profile)
        _data_only(raw)
        task = Task.model_validate(raw)
    except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
        raise ContentError(f"Invalid generated task for {family.id}") from exc
    if (
        task.id != f"course-{family.id}-{seed}"
        or task.revision != "1"
        or task.family_id != family.id
        or task.slot != slot.number
        or task.slot_id != slot.id
        or task.profile_id != profile.id
        or set(task.skill_ids) != set(family.skill_ids)
        or task.generation is None
        or task.generation.template_id != family.id
        or task.generation.template_version != "1"
        or task.generation.seed != seed
        or task.review_status != "demo"
        or task.source.reviewed_by is not None
    ):
        raise ContentError(f"Generated task does not match its registered binding: {family.id}")
    return task


def generate(template_id: str, seed: int, profile: ProfileSource) -> Task:
    """Generate a validated Task using only one of the 26 runtime templates.

    Seeds are strict uint32 integers, including both boundaries. Booleans,
    coercible strings and floats are rejected. Equal inputs produce equal
    snapshots, but distinct seeds need not produce distinct mathematical tasks.
    """
    _seed(seed)
    if not isinstance(template_id, str) or template_id not in _RUNTIME_BY_ID:
        raise ValueError("Template is not registered for runtime generation")
    return _generate(_RUNTIME_BY_ID[template_id], seed, _validated_profile(profile))


def reproduce(template_id: str, seed: int, profile: ProfileSource) -> Task:
    """Reproduce any of the 78 registered families for static/editorial use."""
    _seed(seed)
    if not isinstance(template_id, str) or template_id not in FAMILY_BY_ID:
        raise ValueError("Template is not registered for static reproduction")
    return _generate(FAMILY_BY_ID[template_id], seed, _validated_profile(profile))


__all__ = ["FAMILIES", "FAMILY_BY_ID", "RUNTIME_FAMILIES", "generate", "reproduce"]
