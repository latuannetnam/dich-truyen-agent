from __future__ import annotations

from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from dich_truyen_agent.checkpoints import (
    approve_current_qa,
    approve_full_crawl,
    check_orchestrator_gate,
)
from dich_truyen_agent.crawl_probe import probe_crawl_profile
from dich_truyen_agent.crawl_profiles import install_local_profile
from dich_truyen_agent.crawl_reports import build_crawl_report
from dich_truyen_agent.export import export_book
from dich_truyen_agent.models import (
    ApprovalScope,
    BookMetadata,
    BookState,
    ChapterCatalog,
    CheckpointType,
    CrawlReport,
    CrawlSettings,
    OperationStatus,
    QAReport,
    StageStatus,
)
from dich_truyen_agent.qa import run_qa_check
from dich_truyen_agent.orchestrator.attempts import AttemptJournal
from dich_truyen_agent.orchestrator.models import (
    OrchestratorConfig,
    RunOutcome,
    RunSummary,
)
from dich_truyen_agent.orchestrator.runners import resolve_model_for_phase
from dich_truyen_agent.orchestrator.runners.base import HarnessRunner
from dich_truyen_agent.orchestrator.state import BookOrchestratorState
from dich_truyen_agent.orchestrator.tracer import ActivityTracer
from dich_truyen_agent.orchestrator.workspace_ops import WorkspaceOps
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.storage import atomic_write_yaml, load_yaml_model, sha256_file
from dich_truyen_agent.workspace import (
    get_staging_paths,
    next_translation_work_item,
    promote_chapter_translation,
    recover_chapter_promotion,
    verify_staged_chapter,
)


def _compute_crawl_evidence_hashes(
    workspace_root: Path,
    *,
    require_scope: bool = True,
) -> dict[str, str]:
    paths = workspace_paths(workspace_root.parent, workspace_root.name)
    hashes: dict[str, str] = {}
    if paths.chapters.is_file():
        hashes["chapters.yaml"] = sha256_file(paths.chapters)
        catalog = load_yaml_model(paths.chapters, ChapterCatalog)
        for ch in catalog.chapters:
            raw_file = paths.raw / ch.raw_filename
            if raw_file.is_file():
                hashes[f"raw/{ch.raw_filename}"] = sha256_file(raw_file)
    crawl_rep = paths.reports / "crawl.yaml"
    if crawl_rep.is_file():
        hashes["reports/crawl.yaml"] = sha256_file(crawl_rep)
    if paths.book.is_file():
        meta = load_yaml_model(paths.book, BookMetadata)
        if meta.scope_managed:
            if paths.source_scope.is_file():
                hashes["reports/source-scope.yaml"] = sha256_file(paths.source_scope)
            elif require_scope:
                raise ValueError(
                    "scope_managed workspace missing reports/source-scope.yaml"
                )
    return hashes


def _compute_qa_evidence_hashes(
    workspace_root: Path,
    *,
    require_scope: bool = True,
) -> dict[str, str]:
    paths = workspace_paths(workspace_root.parent, workspace_root.name)
    hashes: dict[str, str] = {}
    if paths.chapters.is_file():
        hashes["chapters.yaml"] = sha256_file(paths.chapters)
        catalog = load_yaml_model(paths.chapters, ChapterCatalog)
        for ch in catalog.chapters:
            trans_file = paths.translations / ch.translation_filename
            if trans_file.is_file():
                hashes[f"translations/{ch.translation_filename}"] = sha256_file(
                    trans_file
                )
    if paths.state.is_file():
        hashes["state.yaml"] = sha256_file(paths.state)
    qa_rep = paths.reports / "qa-report.yaml"
    if qa_rep.is_file():
        hashes["reports/qa-report.yaml"] = sha256_file(qa_rep)
    if paths.book.is_file():
        meta = load_yaml_model(paths.book, BookMetadata)
        if meta.scope_managed:
            if paths.source_scope.is_file():
                hashes["reports/source-scope.yaml"] = sha256_file(paths.source_scope)
            elif require_scope:
                raise ValueError(
                    "scope_managed workspace missing reports/source-scope.yaml"
                )
    return hashes


def build_orchestrator_graph(
    ops: WorkspaceOps,
    runner: HarnessRunner,
    tracer: ActivityTracer | None = None,
    checkpointer: Any = None,
    journal: AttemptJournal | None = None,
    config: OrchestratorConfig | None = None,
) -> Any:
    """Construct and compile the LangGraph novel orchestration graph."""

    # 1. Inspect Node
    def inspect_node(state: BookOrchestratorState) -> dict[str, Any]:
        workspace_root = Path(state["workspace_root"])
        decision = ops.inspect_entry(
            workspace_root,
            state["start_at"],
            state["stop_after"],
            formats=config.formats if config else None,
        )

        if decision.status == "completed":
            return {
                "status": "completed",
                "phase": decision.phase or state["stop_after"],
            }
        if decision.status == "blocked":
            return {
                "status": "blocked",
                "error_message": decision.reason,
                "error_code": decision.missing_gate,
            }

        # Status == "enter"
        target_phase = decision.phase or "crawl"
        return {"phase": target_phase, "status": "running"}

    # 2. Crawl Node
    def crawl_node(state: BookOrchestratorState) -> dict[str, Any]:
        workspace_root = Path(state["workspace_root"])
        paths = workspace_paths(workspace_root.parent, workspace_root.name)

        # Check if catalog already has discovered chapters and all raw files completed
        if paths.chapters.is_file() and paths.state.is_file():
            try:
                catalog = load_yaml_model(paths.chapters, ChapterCatalog)
                bstate = load_yaml_model(paths.state, BookState)
                if catalog.chapters:
                    completed_raw = sum(
                        1
                        for ch in bstate.chapters
                        if ch.raw.status is StageStatus.COMPLETED
                        and (
                            paths.raw / catalog.chapters[ch.chapter_id - 1].raw_filename
                        ).is_file()
                    )
                    if completed_raw == len(catalog.chapters):
                        # All raw files are ready; skip downloading and go straight to report
                        return {"phase": "crawl_report"}
            except Exception:
                pass

        # Execute crawl subprocess via ops
        timeout = config.crawl_timeout_seconds if config else 1800
        delay = 3.0
        scope_limit = getattr(config, "scope_limit", None) if config else None
        crawl_res = ops.run_crawl(
            workspace_root,
            max_chapters=0,
            scope_limit=scope_limit,
            delay_seconds=delay,
            timeout_seconds=timeout,
        )

        if crawl_res.status is OperationStatus.OK:
            return {"phase": "crawl_report"}

        # Failure: check if repairable
        reason_lower = crawl_res.reason.lower()
        if (
            "profile" in reason_lower
            or "selector" in reason_lower
            or "zero chapters" in reason_lower
            or "catalog" in reason_lower
        ):
            return {"phase": "profile_repair", "error_message": crawl_res.reason}

        return {"status": "blocked", "error_message": crawl_res.reason}

    # 3. Profile Repair Node
    def profile_repair_node(state: BookOrchestratorState) -> dict[str, Any]:
        workspace_root = Path(state["workspace_root"])
        run_id = state["run_id"]
        run_dir = Path(state["run_dir"])

        # Check / reserve attempt in journal
        if journal is None:
            active_journal = AttemptJournal(run_dir / "attempts.json")
        else:
            active_journal = journal

        try:
            attempt = active_journal.reserve(run_id, "profile_repair", limit=2)
        except RuntimeError as err:
            return {
                "status": "blocked",
                "error_message": f"profile repair budget exhausted: {err}",
            }

        # Snapshot protected workspace file hashes
        protected_hashes = _compute_crawl_evidence_hashes(
            workspace_root, require_scope=False
        )
        paths = workspace_paths(workspace_root.parent, workspace_root.name)
        if paths.book.is_file():
            protected_hashes["book.yaml"] = sha256_file(paths.book)
        if paths.style.is_file():
            protected_hashes["style.yaml"] = sha256_file(paths.style)
        if paths.state.is_file():
            protected_hashes["state.yaml"] = sha256_file(paths.state)
        if paths.chapters.is_file():
            protected_hashes["chapters.yaml"] = sha256_file(paths.chapters)
        if (paths.root / "crawl-profile.yaml").is_file():
            protected_hashes["crawl-profile.yaml"] = sha256_file(
                paths.root / "crawl-profile.yaml"
            )

        candidate_path = run_dir / f"profile_candidate_{attempt}.yaml"
        metadata = load_yaml_model(paths.book, BookMetadata)

        repair_prompt = (
            f"Repair crawl profile for book: {metadata.title}\n"
            f"Source URL: {metadata.source_url}\n"
            f"Error details: {state.get('error_message', 'Selector or index extraction failure')}\n"
            f"Write your proposed crawl profile ONLY to candidate path: {candidate_path}\n"
            "Do NOT modify book.yaml, chapters.yaml, or state.yaml.\n"
        )

        # Dispatch agent
        model = config.global_model if config else None
        runner.run_phase(
            phase="profile_repair",
            workspace=workspace_root,
            prompt=repair_prompt,
            model=model,
            timeout_seconds=600,
        )

        # Check for unauthorized mutation
        for rel_p, orig_h in protected_hashes.items():
            f_path = paths.root / rel_p
            if f_path.is_file() and sha256_file(f_path) != orig_h:
                return {
                    "status": "blocked",
                    "error_message": f"unauthorized workspace mutation detected in {rel_p} during profile repair",
                }

        if not candidate_path.is_file():
            return {
                "status": "blocked",
                "error_message": f"agent did not generate candidate profile at {candidate_path}",
            }

        # Probe candidate
        probe_res = probe_crawl_profile(workspace_root, candidate_path)
        if probe_res.status is not OperationStatus.OK:
            if active_journal.get_attempts(run_id, "profile_repair") < 2:
                return {
                    "phase": "profile_repair",
                    "profile_repair_attempts": attempt,
                    "error_message": f"candidate profile probe failed: {probe_res.reason}",
                }
            return {
                "status": "blocked",
                "error_message": f"candidate profile probe failed: {probe_res.reason}",
            }

        # Install local override
        install_res = install_local_profile(workspace_root, candidate_path)
        if install_res.status is not OperationStatus.OK:
            return {
                "status": "blocked",
                "error_message": f"failed to install candidate profile: {install_res.reason}",
            }

        # Retry crawl with new local profile
        return {"phase": "crawl", "profile_repair_attempts": attempt}

    # 4. Crawl Report Node
    def crawl_report_node(state: BookOrchestratorState) -> dict[str, Any]:
        workspace_root = Path(state["workspace_root"])
        paths = workspace_paths(workspace_root.parent, workspace_root.name)

        if not paths.chapters.is_file() or not paths.state.is_file():
            return {
                "status": "blocked",
                "error_message": "chapters.yaml or state.yaml missing after crawl",
            }

        catalog = load_yaml_model(paths.chapters, ChapterCatalog)
        if len(catalog.chapters) == 0:
            return {
                "status": "blocked",
                "error_message": "discovered catalog contains zero chapters",
            }

        crawl_rep_path = paths.reports / "crawl.yaml"
        if crawl_rep_path.is_file():
            try:
                report = load_yaml_model(crawl_rep_path, CrawlReport)
            except Exception:
                report = None
        else:
            report = None

        if report is None:
            from dich_truyen_agent.crawl_profiles import load_active_crawl_profile
            from dich_truyen_agent.paths import find_project_root

            metadata = load_yaml_model(paths.book, BookMetadata)
            project_root = find_project_root(workspace_root)
            try:
                profile_source = load_active_crawl_profile(
                    project_root, workspace_root, metadata.source_url
                )
                report = build_crawl_report(
                    workspace_root, profile_source.profile, CrawlSettings()
                )
                atomic_write_yaml(crawl_rep_path, report)
            except Exception as e:
                return {
                    "phase": "profile_repair",
                    "error_message": f"failed to load crawl profile for report: {e}",
                }

        # Check for blockers
        if report.blockers:
            if any(
                "selector" in b.lower() or "ordinal" in b.lower()
                for b in report.blockers
            ):
                return {
                    "phase": "profile_repair",
                    "error_message": f"crawl blockers: {report.blockers}",
                }
            return {
                "status": "blocked",
                "error_message": f"crawl blockers: {report.blockers}",
            }

        if (
            report.scope != ApprovalScope.FULL
            or report.completed_count < report.selected_count
        ):
            return {
                "status": "blocked",
                "error_message": f"incomplete crawl: {report.completed_count}/{report.selected_count} chapters completed",
            }

        report_hash = sha256_file(crawl_rep_path)
        evidence_hashes = _compute_crawl_evidence_hashes(workspace_root)
        return {
            "phase": "crawl_decision",
            "approval_report_hash": report_hash,
            "approval_evidence_hashes": evidence_hashes,
        }

    # 5. Crawl Decision Node (auto policy or interrupt)
    def crawl_decision_node(state: BookOrchestratorState) -> dict[str, Any]:
        workspace_root = Path(state["workspace_root"])
        paths = workspace_paths(workspace_root.parent, workspace_root.name)
        crawl_rep_path = paths.reports / "crawl.yaml"
        report = load_yaml_model(crawl_rep_path, CrawlReport)

        report_hash = state.get("approval_report_hash") or sha256_file(crawl_rep_path)
        evidence_hashes = state.get(
            "approval_evidence_hashes"
        ) or _compute_crawl_evidence_hashes(workspace_root)

        auto_approve = config.auto_approve if config else False

        # Auto policy: requires ZERO warnings
        if auto_approve and len(report.warnings) == 0:
            return {
                "pending_approval": None,
                "approval_report_hash": report_hash,
                "approval_evidence_hashes": evidence_hashes,
                "phase": "approve_crawl",
            }

        # Interrupt for manual decision (or when auto policy pauses on warnings)
        interrupt_val = {
            "type": "crawl_approval",
            "report_path": "reports/crawl.yaml",
            "report_hash": report_hash,
            "evidence_hashes": evidence_hashes,
            "warnings": report.warnings,
            "discovered_count": report.discovered_count,
            "completed_count": report.completed_count,
        }

        decision = interrupt(interrupt_val)

        # On resume: verify decision
        approved = False
        if isinstance(decision, bool):
            approved = decision
        elif isinstance(decision, dict):
            approved = bool(decision.get("approved"))
        elif isinstance(decision, str) and decision.lower() in {
            "approve",
            "approved",
            "yes",
        }:
            approved = True

        if not approved:
            return {"status": "blocked", "error_message": "crawl approval rejected"}

        # Verify evidence has not changed while waiting for decision
        current_report_hash = (
            sha256_file(crawl_rep_path) if crawl_rep_path.is_file() else None
        )
        try:
            current_evidence_hashes = _compute_crawl_evidence_hashes(workspace_root)
        except Exception as err:
            return {
                "status": "blocked",
                "pending_approval": None,
                "error_message": f"evidence verification failed: {err}",
            }
        if (
            current_report_hash != report_hash
            or current_evidence_hashes != evidence_hashes
        ):
            return {
                "status": "blocked",
                "pending_approval": None,
                "error_message": "evidence changed while awaiting crawl approval; please re-run to generate fresh report and decision",
            }

        return {
            "pending_approval": None,
            "approval_report_hash": report_hash,
            "phase": "approve_crawl",
        }

    # 6. Approve Crawl Node
    def approve_crawl_node(state: BookOrchestratorState) -> dict[str, Any]:
        workspace_root = Path(state["workspace_root"])
        paths = workspace_paths(workspace_root.parent, workspace_root.name)

        # Check if already approved (skip duplicate write)
        if (
            check_orchestrator_gate(
                workspace_root, CheckpointType.CRAWL_APPROVED
            ).status
            is not OperationStatus.OK
        ):
            report = load_yaml_model(paths.reports / "crawl.yaml", CrawlReport)
            app_res = approve_full_crawl(workspace_root, report)
            if app_res.status is not OperationStatus.OK:
                return {
                    "status": "blocked",
                    "error_message": f"approve_full_crawl failed: {app_res.reason}",
                }

        # Verify gate
        gate_res = check_orchestrator_gate(
            workspace_root, CheckpointType.CRAWL_APPROVED
        )
        if gate_res.status is not OperationStatus.OK:
            return {
                "status": "blocked",
                "error_message": f"crawl gate check failed: {gate_res.reason}",
            }

        if state["stop_after"] == "crawl":
            return {"status": "completed", "phase": "crawl"}

        return {"phase": "metadata"}

    # 7. Metadata Node
    def metadata_node(state: BookOrchestratorState) -> dict[str, Any]:
        workspace_root = Path(state["workspace_root"])
        paths = workspace_paths(workspace_root.parent, workspace_root.name)
        if not paths.book.is_file():
            return {"status": "blocked", "error_message": "book.yaml missing"}
        metadata = load_yaml_model(paths.book, BookMetadata)

        needs_translation = not metadata.translated_title or (
            metadata.author and not metadata.translated_author
        )
        if needs_translation:
            model = (
                resolve_model_for_phase(
                    "metadata_translation",
                    global_model=config.global_model,
                    translation_model=config.translation_model,
                )
                if config
                else None
            )
            prompt = (
                f"Translate novel metadata in book.yaml for book: {metadata.title}\n"
                f"Path to book.yaml: {paths.book}\n"
                f"Source title: {metadata.title}\n"
                f"Source author: {metadata.author or 'Unknown'}\n"
                "Please update book.yaml with translated_title and translated_author in Vietnamese.\n"
                "Do NOT modify chapters.yaml or state.yaml.\n"
            )
            runner.run_phase(
                phase="metadata_translation",
                workspace=workspace_root,
                prompt=prompt,
                model=model,
                timeout_seconds=600,
            )
            # Recheck metadata
            try:
                metadata = load_yaml_model(paths.book, BookMetadata)
            except Exception as e:
                return {
                    "status": "blocked",
                    "error_message": f"failed to reload book.yaml after metadata translation: {e}",
                }
            if not metadata.translated_title:
                return {
                    "status": "blocked",
                    "error_message": "metadata translation failed: translated_title is empty",
                }

        if state["stop_after"] == "metadata":
            return {"status": "completed", "phase": "metadata"}
        return {"phase": "translate"}

    # 8. Translate Node
    def translate_node(state: BookOrchestratorState) -> dict[str, Any]:
        workspace_root = Path(state["workspace_root"])
        paths = workspace_paths(workspace_root.parent, workspace_root.name)
        run_id = state["run_id"]
        run_dir = Path(state["run_dir"])

        if journal is None:
            active_journal = AttemptJournal(run_dir / "attempts.json")
        else:
            active_journal = journal

        batch_size = config.batch_size if config else 5
        translated_in_batch = 0

        while translated_in_batch < batch_size:
            # 1. First recover any pending promotion journal from a prior interrupted write
            catalog = load_yaml_model(paths.chapters, ChapterCatalog)
            for ch in catalog.chapters:
                j_file = paths.reports / f"promotion-journal-{ch.chapter_id}.yaml"
                if j_file.is_file():
                    rec_res = recover_chapter_promotion(workspace_root, ch.chapter_id)
                    if rec_res.status is not OperationStatus.OK:
                        return {
                            "status": "blocked",
                            "error_message": f"promotion recovery failed for chapter {ch.chapter_id}: {rec_res.reason}",
                        }

            # 2. Get next translation work item
            work_res = next_translation_work_item(
                workspace_root, run_id=run_id, attempt=1
            )
            if work_res.status is not OperationStatus.OK:
                return {"status": "blocked", "error_message": work_res.reason}

            work_data = work_res.data
            if work_data.get("state") == "completed":
                # All chapters are translated!
                if state["stop_after"] == "translate":
                    return {"status": "completed", "phase": "translate"}
                return {"phase": "qa"}

            chapter_id = work_data.get("chapter_id")
            if chapter_id is None:
                return {
                    "status": "blocked",
                    "error_message": "no chapter_id in next translation work item",
                }

            # Predecessor check: strictly enforce valid completed predecessor for chapter > 1
            if chapter_id > 1:
                if work_data.get("is_fallback"):
                    return {
                        "status": "blocked",
                        "error_message": f"missing predecessor translation context for chapter {chapter_id}",
                    }
                prev_path_str = work_data.get("prev_translation_path")
                if not prev_path_str or not Path(prev_path_str).is_file():
                    return {
                        "status": "blocked",
                        "error_message": f"predecessor translation file missing for chapter {chapter_id}: {prev_path_str}",
                    }
                # Check predecessor hash against state.yaml
                bstate = load_yaml_model(paths.state, BookState)
                prev_ch = next(
                    (c for c in bstate.chapters if c.chapter_id == chapter_id - 1), None
                )
                if (
                    not prev_ch
                    or prev_ch.translation.status is not StageStatus.COMPLETED
                ):
                    return {
                        "status": "blocked",
                        "error_message": f"preceding chapter {chapter_id - 1} translation status is not COMPLETED in state.yaml",
                    }
                if sha256_file(Path(prev_path_str)) != prev_ch.translation.sha256:
                    return {
                        "status": "blocked",
                        "error_message": f"predecessor translation hash mismatch for chapter {chapter_id - 1}",
                    }

            # 3. Translation attempt loop (up to 3 attempts with bounded retry)
            chapter_promoted = False
            last_err = None

            while not chapter_promoted:
                try:
                    attempt = active_journal.reserve(
                        run_id, f"chapter_{chapter_id}", limit=3
                    )
                except RuntimeError as err:
                    return {
                        "status": "blocked",
                        "error_message": f"chapter {chapter_id} retry budget exhausted: {err}",
                    }

                staged_txt, staged_yaml = get_staging_paths(
                    paths, chapter_id, run_id=run_id, attempt=attempt
                )
                staged_txt.parent.mkdir(parents=True, exist_ok=True)

                # Snapshot protected hashes
                protected_hashes = {
                    "book.yaml": sha256_file(paths.book)
                    if paths.book.is_file()
                    else None,
                    "chapters.yaml": sha256_file(paths.chapters)
                    if paths.chapters.is_file()
                    else None,
                    "state.yaml": sha256_file(paths.state)
                    if paths.state.is_file()
                    else None,
                    "style.yaml": sha256_file(paths.style)
                    if paths.style.is_file()
                    else None,
                }
                # Also snapshot any existing translated files in translations/
                if paths.translations.is_dir():
                    for f in paths.translations.glob("*.txt"):
                        protected_hashes[f"translations/{f.name}"] = sha256_file(f)

                # Build prompt with absolute paths only (never raw/translated text)
                prompt = (
                    f"Translate chapter {chapter_id}: {work_data.get('original_title', '')}\n"
                    f"chapter_id: {chapter_id}\n"
                    f"raw_path: {work_data.get('raw_path')}\n"
                    f"style_path: {work_data.get('style_path')}\n"
                    f"glossary_path: {work_data.get('glossary_path')}\n"
                    f"glossary_context_path: {work_data.get('glossary_context_path')}\n"
                    f"prev_translation_path: {work_data.get('prev_translation_path')}\n"
                    f"staged_txt: {staged_txt}\n"
                    f"staged_yaml: {staged_yaml}\n"
                    "Translate the chapter from raw_path into staged_txt.\n"
                    "Optional glossary additions may be proposed in staged_yaml.\n"
                    "Do NOT modify book.yaml, chapters.yaml, state.yaml, or any existing files in translations/.\n"
                )

                model = (
                    resolve_model_for_phase(
                        "chapter_translation",
                        global_model=config.global_model,
                        translation_model=config.translation_model,
                    )
                    if config
                    else None
                )
                timeout = config.translation_timeout_seconds if config else 1800
                runner.run_phase(
                    phase="chapter_translation",
                    workspace=workspace_root,
                    prompt=prompt,
                    model=model,
                    timeout_seconds=timeout,
                )

                # Check for unauthorized mutations
                for rel_p, orig_h in protected_hashes.items():
                    f_path = paths.root / rel_p
                    curr_h = sha256_file(f_path) if f_path.is_file() else None
                    if curr_h != orig_h:
                        return {
                            "status": "blocked",
                            "error_message": f"unauthorized workspace mutation detected in {rel_p} during translation",
                        }

                # Verify staging
                verify_res = verify_staged_chapter(
                    workspace_root,
                    chapter_id,
                    run_id=run_id,
                    attempt=attempt,
                    staged_txt_path=staged_txt,
                )
                if verify_res.status is not OperationStatus.OK:
                    last_err = verify_res.reason
                    if (
                        active_journal.get_attempts(run_id, f"chapter_{chapter_id}")
                        >= 3
                    ):
                        return {
                            "status": "blocked",
                            "error_message": f"chapter {chapter_id} staging verification failed: {last_err}",
                        }
                    continue

                # Promote
                prom_res = promote_chapter_translation(
                    workspace_root,
                    chapter_id,
                    run_id=run_id,
                    attempt=attempt,
                    staged_txt_path=staged_txt,
                    staged_yaml_path=staged_yaml,
                )
                if prom_res.status is not OperationStatus.OK:
                    return {
                        "status": "blocked",
                        "error_message": f"chapter {chapter_id} promotion failed: {prom_res.reason}",
                    }

                chapter_promoted = True
                translated_in_batch += 1
                if tracer:
                    tracer.record_invocation(
                        {
                            "phase": "chapter_translation",
                            "chapter_id": chapter_id,
                            "attempt": attempt,
                            "status": "promoted",
                        }
                    )

            # End of chapter translation

        # Batch completed: check if more chapters remain
        work_res = next_translation_work_item(workspace_root, run_id=run_id, attempt=1)
        if (
            work_res.status is OperationStatus.OK
            and work_res.data.get("state") == "completed"
        ):
            if state["stop_after"] == "translate":
                return {"status": "completed", "phase": "translate"}
            return {"phase": "qa"}

        # More chapters remain: yield checkpoint to LangGraph and continue in next batch
        return {
            "phase": "translate",
            "batch_index": state.get("batch_index", 0) + 1,
            "current_chapter_id": chapter_id,
        }

    # 9. QA Node
    def qa_node(state: BookOrchestratorState) -> dict[str, Any]:
        workspace_root = Path(state["workspace_root"])
        paths = workspace_paths(workspace_root.parent, workspace_root.name)

        # First check whether the existing qa-approved gate is current
        qa_gate = check_orchestrator_gate(workspace_root, CheckpointType.QA_APPROVED)
        if qa_gate.status is OperationStatus.OK:
            if state["stop_after"] == "qa":
                return {"status": "completed", "phase": "qa"}
            return {"phase": "export"}

        # Run deterministic QA check
        qa_rep_path = paths.reports / "qa-report.yaml"
        report = run_qa_check(workspace_root)
        atomic_write_yaml(qa_rep_path, report)
        if tracer:
            tracer.add_report_path("reports/qa-report.yaml")

        error_count = report.summary.get("error_count", 0)
        if error_count > 0:
            return {
                "status": "blocked",
                "error_code": "needs_repair",
                "error_message": f"QA check found {error_count} critical errors. Review {qa_rep_path}",
            }

        report_hash = sha256_file(qa_rep_path)
        evidence_hashes = _compute_qa_evidence_hashes(workspace_root)
        return {
            "phase": "qa_decision",
            "approval_report_path": "reports/qa-report.yaml",
            "approval_report_hash": report_hash,
            "approval_evidence_hashes": evidence_hashes,
        }

    # 10. QA Decision Node (auto policy or interrupt)
    def qa_decision_node(state: BookOrchestratorState) -> dict[str, Any]:
        workspace_root = Path(state["workspace_root"])
        paths = workspace_paths(workspace_root.parent, workspace_root.name)
        qa_rep_path = paths.reports / "qa-report.yaml"
        if not qa_rep_path.is_file():
            return {
                "status": "blocked",
                "error_message": "QA report missing before approval decision",
            }
        report = load_yaml_model(qa_rep_path, QAReport)

        report_hash = state.get("approval_report_hash") or sha256_file(qa_rep_path)
        evidence_hashes = state.get(
            "approval_evidence_hashes"
        ) or _compute_qa_evidence_hashes(workspace_root)

        auto_approve = config.auto_approve if config else False
        findings_count = report.summary.get("findings_count", len(report.findings))

        # Auto-approve policy requires ZERO findings (errors or warnings)
        if auto_approve and findings_count == 0:
            return {
                "pending_approval": None,
                "approval_report_hash": report_hash,
                "approval_evidence_hashes": evidence_hashes,
                "phase": "approve_qa",
            }

        # Interrupt for manual decision (or when auto policy pauses due to findings)
        interrupt_val = {
            "type": "qa_approval",
            "report_path": "reports/qa-report.yaml",
            "report_hash": report_hash,
            "evidence_hashes": evidence_hashes,
            "error_count": report.summary.get("error_count", 0),
            "warning_count": report.summary.get("warning_count", 0),
            "findings_count": findings_count,
        }

        decision = interrupt(interrupt_val)

        # On resume: verify decision
        approved = False
        if isinstance(decision, bool):
            approved = decision
        elif isinstance(decision, dict):
            approved = bool(decision.get("approved"))
        elif isinstance(decision, str) and decision.lower() in {
            "approve",
            "approved",
            "yes",
        }:
            approved = True

        if not approved:
            return {"status": "blocked", "error_message": "QA approval rejected"}

        # Verify evidence has not changed while waiting for decision
        current_report_hash = (
            sha256_file(qa_rep_path) if qa_rep_path.is_file() else None
        )
        try:
            current_evidence_hashes = _compute_qa_evidence_hashes(workspace_root)
        except Exception as err:
            return {
                "status": "blocked",
                "pending_approval": None,
                "error_message": f"cannot approve QA: workspace evidence changed during pause ({err})",
            }
        if (
            current_report_hash != report_hash
            or current_evidence_hashes != evidence_hashes
        ):
            return {
                "status": "blocked",
                "pending_approval": None,
                "error_message": "cannot approve QA: workspace evidence changed during pause",
            }

        return {
            "pending_approval": None,
            "approval_report_hash": report_hash,
            "approval_evidence_hashes": evidence_hashes,
            "phase": "approve_qa",
        }

    # 11. Approve QA Node
    def approve_qa_node(state: BookOrchestratorState) -> dict[str, Any]:
        workspace_root = Path(state["workspace_root"])
        paths = workspace_paths(workspace_root.parent, workspace_root.name)
        qa_rep_path = paths.reports / "qa-report.yaml"
        report = (
            load_yaml_model(qa_rep_path, QAReport) if qa_rep_path.is_file() else None
        )

        app_res = approve_current_qa(workspace_root, report=report, allow_warnings=True)
        if app_res.status is not OperationStatus.OK:
            return {
                "status": "blocked",
                "error_message": f"QA approval failed: {app_res.reason}",
            }

        gate_res = check_orchestrator_gate(workspace_root, CheckpointType.QA_APPROVED)
        if gate_res.status is not OperationStatus.OK:
            return {
                "status": "blocked",
                "error_message": f"QA gate check failed after approval: {gate_res.reason}",
            }

        if state["stop_after"] == "qa":
            return {"status": "completed", "phase": "qa"}
        return {"phase": "export"}

    # 12. Export Node
    def export_node(state: BookOrchestratorState) -> dict[str, Any]:
        workspace_root = Path(state["workspace_root"])
        paths = workspace_paths(workspace_root.parent, workspace_root.name)

        # 1. Recheck QA gate immediately before export
        gate_res = check_orchestrator_gate(workspace_root, CheckpointType.QA_APPROVED)
        if gate_res.status is not OperationStatus.OK:
            return {
                "status": "blocked",
                "error_message": f"Export blocked: QA gate is not approved ({gate_res.reason})",
            }

        # 2. Get requested formats
        formats = config.formats if config and config.formats else ["epub", "azw3"]

        # 3. Run export_book
        export_res = export_book(workspace_root, formats=formats)
        if export_res.status is not OperationStatus.OK:
            return {
                "status": "blocked",
                "error_message": f"export failed: {export_res.reason}",
            }

        # 4. Verify every explicitly requested format exists and has size > 0
        try:
            metadata = load_yaml_model(paths.book, BookMetadata)
            slug = metadata.book_slug
        except Exception as e:
            return {
                "status": "blocked",
                "error_message": f"failed to load book metadata for export verification: {e}",
            }

        missing_formats = []
        for fmt in formats:
            fmt_clean = fmt.lower().strip()
            export_file = paths.exports / f"{slug}.{fmt_clean}"
            if not export_file.is_file() or export_file.stat().st_size == 0:
                missing_formats.append(fmt_clean)

        if missing_formats:
            return {
                "status": "blocked",
                "error_message": (
                    f"export output file missing or empty for requested format(s): {', '.join(missing_formats)}. "
                    f"Export detail: {export_res.reason}"
                ),
            }

        return {"status": "completed", "phase": "export"}

    # 13. Done Node
    def done_node(state: BookOrchestratorState) -> dict[str, Any]:
        return {"status": "completed"}

    # 14. Blocked Node
    def blocked_node(state: BookOrchestratorState) -> dict[str, Any]:
        return {"status": "blocked"}

    # Router logic
    def route_inspect(state: BookOrchestratorState) -> str:
        if state.get("status") == "completed":
            return "done_node"
        if state.get("status") == "blocked":
            return "blocked_node"
        ph = state.get("phase", "crawl")
        if ph == "crawl":
            return "crawl_node"
        if ph == "translate":
            return "metadata_node"
        if ph == "qa":
            return "qa_node"
        if ph == "export":
            return "export_node"
        return "blocked_node"

    def route_crawl(state: BookOrchestratorState) -> str:
        if state.get("status") == "blocked":
            return "blocked_node"
        ph = state.get("phase")
        if ph == "profile_repair":
            return "profile_repair_node"
        if ph == "crawl_report":
            return "crawl_report_node"
        return "blocked_node"

    def route_profile_repair(state: BookOrchestratorState) -> str:
        if state.get("status") == "blocked":
            return "blocked_node"
        ph = state.get("phase")
        if ph == "crawl":
            return "crawl_node"
        if ph == "profile_repair":
            return "profile_repair_node"
        return "blocked_node"

    def route_crawl_report(state: BookOrchestratorState) -> str:
        if state.get("status") == "blocked":
            return "blocked_node"
        ph = state.get("phase")
        if ph == "profile_repair":
            return "profile_repair_node"
        if ph == "crawl_decision":
            return "crawl_decision_node"
        return "blocked_node"

    def route_crawl_decision(state: BookOrchestratorState) -> str:
        if state.get("status") == "blocked":
            return "blocked_node"
        ph = state.get("phase")
        if ph == "crawl_report":
            return "crawl_report_node"
        if ph == "approve_crawl":
            return "approve_crawl_node"
        return "blocked_node"

    def route_approve_crawl(state: BookOrchestratorState) -> str:
        if state.get("status") == "completed":
            return "done_node"
        if state.get("status") == "blocked":
            return "blocked_node"
        return "metadata_node"

    def route_metadata(state: BookOrchestratorState) -> str:
        if state.get("status") == "completed":
            return "done_node"
        if state.get("status") == "blocked":
            return "blocked_node"
        return "translate_node"

    def route_translate(state: BookOrchestratorState) -> str:
        if state.get("status") == "completed":
            return "done_node"
        if state.get("status") == "blocked":
            return "blocked_node"
        if state.get("phase") == "translate":
            return "translate_node"
        return "qa_node"

    def route_qa(state: BookOrchestratorState) -> str:
        if state.get("status") == "completed":
            return "done_node"
        if state.get("status") == "blocked":
            return "blocked_node"
        ph = state.get("phase")
        if ph == "qa_decision":
            return "qa_decision_node"
        if ph == "export":
            return "export_node"
        return "blocked_node"

    def route_qa_decision(state: BookOrchestratorState) -> str:
        if state.get("status") == "blocked":
            return "blocked_node"
        ph = state.get("phase")
        if ph == "approve_qa":
            return "approve_qa_node"
        return "blocked_node"

    def route_approve_qa(state: BookOrchestratorState) -> str:
        if state.get("status") == "completed":
            return "done_node"
        if state.get("status") == "blocked":
            return "blocked_node"
        return "export_node"

    def route_export(state: BookOrchestratorState) -> str:
        if state.get("status") == "completed":
            return "done_node"
        return "blocked_node"

    # Assemble Graph
    builder = StateGraph(BookOrchestratorState)

    builder.add_node("inspect_node", inspect_node)
    builder.add_node("crawl_node", crawl_node)
    builder.add_node("profile_repair_node", profile_repair_node)
    builder.add_node("crawl_report_node", crawl_report_node)
    builder.add_node("crawl_decision_node", crawl_decision_node)
    builder.add_node("approve_crawl_node", approve_crawl_node)
    builder.add_node("metadata_node", metadata_node)
    builder.add_node("translate_node", translate_node)
    builder.add_node("qa_node", qa_node)
    builder.add_node("qa_decision_node", qa_decision_node)
    builder.add_node("approve_qa_node", approve_qa_node)
    builder.add_node("export_node", export_node)
    builder.add_node("done_node", done_node)
    builder.add_node("blocked_node", blocked_node)

    builder.add_edge(START, "inspect_node")
    builder.add_conditional_edges("inspect_node", route_inspect)
    builder.add_conditional_edges("crawl_node", route_crawl)
    builder.add_conditional_edges("profile_repair_node", route_profile_repair)
    builder.add_conditional_edges("crawl_report_node", route_crawl_report)
    builder.add_conditional_edges("crawl_decision_node", route_crawl_decision)
    builder.add_conditional_edges("approve_crawl_node", route_approve_crawl)
    builder.add_conditional_edges("metadata_node", route_metadata)
    builder.add_conditional_edges("translate_node", route_translate)
    builder.add_conditional_edges("qa_node", route_qa)
    builder.add_conditional_edges("qa_decision_node", route_qa_decision)
    builder.add_conditional_edges("approve_qa_node", route_approve_qa)
    builder.add_conditional_edges("export_node", route_export)
    builder.add_edge("done_node", END)
    builder.add_edge("blocked_node", END)

    active_checkpointer = checkpointer if checkpointer is not None else MemorySaver()
    return builder.compile(checkpointer=active_checkpointer)


class GraphRunner:
    """Convenience runner wrapping compiled graph invocation, interruption detection, and RunOutcome."""

    def __init__(
        self,
        ops: WorkspaceOps,
        runner: HarnessRunner,
        config: OrchestratorConfig,
        checkpointer: Any = None,
        journal: AttemptJournal | None = None,
        tracer: ActivityTracer | None = None,
    ) -> None:
        self.ops = ops
        self.runner = runner
        self.config = config
        self.checkpointer = checkpointer or MemorySaver()
        self.journal = journal or AttemptJournal(
            config.workspace_root / "reports" / "runs" / config.run_id / "attempts.json"
        )
        self.tracer = tracer or ActivityTracer(
            config.workspace_root / "reports" / "runs" / config.run_id,
            RunSummary(
                run_id=config.run_id,
                status="running",
                start_at=config.start_at,
                stop_after=config.stop_after,
                selected_span=(config.start_at, config.stop_after),
                current_phase="inspect",
                requested_formats=config.formats,
                global_model=config.global_model,
                translation_model=config.translation_model,
                allow_harness_permission_bypass=config.allow_harness_permission_bypass,
            ),
        )
        self.graph = build_orchestrator_graph(
            self.ops,
            self.runner,
            self.tracer,
            checkpointer=self.checkpointer,
            journal=self.journal,
            config=self.config,
        )

    def run(self, resume_decision: Any = None) -> RunOutcome:
        thread_config = {"configurable": {"thread_id": self.config.run_id}}
        run_dir = self.config.workspace_root / "reports" / "runs" / self.config.run_id

        state_snapshot = self.graph.get_state(thread_config)
        is_paused = bool(
            state_snapshot.tasks and any(t.interrupts for t in state_snapshot.tasks)
        )

        if is_paused and resume_decision is None:
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
            self.tracer.update_status(
                "paused",
                pending_approval=pending_app,
                approval_report_path=rep_path,
            )
            return RunOutcome(
                status="paused",
                run_id=self.config.run_id,
                selected_span=(self.config.start_at, self.config.stop_after),
                current_phase=state_snapshot.values.get(
                    "phase",
                    "qa_decision" if pending_app == "qa_approval" else "crawl_decision",
                ),
                pending_approval=pending_app,
                approval_report_path=rep_path,
                approval_report_hash=rep_hash,
                exit_code=2,
                next_command=f"orchestrate --workspace {self.config.workspace_root} --resume --decision approve",
                data={"interrupt": interrupt_val},
            )

        if resume_decision is not None:
            from langgraph.types import Command

            raw_output = self.graph.invoke(
                Command(resume=resume_decision), config=thread_config
            )
        elif state_snapshot.values:
            raw_output = self.graph.invoke(None, config=thread_config)
        else:
            from dich_truyen_agent.orchestrator.state import create_initial_state

            initial_state = create_initial_state(self.config, run_dir)
            raw_output = self.graph.invoke(initial_state, config=thread_config)

        # Check if graph paused on interrupt
        state_snapshot = self.graph.get_state(thread_config)
        is_paused = bool(
            state_snapshot.tasks and any(t.interrupts for t in state_snapshot.tasks)
        )

        if is_paused:
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
            self.tracer.update_status(
                "paused",
                pending_approval=pending_app,
                approval_report_path=rep_path,
            )
            return RunOutcome(
                status="paused",
                run_id=self.config.run_id,
                selected_span=(self.config.start_at, self.config.stop_after),
                current_phase=raw_output.get(
                    "phase",
                    "qa_decision" if pending_app == "qa_approval" else "crawl_decision",
                ),
                pending_approval=pending_app,
                approval_report_path=rep_path,
                approval_report_hash=rep_hash,
                exit_code=2,
                next_command="orchestrate --resume --decision approve",
                data={"interrupt": interrupt_val},
            )

        final_status = raw_output.get("status", "completed")
        exit_code = (
            0
            if final_status == "completed"
            else (3 if final_status == "blocked" else 1)
        )
        err_msg = raw_output.get("error_message")
        self.tracer.update_status(final_status, error_message=err_msg)

        return RunOutcome(
            status=final_status,
            run_id=self.config.run_id,
            selected_span=(self.config.start_at, self.config.stop_after),
            current_phase=raw_output.get("phase", self.config.stop_after),
            error_message=err_msg,
            error_code=raw_output.get("error_code"),
            exit_code=exit_code,
        )
