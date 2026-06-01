from __future__ import annotations

import argparse
from pathlib import Path

from dich_truyen_agent.checkpoints import approve_checkpoint, check_gate
from dich_truyen_agent.models import (
    BookMetadata,
    BookState,
    ChapterCatalog,
    CheckpointType,
    CrawlSettings,
    OperationResult,
    OperationStatus,
    GlossaryTerm,
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


def main() -> None:
    args = build_parser().parse_args()
    _print_result(run_command(args))
