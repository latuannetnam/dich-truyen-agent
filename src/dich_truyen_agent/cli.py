from __future__ import annotations

import argparse
from pathlib import Path

from dich_truyen_agent.checkpoints import approve_checkpoint, check_gate
from dich_truyen_agent.models import (
    BookMetadata,
    ChapterCatalog,
    CheckpointType,
    OperationResult,
    OperationStatus,
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
