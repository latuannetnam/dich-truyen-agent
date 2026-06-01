from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import PurePosixPath
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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


class ApprovalScope(str, Enum):
    FULL = "full"
    PARTIAL = "partial"


class CheckpointRecord(PersistedModel):
    checkpoint_type: CheckpointType
    approved_at: datetime
    report_path: str
    evidence_hashes: dict[str, str] = Field(default_factory=dict)
    scope: ApprovalScope = ApprovalScope.FULL


class TranslationStyle(PersistedModel):
    name: str
    description: str
    guidelines: list[str] = Field(default_factory=list)
    vocabulary: dict[str, str] = Field(default_factory=dict)
    tone: str
    examples: list[str | dict[str, str]] = Field(default_factory=list)


class CrawlSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DICH_TRUYEN_CRAWL_",
        extra="forbid",
    )

    max_chapters: int = Field(default=0, ge=0)
    chapter_delay_seconds: float = Field(default=3.0, ge=0)
    max_attempts: int = Field(default=3, gt=0)
    backoff_seconds: float = Field(default=1.0, ge=0)
    timeout_seconds: float = Field(default=30.0, gt=0)
    user_agent: str = "dich-truyen-agent/0.1"


class CrawlIndexProfile(PersistedModel):
    chapter_link_selector: str = Field(min_length=1)
    pagination_selector: str | None = None
    list_section_selectors: list[str] = Field(default_factory=list)


class CrawlChapterProfile(PersistedModel):
    title_selector: str = Field(min_length=1)
    content_selector: str = Field(min_length=1)
    remove_selectors: list[str] = Field(default_factory=list)


class CrawlEncodingProfile(PersistedModel):
    index: str | None = Field(default=None, min_length=1)
    chapter: str | None = Field(default=None, min_length=1)


class CrawlValidationProfile(PersistedModel):
    min_chapter_characters: int = Field(default=1, gt=0)


class CrawlProfile(PersistedModel):
    schema_version: int = 1
    domain: str = Field(min_length=1)
    index: CrawlIndexProfile
    chapter: CrawlChapterProfile
    encoding: CrawlEncodingProfile = Field(default_factory=CrawlEncodingProfile)
    validation: CrawlValidationProfile = Field(default_factory=CrawlValidationProfile)


class ProfileSource(PersistedModel):
    shared_path: Path
    local_path: Path
    active_path: Path
    is_local_override: bool
    profile: CrawlProfile


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


class DiscoveredChapter(PersistedModel):
    position: int = Field(gt=0)
    source_id: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    original_title: str = Field(min_length=1)
    parsed_ordinal: int | None = Field(default=None, ge=0)


class ExtractedChapter(PersistedModel):
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    encoding: str = Field(min_length=1)
    encoding_source: str = Field(min_length=1)


class CrawlReport(PersistedModel):
    schema_version: int = 1
    discovered_count: int = Field(ge=0)
    selected_count: int = Field(ge=0)
    completed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    max_chapters: int = Field(ge=0)
    scope: ApprovalScope
    active_profile_source: str = Field(min_length=1)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    chapter_lengths: dict[str, int] = Field(default_factory=dict)
    suspicious_residue_findings: dict[str, list[str]] = Field(default_factory=dict)
    excerpts: dict[str, dict[str, str]] = Field(default_factory=dict)


class GlossaryTerm(PersistedModel):
    translation: str = Field(min_length=1)
    category: str = Field(default="other")  # character, sect, location, item, cultivation, other
    source: str = Field(min_length=1)      # manual, initial_generation, chapter_N_proposal
    is_canonical: bool = Field(default=False)
    note: str | None = None


class BookGlossary(PersistedModel):
    schema_version: int = 1
    terms: dict[str, GlossaryTerm] = Field(default_factory=dict)  # Chinese term -> GlossaryTerm


class GlossaryConflict(PersistedModel):
    term: str = Field(min_length=1)
    existing_translation: str = Field(min_length=1)
    existing_source: str = Field(min_length=1)
    proposed_translation: str = Field(min_length=1)
    proposed_source: str = Field(min_length=1)
    chapter_id: int = Field(gt=0)


class GlossaryConflictReport(PersistedModel):
    schema_version: int = 1
    conflicts: list[GlossaryConflict] = Field(default_factory=list)


class QAFindingType(str, Enum):
    STRUCTURAL = "structural"
    RESIDUE = "residue"
    LENGTH = "length"
    GLOSSARY = "glossary"


class QAFinding(PersistedModel):
    chapter_id: int = Field(gt=0)
    finding_type: QAFindingType
    severity: str = Field(default="warning")  # warning, error
    message: str = Field(min_length=1)
    details: dict = Field(default_factory=dict)


class QAReport(PersistedModel):
    schema_version: int = 1
    generated_at: datetime = Field(default_factory=datetime.now)
    summary: dict = Field(default_factory=dict)
    findings: list[QAFinding] = Field(default_factory=list)


