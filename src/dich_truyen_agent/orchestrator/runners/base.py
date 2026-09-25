from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field


class HarnessRunResult(BaseModel):
    """Execution facts reported by a harness runner. Does not claim domain success."""

    exit_code: int | None = None
    timed_out: bool = False
    cancelled: bool = False
    started_at: datetime
    ended_at: datetime
    stdout_path: Path
    stderr_path: Path
    failure_detail: str | None = None
    argv: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)

    @property
    def finished_at(self) -> datetime:
        return self.ended_at


class HarnessRunner(Protocol):
    """Protocol for harness agent runners."""

    def run_phase(
        self,
        *,
        phase: str,
        workspace: Path,
        prompt: str,
        model: str | None = None,
        timeout_seconds: int = 1800,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> HarnessRunResult: ...


def resolve_model_for_phase(
    phase: str,
    *,
    global_model: str | None,
    translation_model: str | None,
) -> str | None:
    """Resolve the effective model slug for a given orchestrator phase.

    Global model applies to metadata, profile repair, and translation.
    Translation override changes chapter translation only.
    """
    if phase in ("translate", "chapter_translation"):
        return translation_model if translation_model is not None else global_model
    return global_model
