from __future__ import annotations

import argparse
from pathlib import Path

from dich_truyen_agent.checkpoints import approve_checkpoint, check_gate
from dich_truyen_agent.models import (
    ApprovalScope,
    BookMetadata,
    BookState,
    ChapterCatalog,
    CheckpointType,
    CrawlSettings,
    OperationResult,
    OperationStatus,
    GlossaryTerm,
    TranslationSettings,
)
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.storage import atomic_write_yaml
from dich_truyen_agent.styles import load_selected_style, load_style
from dich_truyen_agent.workspace import (
    initialize_workspace,
    inspect_workspace,
    resume_workspace,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dich Truyen Agent deterministic helpers")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_json_flag(command_parser: argparse.ArgumentParser) -> None:
        command_parser.add_argument("--json", action="store_true")

    init = subparsers.add_parser("init-book")
    init.add_argument("--books-root", type=Path, default=Path("books"))
    init.add_argument("--slug", required=True)
    init.add_argument("--source-url", required=True)
    init.add_argument("--title", required=True)
    init.add_argument("--author")
    init.add_argument("--style", type=Path)
    init.add_argument("--resume", action="store_true")

    inspect = subparsers.add_parser("inspect-workspace")
    inspect.add_argument("--workspace", type=Path, required=True)

    approve = subparsers.add_parser("approve-checkpoint")
    approve.add_argument("--workspace", type=Path, required=True)
    approve.add_argument("--type", dest="checkpoint_type", choices=[item.value for item in CheckpointType], required=True)
    approve.add_argument("--report", required=True)
    approve.add_argument("--evidence", nargs="+", required=True)

    gate = subparsers.add_parser("check-gate")
    gate.add_argument("--workspace", type=Path, required=True)
    gate.add_argument("--type", dest="checkpoint_type", choices=[item.value for item in CheckpointType], required=True)
    add_json_flag(gate)

    validate = subparsers.add_parser("validate-style")
    validate.add_argument("--style", type=Path, required=True)
    validate.add_argument("--workspace", type=Path)

    # Phase 2 Crawl Commands
    crawl = subparsers.add_parser("crawl-book")
    crawl.add_argument("--books-root", type=Path, default=Path("books"))
    crawl.add_argument("--slug", required=True)
    crawl.add_argument("--source-url", required=True)
    crawl.add_argument("--style")
    crawl.add_argument("--max-chapters", type=int, default=0)
    crawl.add_argument("--chapter-delay-seconds", type=float, default=3.0)

    val_prof = subparsers.add_parser("validate-crawl-profile")
    val_prof.add_argument("--workspace", type=Path, required=True)
    val_prof.add_argument("--profile", type=Path, required=True)

    prom_prof = subparsers.add_parser("promote-crawl-profile")
    prom_prof.add_argument("--workspace", type=Path, required=True)

    app_crawl = subparsers.add_parser("approve-crawl")
    app_crawl.add_argument("--workspace", type=Path, required=True)
    app_crawl.add_argument("--max-chapters", type=int, default=0)

    # Phase 3 Glossary Commands
    gen_glos = subparsers.add_parser("generate-glossary")
    gen_glos.add_argument("--books-root", type=Path, default=Path("books"))
    gen_glos.add_argument("--slug", required=True)
    gen_glos.add_argument("--chapters", default="1,2,3")
    gen_glos.add_argument("--terms-input", type=Path)

    merge_prop = subparsers.add_parser("merge-proposals")
    merge_prop.add_argument("--workspace", type=Path, required=True)
    merge_prop.add_argument("--chapter-id", type=int, required=True)
    merge_prop.add_argument("--proposals", type=Path, required=True)

    lock_t = subparsers.add_parser("lock-term")
    lock_t.add_argument("--workspace", type=Path, required=True)
    lock_t.add_argument("--term", required=True)

    # Phase 4 Translation Commands
    prep_trans = subparsers.add_parser("prepare-translation-context")
    prep_trans.add_argument("--workspace", type=Path, required=True)
    prep_trans.add_argument("--chapter-id", type=int, required=True)
    add_json_flag(prep_trans)

    prom_ch = subparsers.add_parser("promote-chapter")
    prom_ch.add_argument("--workspace", type=Path, required=True)
    prom_ch.add_argument("--chapter-id", type=int, required=True)
    add_json_flag(prom_ch)

    show_prog = subparsers.add_parser("show-translation-progress")
    show_prog.add_argument("--workspace", type=Path, required=True)
    add_json_flag(show_prog)

    next_work = subparsers.add_parser("next-translation-work-item")
    next_work.add_argument("--workspace", type=Path, required=True)
    add_json_flag(next_work)

    verify_staged = subparsers.add_parser("verify-staged-chapter")
    verify_staged.add_argument("--workspace", type=Path, required=True)
    verify_staged.add_argument("--chapter-id", type=int, required=True)
    add_json_flag(verify_staged)

    show_trans_settings = subparsers.add_parser("show-translation-settings")
    add_json_flag(show_trans_settings)

    # Phase 5 Quality Assurance Commands
    check_trans = subparsers.add_parser("check-translation")
    check_trans.add_argument("--workspace", type=Path, required=True)

    app_qa = subparsers.add_parser("approve-qa")
    app_qa.add_argument("--workspace", type=Path, required=True)

    # Phase 6 Export Commands
    export_cmd = subparsers.add_parser("export-book")
    export_cmd.add_argument("--workspace", type=Path, required=True)
    export_cmd.add_argument("--formats", default="epub,azw3")

    update_meta = subparsers.add_parser("update-book-metadata")
    update_meta.add_argument("--workspace", type=Path, required=True)
    update_meta.add_argument("--translated-title", required=True)
    update_meta.add_argument("--translated-author")

    return parser



def _persist_result(workspace_root: Path | None, command: str, result: OperationResult) -> None:
    if workspace_root is None or not workspace_root.is_dir():
        return
    atomic_write_yaml(workspace_root / "reports" / "results" / f"{command}.yaml", result)


def run_command(args: argparse.Namespace) -> OperationResult:
    workspace_root: Path | None = getattr(args, "workspace", None)
    if args.command == "init-book":
        if args.resume:
            result = resume_workspace(args.books_root, args.slug)
        else:
            style = load_selected_style(PROJECT_ROOT, args.style)
            metadata = BookMetadata(
                book_slug=args.slug,
                source_url=args.source_url,
                title=args.title,
                author=args.author,
            )
            result = initialize_workspace(
                args.books_root,
                metadata,
                ChapterCatalog(),
                style,
            )
        workspace_root = workspace_paths(args.books_root, args.slug).root
    elif args.command == "inspect-workspace":
        result = inspect_workspace(args.workspace)
    elif args.command == "approve-checkpoint":
        result = approve_checkpoint(
            args.workspace,
            CheckpointType(args.checkpoint_type),
            args.report,
            args.evidence,
        )
    elif args.command == "check-gate":
        result = check_gate(args.workspace, CheckpointType(args.checkpoint_type))
    elif args.command == "validate-style":
        style = load_style(args.style)
        result = OperationResult(
            status=OperationStatus.OK,
            reason=f"style is valid: {style.name}",
            report_paths=[str(args.style)],
        )
    elif args.command == "crawl-book":
        import asyncio
        from dich_truyen_agent.crawl_batch import crawl_book
        
        result = asyncio.run(
            crawl_book(
                books_root=args.books_root,
                book_slug=args.slug,
                source_url=args.source_url,
                project_root=PROJECT_ROOT,
                style_name=args.style,
                max_chapters=args.max_chapters,
                chapter_delay_seconds=args.chapter_delay_seconds,
            )
        )
        workspace_root = workspace_paths(args.books_root, args.slug).root
    elif args.command == "validate-crawl-profile":
        from dich_truyen_agent.crawl_profiles import load_crawl_profile, _source_host, _require_matching_domain
        from dich_truyen_agent.storage import load_yaml_model
        
        try:
            profile = load_crawl_profile(args.profile)
            paths = workspace_paths(args.workspace.parent, args.workspace.name)
            metadata = load_yaml_model(paths.book, BookMetadata)
            domain = _source_host(metadata.source_url)
            _require_matching_domain(profile, domain)
            result = OperationResult(
                status=OperationStatus.OK,
                reason="crawl profile is valid and domain matches book source domain",
                report_paths=[str(args.profile)],
            )
        except Exception as e:
            result = OperationResult(
                status=OperationStatus.ERROR,
                reason=f"crawl profile validation failed: {e}",
            )
    elif args.command == "promote-crawl-profile":
        from dich_truyen_agent.crawl_profiles import promote_local_crawl_profile
        try:
            shared_path = promote_local_crawl_profile(PROJECT_ROOT, args.workspace)
            result = OperationResult(
                status=OperationStatus.OK,
                reason=f"local override crawl profile promoted to shared domain profile: {shared_path.name}",
                report_paths=[str(shared_path)],
            )
        except Exception as e:
            result = OperationResult(
                status=OperationStatus.ERROR,
                reason=f"crawl profile promotion failed: {e}",
            )
    elif args.command == "approve-crawl":
        from dich_truyen_agent.storage import load_yaml_model
        from dich_truyen_agent.crawl_profiles import load_active_crawl_profile
        from dich_truyen_agent.crawl_reports import build_crawl_report, approval_blockers
        
        try:
            paths = workspace_paths(args.workspace.parent, args.workspace.name)
            metadata = load_yaml_model(paths.book, BookMetadata)
            profile_source = load_active_crawl_profile(PROJECT_ROOT, args.workspace, metadata.source_url)
            
            settings = CrawlSettings(max_chapters=args.max_chapters)
            report = build_crawl_report(args.workspace, profile_source.profile, settings)
            
            blockers = approval_blockers(report)
            if blockers:
                result = OperationResult(
                    status=OperationStatus.BLOCKED,
                    reason=f"crawl approval blocked due to findings: {blockers}",
                    report_paths=[str(paths.crawl_report)],
                )
            else:
                # Save the crawl report
                atomic_write_yaml(paths.crawl_report, report)
                
                # Evidence hashing
                catalog = load_yaml_model(paths.chapters, ChapterCatalog)
                state = load_yaml_model(paths.state, BookState)
                target_chapters = catalog.chapters
                if args.max_chapters > 0:
                    target_chapters = catalog.chapters[:args.max_chapters]
                    
                evidence = ["reports/crawl.yaml"]
                state_by_id = {ch.chapter_id: ch for ch in state.chapters}
                for tc in target_chapters:
                    c_state = state_by_id.get(tc.chapter_id)
                    if c_state and c_state.raw.canonical_path:
                        evidence.append(c_state.raw.canonical_path)
                
                result = approve_checkpoint(
                    workspace_root=args.workspace,
                    checkpoint_type=CheckpointType.CRAWL_APPROVED,
                    report_path="reports/crawl.yaml",
                    evidence_paths=evidence,
                    scope=report.scope,
                )
        except Exception as e:
            result = OperationResult(
                status=OperationStatus.ERROR,
                reason=f"crawl approval failed: {e}",
            )
    elif args.command == "generate-glossary":
        from dich_truyen_agent.glossary import initialize_glossary_file
        import yaml
        
        try:
            workspace_root = workspace_paths(args.books_root, args.slug).root
            
            # Load from input file if provided
            if args.terms_input:
                if not args.terms_input.is_file():
                    result = OperationResult(
                        status=OperationStatus.ERROR,
                        reason=f"Terms input file does not exist: {args.terms_input}",
                    )
                else:
                    with args.terms_input.open(encoding="utf-8") as stream:
                        terms_data = yaml.safe_load(stream)
                    result = initialize_glossary_file(workspace_root, terms_data)
            else:
                result = initialize_glossary_file(workspace_root, {})
        except Exception as e:
            result = OperationResult(
                status=OperationStatus.ERROR,
                reason=f"Glossary generation failed: {e}",
            )
    elif args.command == "merge-proposals":
        from dich_truyen_agent.glossary import merge_glossary_proposals
        from dich_truyen_agent.storage import load_yaml_model
        import yaml
        
        try:
            if not args.proposals.is_file():
                result = OperationResult(
                    status=OperationStatus.ERROR,
                    reason=f"Proposals file does not exist: {args.proposals}",
                )
            else:
                with args.proposals.open(encoding="utf-8") as stream:
                    proposals_raw = yaml.safe_load(stream)
                
                proposals = {}
                for term, data in proposals_raw.items():
                    proposals[term] = GlossaryTerm(
                        translation=data.get("translation", ""),
                        category=data.get("category", "other"),
                        source=f"chapter_{args.chapter_id}_proposal",
                        is_canonical=False,
                        note=data.get("note"),
                    )
                result = merge_glossary_proposals(args.workspace, args.chapter_id, proposals)
        except Exception as e:
            result = OperationResult(
                status=OperationStatus.ERROR,
                reason=f"Merge proposals failed: {e}",
            )
    elif args.command == "lock-term":
        from dich_truyen_agent.glossary import lock_glossary_term
        
        try:
            result = lock_glossary_term(args.workspace, args.term)
        except Exception as e:
            result = OperationResult(
                status=OperationStatus.ERROR,
                reason=f"Lock term failed: {e}",
            )
    elif args.command == "prepare-translation-context":
        from dich_truyen_agent.workspace import prepare_translation_context
        
        try:
            result = prepare_translation_context(args.workspace, args.chapter_id)
        except Exception as e:
            result = OperationResult(
                status=OperationStatus.ERROR,
                reason=f"Prepare translation context failed: {e}",
            )
    elif args.command == "promote-chapter":
        from dich_truyen_agent.workspace import promote_chapter_translation
        
        try:
            result = promote_chapter_translation(args.workspace, args.chapter_id)
        except Exception as e:
            result = OperationResult(
                status=OperationStatus.ERROR,
                reason=f"Promote chapter failed: {e}",
            )
    elif args.command == "show-translation-progress":
        from dich_truyen_agent.workspace import get_next_pending_translation
        
        try:
            result = get_next_pending_translation(args.workspace)
        except Exception as e:
            result = OperationResult(
                status=OperationStatus.ERROR,
                reason=f"Show translation progress failed: {e}",
            )
    elif args.command == "next-translation-work-item":
        from dich_truyen_agent.workspace import next_translation_work_item

        try:
            result = next_translation_work_item(args.workspace)
        except Exception as e:
            result = OperationResult(
                status=OperationStatus.ERROR,
                reason=f"Next translation work item failed: {e}",
            )
    elif args.command == "verify-staged-chapter":
        from dich_truyen_agent.workspace import verify_staged_chapter

        try:
            result = verify_staged_chapter(args.workspace, args.chapter_id)
        except Exception as e:
            result = OperationResult(
                status=OperationStatus.ERROR,
                reason=f"Verify staged chapter failed: {e}",
            )
    elif args.command == "show-translation-settings":
        try:
            settings = TranslationSettings(_env_file=PROJECT_ROOT / ".env")
            result = OperationResult(
                status=OperationStatus.OK,
                reason="translation settings loaded",
                data={"batch_size": settings.batch_size},
            )
        except Exception as e:
            result = OperationResult(
                status=OperationStatus.ERROR,
                reason=f"Show translation settings failed: {e}",
                data={"failure_reason": str(e)},
            )
    elif args.command == "check-translation":
        from dich_truyen_agent.qa import run_qa_check
        
        try:
            # 1. Run check
            report = run_qa_check(args.workspace)
            
            # 2. Persist report.yaml atomically
            paths = workspace_paths(args.workspace.parent, args.workspace.name)
            qa_report_path = paths.reports / "qa-report.yaml"
            atomic_write_yaml(qa_report_path, report)
            
            # 3. Print beautiful Markdown table to console stdout
            print("\n### Translation QA Findings Summary")
            print(f"**Passed Checks:** {report.summary['passed']}")
            print(f"**Total Findings:** {report.summary['findings_count']} (Errors: {report.summary['error_count']}, Warnings: {report.summary['warning_count']})\n")
            
            if report.findings:
                print("| Chapter | Type | Severity | Finding Details |")
                print("| :--- | :--- | :--- | :--- |")
                for f in report.findings:
                    msg = f.message
                    if f.details and "snippet" in f.details:
                        msg += f" Context: `{f.details['snippet']}`"
                    print(f"| {f.chapter_id} | {f.finding_type.value} | {f.severity} | {msg} |")
                print()
            else:
                print("✨ No issues found! Workspace is ready for approval.\n")
                
            result = OperationResult(
                status=OperationStatus.OK if report.summary['passed'] else OperationStatus.BLOCKED,
                reason=f"QA check completed with {report.summary['findings_count']} findings",
                report_paths=[str(qa_report_path.resolve().relative_to(args.workspace.resolve()).as_posix())],
            )
        except Exception as e:
            result = OperationResult(
                status=OperationStatus.ERROR,
                reason=f"Check translation failed: {e}",
            )
    elif args.command == "approve-qa":
        from dich_truyen_agent.qa import run_qa_check
        from dich_truyen_agent.storage import load_yaml_model
        
        try:
            paths = workspace_paths(args.workspace.parent, args.workspace.name)
            qa_report_path = paths.reports / "qa-report.yaml"
            
            # Load or run QA check
            if qa_report_path.is_file():
                from dich_truyen_agent.models import QAReport
                report = load_yaml_model(qa_report_path, QAReport)
            else:
                report = run_qa_check(args.workspace)
                atomic_write_yaml(qa_report_path, report)
                
            if report.summary["error_count"] > 0:
                result = OperationResult(
                    status=OperationStatus.BLOCKED,
                    reason=f"QA approval blocked: workspace contains {report.summary['error_count']} critical errors. Run main.py check-translation for details.",
                    report_paths=[str(qa_report_path.resolve().relative_to(args.workspace.resolve()).as_posix())],
                )
            else:
                # Evidence hashing: all translation files in Chapters catalog
                catalog = load_yaml_model(paths.chapters, ChapterCatalog)
                evidence = [str(qa_report_path.resolve().relative_to(args.workspace.resolve()).as_posix())]
                for entry in catalog.chapters:
                    trans_file = paths.translations / entry.translation_filename
                    if trans_file.is_file():
                        evidence.append(str(trans_file.resolve().relative_to(args.workspace.resolve()).as_posix()))
                        
                result = approve_checkpoint(
                    workspace_root=args.workspace,
                    checkpoint_type=CheckpointType.QA_APPROVED,
                    report_path=str(qa_report_path.resolve().relative_to(args.workspace.resolve()).as_posix()),
                    evidence_paths=evidence,
                    scope=ApprovalScope.FULL if report.summary["findings_count"] == 0 else ApprovalScope.PARTIAL,
                )
        except Exception as e:
            result = OperationResult(
                status=OperationStatus.ERROR,
                reason=f"QA approval failed: {e}",
            )
    elif args.command == "export-book":
        from dich_truyen_agent.export import export_book
        
        try:
            formats_list = [f.strip() for f in args.formats.split(",") if f.strip()]
            result = export_book(args.workspace, formats_list)
        except Exception as e:
            result = OperationResult(
                status=OperationStatus.ERROR,
                reason=f"Export failed: {e}",
            )
    elif args.command == "update-book-metadata":
        from dich_truyen_agent.workspace import update_book_metadata
        
        try:
            result = update_book_metadata(
                args.workspace,
                args.translated_title,
                args.translated_author,
            )
        except Exception as e:
            result = OperationResult(
                status=OperationStatus.ERROR,
                reason=f"Update metadata failed: {e}",
            )
    else:
        raise ValueError(f"unsupported command: {args.command}")

    _persist_result(workspace_root, args.command, result)
    return result


def _print_result(result: OperationResult) -> None:
    print(f"status: {result.status.value}")
    print(f"reason: {result.reason}")
    if result.progress is not None:
        print(f"progress: {result.progress.completed}/{result.progress.total}")
    for report_path in result.report_paths:
        print(f"report: {report_path}")
    if result.approval_path:
        print(f"approval: {result.approval_path}")


def _print_json_result(result: OperationResult) -> None:
    print(result.model_dump_json(indent=2))


def main() -> None:
    args = build_parser().parse_args()
    result = run_command(args)
    if getattr(args, "json", False):
        _print_json_result(result)
    else:
        _print_result(result)
