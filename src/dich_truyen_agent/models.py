from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from pathlib import PurePosixPath
from pathlib import Path
from typing import Literal

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
    translated_title: str | None = None
    translated_author: str | None = None


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


class TranslationSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DICH_TRUYEN_TRANSLATION_",
        extra="ignore",
    )

    batch_size: int = Field(default=5, ge=1)


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


class CrawlBrowserViewportProfile(PersistedModel):
    width: int = Field(default=1280, gt=0)
    height: int = Field(default=800, gt=0)


class CrawlBrowserChallengeProfile(PersistedModel):
    title_markers: list[str] = Field(default_factory=list)
    max_wait_seconds: float = Field(default=0, ge=0)
    poll_seconds: float = Field(default=1.0, gt=0)

    @model_validator(mode="after")
    def reject_blank_title_markers(self) -> CrawlBrowserChallengeProfile:
        if any(not marker.strip() for marker in self.title_markers):
            raise ValueError("browser challenge title markers must not be blank")
        return self


class CrawlBrowserSessionWarmupProfile(PersistedModel):
    url_pattern: str | None = Field(default=None, min_length=1)
    warmup_url: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_warmup_placeholders(self) -> CrawlBrowserSessionWarmupProfile:
        compiled_pattern = None
        if self.url_pattern is not None:
            try:
                compiled_pattern = re.compile(self.url_pattern)
            except re.error as exc:
                raise ValueError(f"invalid browser warmup url_pattern: {exc}") from exc

        placeholders = set(re.findall(r"{([A-Za-z_][A-Za-z0-9_]*)}", self.warmup_url))
        if not placeholders:
            return self
        if compiled_pattern is None:
            raise ValueError("warmup URL placeholders require url_pattern")

        groups = set(compiled_pattern.groupindex)
        unknown = sorted(placeholders - groups)
        if unknown:
            raise ValueError(f"unknown warmup placeholder(s): {unknown}")
        return self


class CrawlBrowserSessionProfile(PersistedModel):
    warmups: list[CrawlBrowserSessionWarmupProfile] = Field(default_factory=list)


class CrawlBrowserNavigationProfile(PersistedModel):
    wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] = "domcontentloaded"
    timeout_milliseconds: int = Field(default=30000, gt=0)


class CrawlBrowserIndexProfile(PersistedModel):
    wait_for_response_url_contains: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_blank_response_markers(self) -> CrawlBrowserIndexProfile:
        if any(not marker.strip() for marker in self.wait_for_response_url_contains):
            raise ValueError("browser response URL markers must not be blank")
        return self


class CrawlBrowserActionProfile(PersistedModel):
    purpose: Literal["all", "index", "chapter"] = "all"
    action: Literal["click", "wait_for_selector", "wait_for_response_url_contains"]
    selector: str | None = Field(default=None, min_length=1)
    wait_for_selector: str | None = Field(default=None, min_length=1)
    url_contains: str | None = Field(default=None, min_length=1)
    timeout_milliseconds: int = Field(default=10000, gt=0)

    @model_validator(mode="after")
    def validate_action_target(self) -> CrawlBrowserActionProfile:
        if self.action in {"click", "wait_for_selector"} and not self.selector:
            raise ValueError(f"browser action {self.action!r} requires selector")
        if self.action == "wait_for_response_url_contains" and not self.url_contains:
            raise ValueError("browser response wait action requires url_contains")
        return self


class CrawlBrowserProfile(PersistedModel):
    enabled: bool = False
    strategy: str | None = Field(default=None, min_length=1)
    launch_args: list[str] = Field(default_factory=list)
    user_agent: str | None = Field(default=None, min_length=1)
    viewport: CrawlBrowserViewportProfile = Field(default_factory=CrawlBrowserViewportProfile)
    init_scripts: list[str] = Field(default_factory=list)
    challenge: CrawlBrowserChallengeProfile = Field(default_factory=CrawlBrowserChallengeProfile)
    session: CrawlBrowserSessionProfile = Field(default_factory=CrawlBrowserSessionProfile)
    navigation: CrawlBrowserNavigationProfile = Field(default_factory=CrawlBrowserNavigationProfile)
    index: CrawlBrowserIndexProfile = Field(default_factory=CrawlBrowserIndexProfile)
    actions: list[CrawlBrowserActionProfile] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_blank_string_lists(self) -> CrawlBrowserProfile:
        for field_name in ("launch_args", "init_scripts"):
            values = getattr(self, field_name)
            if any(not value.strip() for value in values):
                raise ValueError(f"browser {field_name} entries must not be blank")
        return self


class CrawlProfile(PersistedModel):
    schema_version: int = 1
    domain: str = Field(min_length=1)
    index: CrawlIndexProfile
    chapter: CrawlChapterProfile
    encoding: CrawlEncodingProfile = Field(default_factory=CrawlEncodingProfile)
    validation: CrawlValidationProfile = Field(default_factory=CrawlValidationProfile)
    browser: CrawlBrowserProfile = Field(default_factory=CrawlBrowserProfile)


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
    data: dict = Field(default_factory=dict)


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


class GlossaryContextTerm(PersistedModel):
    translation: str = Field(min_length=1)
    category: str = Field(default="other")
    source: str = Field(min_length=1)
    is_canonical: bool = Field(default=False)
    note: str | None = None
    rejected_aliases: list[str] = Field(default_factory=list)


class GlossaryContext(PersistedModel):
    schema_version: int = 1
    chapter_id: int = Field(gt=0)
    terms: dict[str, GlossaryContextTerm] = Field(default_factory=dict)


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
