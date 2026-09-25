from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import threading
from typing import Any

from dich_truyen_agent.orchestrator.models import RunSummary
from dich_truyen_agent.orchestrator.process import scrub_sensitive_text
from dich_truyen_agent.storage import atomic_write_text


class ActivityTracer:
    """Manages the run directory, bounded log allocation, and atomic run_summary.json updates."""

    def __init__(self, run_dir: Path | str, summary: RunSummary) -> None:
        self.run_dir = Path(run_dir).resolve()
        self.summary = summary
        self.logs_dir = self.run_dir / "logs"
        self.summary_file = self.run_dir / "run_summary.json"
        self._lock = threading.Lock()

        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.write_summary()

    def get_invocation_log_paths(self, prefix: str) -> tuple[Path, Path]:
        """Allocate distinct stdout and stderr log paths for a harness invocation."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        stdout_path = self.logs_dir / f"{prefix}_{timestamp}_stdout.log"
        stderr_path = self.logs_dir / f"{prefix}_{timestamp}_stderr.log"
        return stdout_path, stderr_path

    def record_invocation(self, invocation_data: dict[str, Any]) -> None:
        """Record a single harness or deterministic subprocess invocation."""
        with self._lock:
            # Clean sensitive data from record
            sanitized = {}
            for k, v in invocation_data.items():
                if isinstance(v, str):
                    sanitized[k] = scrub_sensitive_text(v)
                else:
                    sanitized[k] = v
            self.summary.invocations.append(sanitized)
            self._write_summary_locked()

    def update_status(
        self,
        status: str,
        *,
        current_phase: str | None = None,
        completed_chapters: int | None = None,
        total_chapters: int | None = None,
        pending_approval: str | None = None,
        approval_report_path: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        effective_model: str | None = None,
    ) -> None:
        """Update summary status and metadata, atomically persisting the changes."""
        with self._lock:
            self.summary.status = status
            if current_phase is not None:
                self.summary.current_phase = current_phase
            if completed_chapters is not None:
                self.summary.completed_chapters = completed_chapters
            if total_chapters is not None:
                self.summary.total_chapters = total_chapters
            if pending_approval is not None:
                self.summary.pending_approval = pending_approval
            if approval_report_path is not None:
                self.summary.approval_report_path = approval_report_path
            if error_code is not None:
                self.summary.error_code = error_code
            if error_message is not None:
                self.summary.error_message = scrub_sensitive_text(error_message)
            if effective_model is not None:
                self.summary.effective_model = effective_model

            if status in {"completed", "error", "superseded"}:
                self.summary.finished_at = datetime.now(UTC)

            self._write_summary_locked()

    def add_report_path(self, path: str) -> None:
        with self._lock:
            if path not in self.summary.report_paths:
                self.summary.report_paths.append(path)
                self._write_summary_locked()

    def write_summary(self) -> Path:
        with self._lock:
            self._write_summary_locked()
            return self.summary_file

    def _write_summary_locked(self) -> None:
        raw_json = self.summary.model_dump_json(indent=2)
        atomic_write_text(self.summary_file, raw_json)
