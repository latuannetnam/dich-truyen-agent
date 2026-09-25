from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dich_truyen_agent.checkpoints import check_orchestrator_gate
from dich_truyen_agent.models import (
    BookMetadata,
    ChapterCatalog,
    CheckpointType,
    OperationResult,
    OperationStatus,
)
from dich_truyen_agent.orchestrator.models import PHASES, VALID_START_AT, VALID_STOP_AFTER
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.storage import load_yaml_model
from dich_truyen_agent.workspace import inspect_workspace, next_translation_work_item


@dataclass
class EntryDecision:
    """Decision produced by reconciling workspace evidence and requested phase span."""

    status: str  # "enter", "completed", "blocked"
    phase: str | None
    reason: str
    missing_gate: str | None = None
    remedy_command: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


class WorkspaceOps:
    """Domain-level operations and gate reconciliation for the orchestrator."""

    def inspect_entry(
        self,
        workspace_root: Path | str,
        start_at: str,
        stop_after: str,
        formats: list[str] | None = None,
    ) -> EntryDecision:
        """Resolve workspace evidence against requested phase span without starting child processes."""
        workspace_path = Path(workspace_root).resolve()
        paths = workspace_paths(workspace_path.parent, workspace_path.name)

        # 1. Validate inputs
        if start_at not in VALID_START_AT:
            return EntryDecision(
                status="blocked",
                phase=None,
                reason=f"invalid start_at: {start_at!r}; valid choices: {VALID_START_AT}",
            )
        if stop_after not in VALID_STOP_AFTER:
            return EntryDecision(
                status="blocked",
                phase=None,
                reason=f"invalid stop_after: {stop_after!r}; valid choices: {VALID_STOP_AFTER}",
            )
        if start_at != "auto":
            if PHASES.index(start_at) > PHASES.index(stop_after):
                return EntryDecision(
                    status="blocked",
                    phase=None,
                    reason=f"invalid phase span: stop_after ({stop_after!r}) cannot precede start_at ({start_at!r})",
                )

        # 2. Basic workspace existence
        if not paths.book.is_file():
            return EntryDecision(
                status="blocked",
                phase=None,
                reason=f"workspace metadata book.yaml is missing: {paths.book}",
            )

        # 3. Check phase states from domain evidence
        crawl_gate = check_orchestrator_gate(workspace_path, CheckpointType.CRAWL_APPROVED)
        is_crawl_complete = crawl_gate.status is OperationStatus.OK

        is_translation_complete = False
        translation_reason = ""
        if is_crawl_complete:
            if paths.chapters.is_file() and paths.state.is_file():
                try:
                    catalog = load_yaml_model(paths.chapters, ChapterCatalog)
                    if len(catalog.chapters) > 0:
                        work_item_res = next_translation_work_item(workspace_path)
                        if (
                            work_item_res.status is OperationStatus.OK
                            and work_item_res.data.get("state") == "completed"
                        ):
                            ws_res = inspect_workspace(workspace_path)
                            if ws_res.status is OperationStatus.OK:
                                is_translation_complete = True
                            else:
                                translation_reason = ws_res.reason
                        elif work_item_res.status is OperationStatus.BLOCKED:
                            translation_reason = work_item_res.reason
                        else:
                            translation_reason = f"pending chapters: {work_item_res.progress}"
                    else:
                        translation_reason = "catalog has zero chapters"
                except Exception as e:
                    translation_reason = f"failed to load catalog/state: {e}"
            else:
                translation_reason = "catalog or state missing"
        else:
            translation_reason = f"crawl gate is not approved ({crawl_gate.reason})"

        is_qa_complete = False
        qa_reason = ""
        if is_translation_complete:
            qa_gate = check_orchestrator_gate(workspace_path, CheckpointType.QA_APPROVED)
            if qa_gate.status is OperationStatus.OK:
                is_qa_complete = True
            else:
                qa_reason = qa_gate.reason
        else:
            qa_reason = translation_reason or "translation is incomplete"

        requested_formats = formats or ["epub", "txt"]
        is_export_complete = False
        if is_qa_complete:
            try:
                metadata = load_yaml_model(paths.book, BookMetadata)
                slug = metadata.book_slug
                missing_formats = []
                for fmt in requested_formats:
                    export_file = paths.exports / f"{slug}.{fmt}"
                    if not export_file.is_file() or export_file.stat().st_size == 0:
                        missing_formats.append(fmt)
                if not missing_formats:
                    is_export_complete = True
            except Exception:
                pass

        # 4. Route decision: Auto vs Explicit
        if start_at == "auto":
            stop_idx = PHASES.index(stop_after)
            candidate_phases = PHASES[: stop_idx + 1]

            for ph in candidate_phases:
                if ph == "crawl":
                    if not is_crawl_complete:
                        return EntryDecision(status="enter", phase="crawl", reason="earliest incomplete phase is crawl")
                elif ph == "translate":
                    if not is_translation_complete:
                        if not is_crawl_complete:
                            return EntryDecision(status="enter", phase="crawl", reason="crawl required before translation")
                        return EntryDecision(status="enter", phase="translate", reason="earliest incomplete phase is translate")
                elif ph == "qa":
                    if not is_qa_complete:
                        if not is_translation_complete:
                            return EntryDecision(status="enter", phase="translate", reason="translation required before qa")
                        return EntryDecision(status="enter", phase="qa", reason="earliest incomplete phase is qa")
                elif ph == "export":
                    if not is_export_complete:
                        if not is_qa_complete:
                            return EntryDecision(status="enter", phase="qa", reason="qa required before export")
                        return EntryDecision(status="enter", phase="export", reason="earliest incomplete phase is export")

            return EntryDecision(
                status="completed",
                phase=stop_after,
                reason=f"all phases up to {stop_after} are already completed",
            )

        # Explicit start_at
        if start_at == "crawl":
            if is_crawl_complete:
                if stop_after == "crawl":
                    return EntryDecision(status="completed", phase="crawl", reason="crawl is already approved")
                # Advance along selected span to first incomplete phase
                stop_idx = PHASES.index(stop_after)
                for ph in PHASES[1 : stop_idx + 1]:
                    if ph == "translate" and not is_translation_complete:
                        return EntryDecision(status="enter", phase="translate", reason="entering translate phase")
                    if ph == "qa" and not is_qa_complete:
                        return EntryDecision(status="enter", phase="qa", reason="entering qa phase")
                    if ph == "export" and not is_export_complete:
                        return EntryDecision(status="enter", phase="export", reason="entering export phase")
                return EntryDecision(status="completed", phase=stop_after, reason=f"all phases up to {stop_after} are already completed")
            return EntryDecision(status="enter", phase="crawl", reason="entering crawl phase")

        if start_at == "translate":
            if not is_crawl_complete:
                return EntryDecision(
                    status="blocked",
                    phase="translate",
                    missing_gate="crawl-approved",
                    remedy_command="orchestrate --start-at crawl --stop-after crawl",
                    reason=f"cannot start at translate: crawl gate is not approved ({crawl_gate.reason})",
                )
            if not paths.chapters.is_file() or len(load_yaml_model(paths.chapters, ChapterCatalog).chapters) == 0:
                return EntryDecision(
                    status="blocked",
                    phase="translate",
                    missing_gate="crawl-approved",
                    remedy_command="orchestrate --start-at crawl --stop-after crawl",
                    reason="cannot start at translate: catalog has zero chapters",
                )

            if is_translation_complete:
                if stop_after == "translate":
                    return EntryDecision(status="completed", phase="translate", reason="translation is already completed")
                stop_idx = PHASES.index(stop_after)
                for ph in PHASES[2 : stop_idx + 1]:
                    if ph == "qa" and not is_qa_complete:
                        return EntryDecision(status="enter", phase="qa", reason="entering qa phase")
                    if ph == "export" and not is_export_complete:
                        return EntryDecision(status="enter", phase="export", reason="entering export phase")
                return EntryDecision(status="completed", phase=stop_after, reason=f"all phases up to {stop_after} are already completed")
            return EntryDecision(status="enter", phase="translate", reason="entering translate phase")

        if start_at == "qa":
            if not is_crawl_complete:
                return EntryDecision(
                    status="blocked",
                    phase="qa",
                    missing_gate="crawl-approved",
                    remedy_command="orchestrate --start-at crawl",
                    reason=f"cannot start at qa: crawl gate is not approved ({crawl_gate.reason})",
                )
            if not is_translation_complete:
                return EntryDecision(
                    status="blocked",
                    phase="qa",
                    missing_gate="translation-completed",
                    remedy_command="orchestrate --start-at translate",
                    reason=f"cannot start at qa: translation is incomplete ({translation_reason})",
                )

            if is_qa_complete:
                if stop_after == "qa":
                    return EntryDecision(status="completed", phase="qa", reason="qa is already approved")
                return EntryDecision(status="enter", phase="export", reason="entering export phase")
            return EntryDecision(status="enter", phase="qa", reason="entering qa phase")

        if start_at == "export":
            if not is_crawl_complete:
                return EntryDecision(
                    status="blocked",
                    phase="export",
                    missing_gate="crawl-approved",
                    remedy_command="orchestrate --start-at crawl",
                    reason=f"cannot start at export: crawl gate is not approved ({crawl_gate.reason})",
                )
            if not is_translation_complete:
                return EntryDecision(
                    status="blocked",
                    phase="export",
                    missing_gate="translation-completed",
                    remedy_command="orchestrate --start-at translate",
                    reason=f"cannot start at export: translation is incomplete ({translation_reason})",
                )
            if not is_qa_complete:
                return EntryDecision(
                    status="blocked",
                    phase="export",
                    missing_gate="qa-approved",
                    remedy_command="orchestrate --start-at qa",
                    reason=f"cannot start at export: qa gate is not approved ({qa_reason})",
                )
            # Explicit export always enters export to regenerate or produce outputs
            return EntryDecision(status="enter", phase="export", reason="entering export phase")

        return EntryDecision(status="blocked", phase=None, reason=f"unhandled phase: {start_at}")

    def run_crawl(
        self,
        workspace_root: Path,
        *,
        max_chapters: int = 0,
        delay_seconds: float = 3.0,
        timeout_seconds: int = 1800,
    ) -> OperationResult:
        """Run deterministic crawl-book via supervised subprocess."""
        import sys
        from dich_truyen_agent.orchestrator.process import run_process

        workspace_root = Path(workspace_root).resolve()
        paths = workspace_paths(workspace_root.parent, workspace_root.name)
        if not paths.book.is_file():
            return OperationResult(
                status=OperationStatus.ERROR,
                reason="book.yaml missing",
            )
        metadata = load_yaml_model(paths.book, BookMetadata)
        log_dir = paths.reports / "runs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stdout_file = log_dir / "crawl_stdout.log"
        stderr_file = log_dir / "crawl_stderr.log"

        argv = [
            sys.executable,
            "-m",
            "dich_truyen_agent.cli",
            "crawl-book",
            "--books-root",
            str(paths.root.parent),
            "--slug",
            paths.root.name,
            "--source-url",
            metadata.source_url,
            "--max-chapters",
            str(max_chapters),
            "--chapter-delay-seconds",
            str(delay_seconds),
            "--json",
        ]
        proc_res = run_process(
            argv,
            cwd=workspace_root,
            timeout_seconds=timeout_seconds,
            stdout_path=stdout_file,
            stderr_path=stderr_file,
        )
        if proc_res.timed_out:
            return OperationResult(
                status=OperationStatus.ERROR,
                reason=f"crawl timed out after {timeout_seconds}s",
            )
        if stdout_file.is_file():
            try:
                content = stdout_file.read_text(encoding="utf-8").strip()
                if content:
                    start = content.find("{")
                    end = content.rfind("}")
                    if start != -1 and end != -1:
                        return OperationResult.model_validate_json(content[start : end + 1])
            except Exception:
                pass
        return OperationResult(
            status=OperationStatus.ERROR,
            reason=proc_res.failure_detail or f"crawl process exited with code {proc_res.exit_code}",
        )
