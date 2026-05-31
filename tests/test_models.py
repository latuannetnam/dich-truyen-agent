from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from dich_truyen_agent.models import (
    BookState,
    ChapterCatalog,
    ChapterCatalogEntry,
    ChapterState,
    CheckpointRecord,
    OperationResult,
    OperationStatus,
    StageRecord,
    StageStatus,
)


def catalog_entry(chapter_id: int = 1, suffix: str = "one") -> ChapterCatalogEntry:
    return ChapterCatalogEntry(
        chapter_id=chapter_id,
        slug=f"chapter-{suffix}",
        source_url=f"https://example.com/{suffix}",
        original_title=f"Chapter {suffix}",
        raw_filename=f"{chapter_id:04d}-{suffix}.txt",
        translation_filename=f"{chapter_id:04d}-{suffix}.txt",
    )


def test_catalog_round_trips() -> None:
    catalog = ChapterCatalog(chapters=[catalog_entry()])
    assert ChapterCatalog.model_validate(catalog.model_dump()) == catalog


@pytest.mark.parametrize("field", ["chapter_id", "raw_filename", "translation_filename"])
def test_catalog_rejects_duplicate_identity_fields(field: str) -> None:
    first = catalog_entry()
    second = catalog_entry(2, "two")
    setattr(second, field, getattr(first, field))
    with pytest.raises(ValidationError):
        ChapterCatalog(chapters=[first, second])


def test_state_rejects_duplicate_chapter_ids() -> None:
    state = ChapterState(chapter_id=1)
    with pytest.raises(ValidationError):
        BookState(chapters=[state, state])


def test_unknown_checkpoint_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CheckpointRecord(
            checkpoint_type="unexpected",
            approved_at=datetime.now(UTC),
            report_path="reports/review.yaml",
        )


def test_operation_result_is_compact() -> None:
    result = OperationResult(status=OperationStatus.OK, reason="ready")
    assert "chapter_body" not in OperationResult.model_fields
    assert set(result.model_dump()) == {
        "status",
        "reason",
        "progress",
        "report_paths",
        "approval_path",
        "orphan_temp_paths",
    }


def test_completed_stage_record_requires_hash_and_path() -> None:
    with pytest.raises(ValidationError):
        StageRecord(status=StageStatus.COMPLETED)
