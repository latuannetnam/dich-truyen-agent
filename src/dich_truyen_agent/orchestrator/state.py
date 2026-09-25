from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from dich_truyen_agent.orchestrator.models import OrchestratorConfig


class BookOrchestratorState(TypedDict):
    """LangGraph orchestrator state schema adhering to Spec Section 5.

    No raw chapter text, translations, or unbounded logs are checkpointed here.
    """

    run_id: str
    workspace_root: str
    start_at: str  # auto, crawl, translate, qa, export
    stop_after: str  # crawl, translate, qa, export
    phase: str
    batch_index: int
    current_chapter_id: int | None
    chapter_attempt: int  # display snapshot only; authoritative attempts live in AttemptJournal
    profile_repair_attempts: int
    pending_approval: str | None  # crawl or qa
    approval_report_hash: str | None
    approval_evidence_hashes: dict[str, str] | None
    status: str  # running, paused, blocked, completed, error, superseded
    error_code: str | None
    error_message: str | None
    run_dir: str


def create_initial_state(config: OrchestratorConfig, run_dir: Path) -> BookOrchestratorState:
    """Instantiate initial graph state from configuration."""
    return BookOrchestratorState(
        run_id=config.run_id,
        workspace_root=str(config.workspace_root.resolve()),
        start_at=config.start_at,
        stop_after=config.stop_after,
        phase="inspect",
        batch_index=0,
        current_chapter_id=None,
        chapter_attempt=0,
        profile_repair_attempts=0,
        pending_approval=None,
        approval_report_hash=None,
        approval_evidence_hashes=None,
        status="running",
        error_code=None,
        error_message=None,
        run_dir=str(run_dir.resolve()),
    )
