from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PersistedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class BookMetadata(PersistedModel):
    schema_version: int = 1
    book_slug: str
    source_url: str
    title: str
    author: str | None = None


class ChapterCatalogEntry(PersistedModel):
    chapter_id: int = Field(gt=0)
    slug: str
    source_url: str
    original_title: str
    raw_filename: str
    translation_filename: str


class ChapterCatalog(PersistedModel):
    schema_version: int = 1
    chapters: list[ChapterCatalogEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_duplicates(self) -> ChapterCatalog:
        for field in ("chapter_id", "raw_filename", "translation_filename"):
            values = [getattr(chapter, field) for chapter in self.chapters]
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate catalog {field}")
        return self


class StageStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    ERROR = "error"


class StageRecord(PersistedModel):
    status: StageStatus = StageStatus.PENDING
    canonical_path: str | None = None
    sha256: str | None = None
    updated_at: datetime | None = None
    error: str | None = None

    @model_validator(mode="after")
    def completed_stage_has_artifact(self) -> StageRecord:
        if self.status is StageStatus.COMPLETED and (
            not self.canonical_path or not self.sha256
        ):
            raise ValueError("completed stage requires canonical_path and sha256")
        return self


class ChapterState(PersistedModel):
    chapter_id: int = Field(gt=0)
    raw: StageRecord = Field(default_factory=StageRecord)
    translation: StageRecord = Field(default_factory=StageRecord)


class BookState(PersistedModel):
    schema_version: int = 1
    chapters: list[ChapterState] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_duplicate_chapters(self) -> BookState:
        chapter_ids = [chapter.chapter_id for chapter in self.chapters]
        if len(chapter_ids) != len(set(chapter_ids)):
            raise ValueError("duplicate state chapter_id")
        return self


class CheckpointType(str, Enum):
    CRAWL_APPROVED = "crawl-approved"
    QA_APPROVED = "qa-approved"


class CheckpointRecord(PersistedModel):
    checkpoint_type: CheckpointType
    approved_at: datetime
    report_path: str
    evidence_hashes: dict[str, str] = Field(default_factory=dict)


class TranslationStyle(PersistedModel):
    name: str
    description: str
    guidelines: list[str] = Field(default_factory=list)
    vocabulary: dict[str, str] = Field(default_factory=dict)
    tone: str
    examples: list[str] = Field(default_factory=list)


class ProgressSummary(PersistedModel):
    completed: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)
    current_chapter_id: int | None = Field(default=None, gt=0)


class OperationStatus(str, Enum):
    OK = "ok"
    BLOCKED = "blocked"
    ERROR = "error"


class OperationResult(PersistedModel):
    status: OperationStatus
    reason: str
    progress: ProgressSummary | None = None
    report_paths: list[str] = Field(default_factory=list)
    approval_path: str | None = None
    orphan_temp_paths: list[str] = Field(default_factory=list)


def as_workspace_relative(path: str) -> PurePosixPath:
    """Normalize a persisted relative path without accepting traversal."""
    normalized = PurePosixPath(path)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError(f"path must stay workspace-relative: {path}")
    return normalized
