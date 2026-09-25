from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
from typing import Any
import uuid

from pydantic import BaseModel, Field, field_validator, model_validator

PHASES = ("crawl", "translate", "qa", "export")
VALID_START_AT = ("auto", "crawl", "translate", "qa", "export")
VALID_STOP_AFTER = ("crawl", "translate", "qa", "export")


class OrchestratorConfig(BaseModel):
    """Configuration for an orchestrator run, validating CLI arguments, env vars, and defaults."""

    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workspace_root: Path
    start_at: str = "auto"
    stop_after: str = "export"
    formats: list[str] = Field(default_factory=lambda: ["epub", "txt"])
    batch_size: int = 5
    timeout_seconds: int = 1800
    crawl_timeout_seconds: int = 1800
    qa_timeout_seconds: int = 600
    export_timeout_seconds: int = 600
    max_repair_attempts: int = 3
    max_chapter_attempts: int = 3
    auto_approve: bool = False
    allow_warnings: bool = False
    allow_harness_permission_bypass: bool = False
    global_model: str | None = None
    translation_model: str | None = None
    effective_model: str = "unknown"

    @field_validator("run_id")
    @classmethod
    def validate_run_id_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError as err:
            raise ValueError(f"run_id must be a valid UUID string: {err}") from err
        return v

    @field_validator("start_at")
    @classmethod
    def validate_start_at(cls, v: str) -> str:
        if v not in VALID_START_AT:
            raise ValueError(f"invalid start_at: {v!r}; must be one of {VALID_START_AT}")
        return v

    @field_validator("stop_after")
    @classmethod
    def validate_stop_after(cls, v: str) -> str:
        if v not in VALID_STOP_AFTER:
            raise ValueError(f"invalid stop_after: {v!r}; must be one of {VALID_STOP_AFTER}")
        return v

    @field_validator(
        "batch_size",
        "timeout_seconds",
        "crawl_timeout_seconds",
        "qa_timeout_seconds",
        "export_timeout_seconds",
        "max_repair_attempts",
        "max_chapter_attempts",
    )
    @classmethod
    def validate_positive_int(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"must be positive: {v}")
        return v

    @model_validator(mode="after")
    def validate_phase_span(self) -> OrchestratorConfig:
        if self.start_at != "auto":
            start_idx = PHASES.index(self.start_at)
            stop_idx = PHASES.index(self.stop_after)
            if start_idx > stop_idx:
                raise ValueError(
                    f"invalid phase span: stop_after ({self.stop_after!r}) cannot precede start_at ({self.start_at!r})"
                )
        return self

    @classmethod
    def resolve_batch_size(cls, explicit_batch_size: int | None = None, env_file: Path | None = None) -> int:
        """Resolve translation batch size with precedence: CLI explicit -> .env / env var -> default 5."""
        if explicit_batch_size is not None and explicit_batch_size > 0:
            return explicit_batch_size

        env_val = os.environ.get("DICH_TRUYEN_TRANSLATION_BATCH_SIZE")
        if env_val:
            try:
                val = int(env_val.strip())
                if val > 0:
                    return val
            except ValueError:
                pass

        if env_file and env_file.is_file():
            try:
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("DICH_TRUYEN_TRANSLATION_BATCH_SIZE="):
                        val_str = line.split("=", 1)[1].strip().strip('"').strip("'")
                        val = int(val_str)
                        if val > 0:
                            return val
            except Exception:
                pass

        return 5


class RunSummary(BaseModel):
    """Compact summary persisted to reports/runs/<run_id>/run_summary.json."""

    schema_version: int = 1
    run_id: str
    status: str = "running"  # running, paused, blocked, completed, error, superseded
    start_at: str
    stop_after: str
    selected_span: tuple[str, str]
    current_phase: str
    requested_formats: list[str]
    global_model: str | None = None
    translation_model: str | None = None
    effective_model: str = "unknown"
    allow_harness_permission_bypass: bool = False
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    completed_chapters: int = 0
    total_chapters: int = 0
    pending_approval: str | None = None
    approval_report_path: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    invocations: list[dict[str, Any]] = Field(default_factory=list)
    report_paths: list[str] = Field(default_factory=list)
