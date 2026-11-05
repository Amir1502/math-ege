"""Recorded server checks and authenticated human attestations for templates.

The automated checks are structural, reproducibility and finite-answer checks.
They are explicitly not represented as an independent mathematical review.
"""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.editor.models import EditorRevision, TemplateCheckRun, TemplateHumanReview
from app.editor.repository import combined_content
from app.editor.schemas import (
    CheckResult,
    EditorActor,
    EvidenceSummary,
    SampleReview,
    TemplateSample,
)
from app.editor.validation import digest, generate_sample
from app.errors import ApiError
from app.schemas import ProfileSource
from app.services import LearningService

SEEDS = (*range(998), 2**32 - 2, 2**32 - 1)
CHECKS = [
    "strict_schema",
    "finite_exam_answer",
    "deterministic_snapshot",
    "profile_binding",
    "version_seed",
]


class TemplateEvidence:
    def __init__(self, learning: LearningService) -> None:
        self.learning = learning

    def profile(self, db: Session, record: EditorRevision) -> ProfileSource:
        linked = record.payload.get("profile_revision_id")
        if linked is not None:
            revision = db.get(EditorRevision, linked)
            if (
                revision is None
                or revision.kind != "profile"
                or revision.status == "archived"
                or revision.content_id != record.payload["profile_id"]
            ):
                raise ApiError(422, "template_profile", "Укажите доступную редакцию профиля.")
            return ProfileSource.model_validate(revision.payload)
        return combined_content(db, self.learning.settings).profile

    def sample(self, db: Session, record: EditorRevision, seed: int) -> TemplateSample:
        task = generate_sample(record.payload, seed, self.profile(db, record))
        return TemplateSample(
            seed=seed, output_hash=digest(task.model_dump(mode="json")), task=task
        )

    def run(self, db: Session, record: EditorRevision, actor: EditorActor) -> CheckResult:
        profile = self.profile(db, record)
        hashes: dict[str, str] = {}
        failure = None
        for seed in SEEDS:
            try:
                first = generate_sample(record.payload, seed, profile).model_dump(mode="json")
                second = generate_sample(record.payload, seed, profile).model_dump(mode="json")
                if first != second:
                    raise ApiError(422, "nondeterministic_generator", "Генерация невоспроизводима.")
                hashes[str(seed)] = digest(first)
            except ApiError as exc:
                failure = f"Seed {seed}: {exc.message}"
                break
        run = TemplateCheckRun(
            id=str(uuid4()),
            revision_id=record.id,
            payload_hash=record.payload_hash,
            profile_hash=digest(profile.model_dump(mode="json")),
            generator_version=record.payload["generator_version"],
            checked_revision=record.revision,
            seed_count=len(hashes),
            output_hashes=hashes,
            checks=CHECKS,
            passed=failure is None and len(hashes) == 1000,
            failure=failure,
            actor_id=actor.id,
            created_at=self.learning.clock(),
        )
        db.add(run)
        db.flush()
        return CheckResult(
            id=run.id,
            passed=run.passed,
            seed_count=run.seed_count,
            checks=run.checks,
            failure=run.failure,
        )

    @staticmethod
    def _records(db: Session, record: EditorRevision, profile: ProfileSource):
        profile_hash = digest(profile.model_dump(mode="json"))
        run = db.scalar(
            select(TemplateCheckRun)
            .where(
                TemplateCheckRun.revision_id == record.id,
                TemplateCheckRun.payload_hash == record.payload_hash,
                TemplateCheckRun.profile_hash == profile_hash,
            )
            .order_by(TemplateCheckRun.checked_revision.desc())
            .limit(1)
        )
        reviews = list(
            db.scalars(
                select(TemplateHumanReview).where(
                    TemplateHumanReview.revision_id == record.id,
                    TemplateHumanReview.payload_hash == record.payload_hash,
                    TemplateHumanReview.profile_hash == profile_hash,
                )
            )
        )
        return run, reviews

    def summary(self, db: Session, record: EditorRevision) -> EvidenceSummary:
        try:
            profile = self.profile(db, record)
        except (ApiError, ValueError):
            return EvidenceSummary(
                automated_seeds=0,
                automated_passed=False,
                reviewed_seeds=[],
                rejected_seeds=[],
                checks=[],
                failure="Привязанный профиль недоступен; доказательства не действуют.",
            )
        run, reviews = self._records(db, record, profile)
        return EvidenceSummary(
            automated_seeds=run.seed_count if run else 0,
            automated_passed=run.passed if run else False,
            reviewed_seeds=sorted({review.seed for review in reviews if review.approved}),
            rejected_seeds=sorted({review.seed for review in reviews if not review.approved}),
            checks=run.checks if run else [],
            failure=run.failure if run else None,
        )

    def review(
        self,
        db: Session,
        record: EditorRevision,
        actor: EditorActor,
        body: SampleReview,
    ) -> None:
        profile = self.profile(db, record)
        task = generate_sample(record.payload, body.seed, profile).model_dump(mode="json")
        output_hash = digest(task)
        if output_hash != body.output_hash:
            raise ApiError(409, "sample_changed", "Результат изменился. Откройте его заново.")
        profile_hash = digest(profile.model_dump(mode="json"))
        existing = db.scalar(
            select(TemplateHumanReview.id).where(
                TemplateHumanReview.revision_id == record.id,
                TemplateHumanReview.payload_hash == record.payload_hash,
                TemplateHumanReview.profile_hash == profile_hash,
                TemplateHumanReview.reviewer_id == actor.id,
                TemplateHumanReview.seed == body.seed,
            )
        )
        if existing:
            raise ApiError(409, "sample_already_reviewed", "Этот seed уже проверен вами.")
        db.add(
            TemplateHumanReview(
                id=str(uuid4()),
                revision_id=record.id,
                payload_hash=record.payload_hash,
                profile_hash=profile_hash,
                seed=body.seed,
                output_hash=output_hash,
                output_snapshot=task,
                approved=body.approved,
                reviewer_id=actor.id,
                note=body.note,
                created_at=self.learning.clock(),
            )
        )

    def gate(
        self,
        db: Session,
        record: EditorRevision,
        reviewer_id: str,
        profile: ProfileSource | None = None,
    ) -> None:
        profile = profile if profile is not None else self.profile(db, record)
        run, reviews = self._records(db, record, profile)
        if (
            run is None
            or not run.passed
            or run.seed_count != 1000
            or set(run.output_hashes) != {str(seed) for seed in SEEDS}
        ):
            raise ApiError(
                422,
                "template_evidence_required",
                "Нужен успешный серверный протокол 1000 разных seed, включая границы uint32.",
            )
        if any(not review.approved for review in reviews):
            raise ApiError(422, "template_rejected", "Есть отклонённый результат генератора.")
        own = [
            review for review in reviews if review.reviewer_id == reviewer_id and review.approved
        ]
        if reviewer_id == record.author_id or len({review.seed for review in own}) < 10:
            raise ApiError(
                422,
                "human_review_required",
                "Нужны 10 разных результатов, проверенных этим независимым методистом.",
            )
        # Code and profile may change after the run. Reproduce the recorded manifest
        # before accepting it; a version string or client-provided count is not proof.
        for seed in SEEDS:
            result = generate_sample(record.payload, seed, profile).model_dump(mode="json")
            if digest(result) != run.output_hashes[str(seed)]:
                raise ApiError(
                    409, "template_evidence_stale", "Генератор изменился после проверки."
                )
        for review in own:
            result = generate_sample(record.payload, review.seed, profile).model_dump(mode="json")
            if digest(result) != review.output_hash:
                raise ApiError(
                    409,
                    "template_evidence_stale",
                    "Ручная проверка относится к другому результату.",
                )
