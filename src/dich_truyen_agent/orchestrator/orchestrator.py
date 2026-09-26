from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver

from dich_truyen_agent.orchestrator.attempts import AttemptJournal
from dich_truyen_agent.orchestrator.graph import GraphRunner
from dich_truyen_agent.orchestrator.models import OrchestratorConfig, RunOutcome
from dich_truyen_agent.orchestrator.runners.agy import AgyRunner
from dich_truyen_agent.orchestrator.runners.base import HarnessRunner
from dich_truyen_agent.orchestrator.workspace_ops import WorkspaceOps
from dich_truyen_agent.paths import workspace_paths


def _lock_path(workspace_root: Path) -> Path:
    resolved = Path(workspace_root).resolve()
    paths = workspace_paths(resolved.parent, resolved.name)
    locks_dir = paths.root.parent / ".orchestrator-locks"
    return locks_dir / f"{paths.root.name}.lock"


def _legacy_lock_path(workspace_root: Path) -> Path:
    return Path(workspace_root).resolve() / "reports" / "runs" / ".orchestrator.lock"


class WorkspaceLock:
    """Inter-process workspace lock to prevent concurrent orchestrator runs."""

    def __init__(self, lock_path: Path) -> None:
        self.lock_path = lock_path
        self._file: Any = None

    def acquire(self) -> bool:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._file = open(self.lock_path, "a+", encoding="utf-8")
            if sys.platform == "win32":
                import msvcrt

                self._file.seek(0)
                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._file.seek(0)
            self._file.truncate()
            self._file.write(f"pid={os.getpid()}\n")
            self._file.flush()
            return True
        except (BlockingIOError, OSError, PermissionError):
            if self._file:
                try:
                    self._file.close()
                except Exception:
                    pass
                self._file = None
            return False

    def release(self) -> None:
        if self._file is not None:
            try:
                if sys.platform == "win32":
                    import msvcrt

                    self._file.seek(0)
                    msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None

    def __enter__(self) -> bool:
        return self.acquire()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()


class BookOrchestrator:
    """Durable lifecycle manager for novel translation workflow."""

    def __init__(
        self,
        runner: HarnessRunner | None = None,
        ops: WorkspaceOps | None = None,
    ) -> None:
        self.runner = runner or AgyRunner()
        self.ops = ops or WorkspaceOps()

    def _manifest_path(self, workspace_root: Path) -> Path:
        return workspace_root / "reports" / "runs" / "manifest.json"

    def _lock_path(self, workspace_root: Path) -> Path:
        return _lock_path(workspace_root)

    def _legacy_lock_path(self, workspace_root: Path) -> Path:
        return _legacy_lock_path(workspace_root)

    def _acquire_locks(
        self, workspace_root: Path
    ) -> tuple[WorkspaceLock | None, WorkspaceLock | None]:
        try:
            ext_path = self._lock_path(workspace_root)
        except Exception:
            return None, None
        ext_lock = WorkspaceLock(ext_path)
        if not ext_lock.acquire():
            return None, None
        legacy_path = self._legacy_lock_path(workspace_root)
        legacy_lock = None
        if legacy_path.is_file():
            legacy_lock = WorkspaceLock(legacy_path)
            if not legacy_lock.acquire():
                ext_lock.release()
                return None, None
        return ext_lock, legacy_lock

    def _release_locks(
        self,
        ext_lock: WorkspaceLock | None,
        legacy_lock: WorkspaceLock | None,
    ) -> None:
        if legacy_lock is not None:
            try:
                legacy_lock.release()
            except Exception:
                pass
        if ext_lock is not None:
            try:
                ext_lock.release()
            except Exception:
                pass

    def _load_manifest(self, workspace_root: Path) -> dict[str, Any] | None:
        manifest_file = self._manifest_path(workspace_root)
        if not manifest_file.is_file():
            return None
        try:
            return json.loads(manifest_file.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _save_manifest(self, workspace_root: Path, data: dict[str, Any]) -> None:
        manifest_file = self._manifest_path(workspace_root)
        manifest_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = manifest_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(manifest_file)

    def start(
        self,
        config_or_workspace: OrchestratorConfig | Path | str,
        **kwargs: Any,
    ) -> RunOutcome:
        if isinstance(config_or_workspace, OrchestratorConfig):
            config = config_or_workspace
        else:
            try:
                config = OrchestratorConfig(
                    workspace_root=Path(config_or_workspace), **kwargs
                )
            except Exception as e:
                start_at = str(kwargs.get("start_at", "auto"))
                stop_after = str(kwargs.get("stop_after", "export"))
                return RunOutcome(
                    status="blocked",
                    run_id="invalid",
                    selected_span=(start_at, stop_after),
                    current_phase="inspect",
                    error_message=str(e),
                    exit_code=3,
                )

        workspace_root = config.workspace_root
        try:
            self._lock_path(workspace_root)
        except Exception as e:
            return RunOutcome(
                status="blocked",
                run_id=config.run_id,
                selected_span=(config.start_at, config.stop_after),
                current_phase="inspect",
                error_message=f"Invalid workspace path or slug: {e}",
                exit_code=3,
            )

        ext_lock, legacy_lock = self._acquire_locks(workspace_root)
        if ext_lock is None:
            return RunOutcome(
                status="blocked",
                run_id=config.run_id,
                selected_span=(config.start_at, config.stop_after),
                current_phase="lock",
                error_code="workspace_locked",
                error_message="Workspace is locked by another process",
                exit_code=3,
            )

        try:
            if not (workspace_root / "book.yaml").is_file():
                return RunOutcome(
                    status="blocked",
                    run_id=config.run_id,
                    selected_span=(config.start_at, config.stop_after),
                    current_phase="inspect",
                    error_message=f"workspace metadata book.yaml is missing: {workspace_root / 'book.yaml'}",
                    exit_code=3,
                )

            # Check manifest for previous paused run
            manifest = self._load_manifest(workspace_root)
            if manifest and manifest.get("status") == "paused":
                old_run_id = manifest.get("current_run_id")
                if config.start_at == "auto":
                    # Plain new invocation reports pending resume
                    return RunOutcome(
                        status="paused",
                        run_id=old_run_id or config.run_id,
                        selected_span=(
                            manifest.get("start_at", "auto"),
                            manifest.get("stop_after", "export"),
                        ),
                        current_phase="paused",
                        error_message=f"Run {old_run_id} is paused. Resume it with --resume or start a new run with an explicit --start-at.",
                        next_command=f"orchestrate --workspace {workspace_root} --resume",
                        exit_code=2,
                    )
                else:
                    # Explicit new --start-at marks old run superseded
                    if old_run_id:
                        old_summary_file = (
                            workspace_root
                            / "reports"
                            / "runs"
                            / old_run_id
                            / "run_summary.json"
                        )
                        if old_summary_file.is_file():
                            try:
                                old_summary = json.loads(
                                    old_summary_file.read_text(encoding="utf-8")
                                )
                                old_summary["status"] = "superseded"
                                old_summary["finished_at"] = datetime.now(
                                    UTC
                                ).isoformat()
                                old_summary_file.write_text(
                                    json.dumps(old_summary, indent=2), encoding="utf-8"
                                )
                            except Exception:
                                pass

            # Model validation preflight
            if config.start_at not in ("qa", "export") and hasattr(
                self.runner, "get_available_models"
            ):
                models_to_check = []
                if config.global_model:
                    models_to_check.append(config.global_model)
                if config.translation_model:
                    models_to_check.append(config.translation_model)
                if models_to_check:
                    try:
                        avail = self.runner.get_available_models()
                        if avail:
                            for m in models_to_check:
                                if m not in avail:
                                    return RunOutcome(
                                        status="blocked",
                                        run_id=config.run_id,
                                        selected_span=(
                                            config.start_at,
                                            config.stop_after,
                                        ),
                                        current_phase="model_preflight",
                                        error_code="invalid_model",
                                        error_message=f"Requested model '{m}' is not available in agy models ({avail})",
                                        exit_code=3,
                                    )
                    except Exception:
                        pass

            run_dir = workspace_root / "reports" / "runs" / config.run_id
            run_dir.mkdir(parents=True, exist_ok=True)

            # Persist initial manifest
            self._save_manifest(
                workspace_root,
                {
                    "current_run_id": config.run_id,
                    "status": "running",
                    "start_at": config.start_at,
                    "stop_after": config.stop_after,
                    "selected_span": [config.start_at, config.stop_after],
                    "updated_at": datetime.now(UTC).isoformat(),
                },
            )

            # SQLite checkpointer
            db_path = run_dir / "checkpoint.sqlite"
            conn = sqlite3.connect(str(db_path), check_same_thread=False)
            saver = SqliteSaver(conn)

            journal = AttemptJournal(run_dir / "attempts.json")
            graph_runner = GraphRunner(
                ops=self.ops,
                runner=self.runner,
                config=config,
                checkpointer=saver,
                journal=journal,
            )

            try:
                outcome = graph_runner.run()
            finally:
                conn.close()

            # Update manifest with final status
            self._save_manifest(
                workspace_root,
                {
                    "current_run_id": config.run_id,
                    "status": outcome.status,
                    "start_at": config.start_at,
                    "stop_after": config.stop_after,
                    "selected_span": [config.start_at, config.stop_after],
                    "updated_at": datetime.now(UTC).isoformat(),
                },
            )
            return outcome
        finally:
            self._release_locks(ext_lock, legacy_lock)

    def resume(
        self,
        workspace: Path | str,
        decision: str | bool | None = None,
        **kwargs: Any,
    ) -> RunOutcome:
        workspace_root = Path(workspace)
        try:
            self._lock_path(workspace_root)
        except Exception as e:
            return RunOutcome(
                status="blocked",
                run_id="unknown",
                selected_span=("auto", "export"),
                current_phase="resume",
                error_message=f"Invalid workspace path or slug: {e}",
                exit_code=3,
            )

        ext_lock, legacy_lock = self._acquire_locks(workspace_root)
        if ext_lock is None:
            return RunOutcome(
                status="blocked",
                run_id="unknown",
                selected_span=("auto", "export"),
                current_phase="lock",
                error_code="workspace_locked",
                error_message="Workspace is locked by another process",
                exit_code=3,
            )

        try:
            manifest = self._load_manifest(workspace_root)
            if not manifest or not manifest.get("current_run_id"):
                return RunOutcome(
                    status="error",
                    run_id="unknown",
                    selected_span=("auto", "export"),
                    current_phase="resume",
                    error_code="no_saved_run",
                    error_message="No run found to resume. Please start a new run.",
                    exit_code=1,
                )

            run_id = manifest["current_run_id"]
            run_dir = workspace_root / "reports" / "runs" / run_id
            summary_file = run_dir / "run_summary.json"
            if not summary_file.is_file():
                return RunOutcome(
                    status="error",
                    run_id=run_id,
                    selected_span=("auto", "export"),
                    current_phase="resume",
                    error_code="missing_run_summary",
                    error_message=f"Run summary for {run_id} is missing.",
                    exit_code=1,
                )

            summary = json.loads(summary_file.read_text(encoding="utf-8"))
            if summary.get("status") == "superseded":
                return RunOutcome(
                    status="blocked",
                    run_id=run_id,
                    selected_span=tuple(
                        summary.get("selected_span", ["auto", "export"])
                    ),
                    current_phase="resume",
                    error_code="run_superseded",
                    error_message=f"Run {run_id} has been superseded and cannot be resumed.",
                    exit_code=3,
                )

            if summary.get("status") == "completed":
                return RunOutcome(
                    status="blocked",
                    run_id=run_id,
                    selected_span=tuple(
                        summary.get("selected_span", ["auto", "export"])
                    ),
                    current_phase="resume",
                    error_code="run_completed",
                    error_message=f"Run {run_id} is already completed.",
                    exit_code=3,
                )

            db_path = run_dir / "checkpoint.sqlite"
            if not db_path.is_file():
                return RunOutcome(
                    status="error",
                    run_id=run_id,
                    selected_span=tuple(
                        summary.get("selected_span", ["auto", "export"])
                    ),
                    current_phase="resume",
                    error_code="missing_checkpoint",
                    error_message=f"Checkpoint file for run {run_id} is missing.",
                    exit_code=1,
                )

            conn = sqlite3.connect(str(db_path), check_same_thread=False)
            saver = SqliteSaver(conn)

            # Reconstruct config pinned from saved summary
            config = OrchestratorConfig(
                run_id=run_id,
                workspace_root=workspace_root,
                start_at=summary.get("start_at", "auto"),
                stop_after=summary.get("stop_after", "export"),
                formats=summary.get("requested_formats", ["epub", "txt"]),
                global_model=summary.get("global_model"),
                translation_model=summary.get("translation_model"),
                allow_harness_permission_bypass=summary.get(
                    "allow_harness_permission_bypass", False
                ),
            )

            journal = AttemptJournal(run_dir / "attempts.json")
            graph_runner = GraphRunner(
                ops=self.ops,
                runner=self.runner,
                config=config,
                checkpointer=saver,
                journal=journal,
            )

            thread_config = {"configurable": {"thread_id": run_id}}
            state_snapshot = graph_runner.graph.get_state(thread_config)
            is_paused = bool(
                state_snapshot.tasks and any(t.interrupts for t in state_snapshot.tasks)
            )

            if is_paused:
                if decision is None:
                    # Missing decision is reported as still paused without graph advancement
                    conn.close()
                    interrupt_val = state_snapshot.tasks[0].interrupts[0].value
                    pending_app = (
                        interrupt_val.get("type")
                        if isinstance(interrupt_val, dict)
                        else "approval"
                    )
                    rep_path = (
                        interrupt_val.get("report_path")
                        if isinstance(interrupt_val, dict)
                        else None
                    )
                    rep_hash = (
                        interrupt_val.get("report_hash")
                        if isinstance(interrupt_val, dict)
                        else None
                    )
                    return RunOutcome(
                        status="paused",
                        run_id=run_id,
                        selected_span=(config.start_at, config.stop_after),
                        current_phase=state_snapshot.values.get(
                            "phase", "crawl_decision"
                        ),
                        pending_approval=pending_app,
                        approval_report_path=rep_path,
                        approval_report_hash=rep_hash,
                        exit_code=2,
                        next_command=f"orchestrate --workspace {workspace_root} --resume --decision approve",
                        error_message="Run is paused awaiting approval decision. Supply --decision approve or --decision reject.",
                    )
                bool_decision = (
                    True if decision in (True, "approve", "approved") else False
                )
                try:
                    outcome = graph_runner.run(resume_decision=bool_decision)
                finally:
                    conn.close()
            else:
                if decision is not None:
                    conn.close()
                    return RunOutcome(
                        status="blocked",
                        run_id=run_id,
                        selected_span=(config.start_at, config.stop_after),
                        current_phase="resume",
                        error_code="no_pending_approval",
                        error_message="Cannot supply --decision when there is no pending approval.",
                        exit_code=3,
                    )
                try:
                    outcome = graph_runner.run()
                finally:
                    conn.close()

            self._save_manifest(
                workspace_root,
                {
                    "current_run_id": config.run_id,
                    "status": outcome.status,
                    "start_at": config.start_at,
                    "stop_after": config.stop_after,
                    "selected_span": [config.start_at, config.stop_after],
                    "updated_at": datetime.now(UTC).isoformat(),
                },
            )
            return outcome
        finally:
            self._release_locks(ext_lock, legacy_lock)

    def prune_terminal_runs(
        self, workspace_root: Path, max_age_days: int = 30
    ) -> list[str]:
        ext_lock, legacy_lock = self._acquire_locks(workspace_root)
        if ext_lock is None:
            return []

        pruned = []
        try:
            runs_dir = workspace_root / "reports" / "runs"
            if not runs_dir.is_dir():
                return []

            now = datetime.now(UTC)
            for item in runs_dir.iterdir():
                if not item.is_dir() or item.name.startswith("."):
                    continue
                summary_file = item / "run_summary.json"
                if not summary_file.is_file():
                    continue

                try:
                    summary = json.loads(summary_file.read_text(encoding="utf-8"))
                except Exception:
                    continue

                status = summary.get("status")
                # Never prune active or paused runs
                if status in ("running", "paused"):
                    continue

                # For terminal runs, check age
                ts_str = summary.get("finished_at") or summary.get("started_at")
                if not ts_str:
                    continue

                try:
                    ts = datetime.fromisoformat(ts_str)
                    age_days = (now - ts).total_seconds() / 86400
                except Exception:
                    age_days = 0

                if age_days >= max_age_days:
                    # Prune SQLite database, preserve run_summary.json
                    for db_name in (
                        "checkpoint.sqlite",
                        "checkpoint.sqlite-wal",
                        "checkpoint.sqlite-shm",
                    ):
                        p = item / db_name
                        if p.is_file():
                            p.unlink(missing_ok=True)
                    pruned.append(item.name)
        finally:
            self._release_locks(ext_lock, legacy_lock)

        return pruned
