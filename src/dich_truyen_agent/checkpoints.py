from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml

from dich_truyen_agent.models import (
    ApprovalScope,
    BookMetadata,
    ChapterCatalog,
    CheckpointRecord,
    CheckpointType,
    CrawlReport,
    OperationResult,
    OperationStatus,
    QAReport,
)
from dich_truyen_agent.paths import (
    find_project_root,
    validate_workspace_relative_path,
    workspace_paths,
)
from dich_truyen_agent.scope import load_source_scope, validate_scope_catalog
from dich_truyen_agent.storage import atomic_write_yaml, load_yaml_model, sha256_file


def _relative(path: Path, workspace_root: Path) -> str:
    return path.relative_to(workspace_root.resolve()).as_posix()


def approve_checkpoint(
    workspace_root: Path,
    checkpoint_type: CheckpointType,
    report_path: str,
    evidence_paths: list[str],
    scope: ApprovalScope = ApprovalScope.FULL,
    approved_at: datetime | None = None,
) -> OperationResult:
    workspace_root = workspace_root.resolve()
    report = validate_workspace_relative_path(workspace_root, report_path)
    if not report.is_file():
        raise ValueError(f"checkpoint report does not exist: {report_path}")
    evidence_hashes: dict[str, str] = {}
    for relative_path in evidence_paths:
        evidence = validate_workspace_relative_path(workspace_root, relative_path)
        if not evidence.is_file():
            raise ValueError(f"checkpoint evidence does not exist: {relative_path}")
        evidence_hashes[_relative(evidence, workspace_root)] = sha256_file(evidence)
    approval_path = workspace_root / "checkpoints" / f"{checkpoint_type.value}.yaml"
    record = CheckpointRecord(
        checkpoint_type=checkpoint_type,
        approved_at=approved_at or datetime.now(UTC),
        report_path=_relative(report, workspace_root),
        evidence_hashes=evidence_hashes,
        scope=scope,
    )
    atomic_write_yaml(approval_path, record)
    return OperationResult(
        status=OperationStatus.OK,
        reason=f"{checkpoint_type.value} checkpoint approved",
        report_paths=[record.report_path],
        approval_path=_relative(approval_path, workspace_root),
    )


def require_checkpoint_scope(
    workspace_root: Path,
    checkpoint_type: CheckpointType,
    required_scope: ApprovalScope,
) -> OperationResult:
    res = check_gate(workspace_root, checkpoint_type)
    if res.status is not OperationStatus.OK:
        return res

    paths = workspace_paths(workspace_root.parent, workspace_root.name)
    approval_path = paths.checkpoint(checkpoint_type.value)
    record = load_yaml_model(approval_path, CheckpointRecord)

    if required_scope == ApprovalScope.FULL and record.scope == ApprovalScope.PARTIAL:
        return OperationResult(
            status=OperationStatus.BLOCKED,
            reason=f"checkpoint {checkpoint_type.value} scope is partial, but full scope is required",
            approval_path=_relative(approval_path, workspace_root),
        )
    return res


def check_gate(
    workspace_root: Path,
    checkpoint_type: CheckpointType,
    *,
    strict: bool = False,
) -> OperationResult:
    workspace_root = workspace_root.resolve()
    paths = workspace_paths(workspace_root.parent, workspace_root.name)
    approval_path = workspace_root / "checkpoints" / f"{checkpoint_type.value}.yaml"
    relative_approval = _relative(approval_path, workspace_root)
    if not approval_path.is_file():
        return OperationResult(
            status=OperationStatus.BLOCKED,
            reason=f"missing {checkpoint_type.value} checkpoint",
            approval_path=relative_approval,
        )
    try:
        record = load_yaml_model(approval_path, CheckpointRecord)
        if record.checkpoint_type is not checkpoint_type:
            raise ValueError("checkpoint type mismatch")
        validate_workspace_relative_path(workspace_root, record.report_path)
        for relative_path, expected_hash in record.evidence_hashes.items():
            evidence = validate_workspace_relative_path(workspace_root, relative_path)
            if not evidence.is_file() or sha256_file(evidence) != expected_hash:
                raise ValueError(f"stale evidence: {relative_path}")

        if strict:
            metadata = (
                load_yaml_model(paths.book, BookMetadata)
                if paths.book.is_file()
                else None
            )
            if metadata and metadata.scope_managed:
                if "reports/source-scope.yaml" not in record.evidence_hashes:
                    return OperationResult(
                        status=OperationStatus.BLOCKED,
                        reason=f"{checkpoint_type.value} approval missing reports/source-scope.yaml in evidence for scope-managed workspace",
                        approval_path=relative_approval,
                    )
                if not paths.source_scope.is_file():
                    return OperationResult(
                        status=OperationStatus.BLOCKED,
                        reason="missing reports/source-scope.yaml for scope-managed workspace",
                        approval_path=relative_approval,
                    )
                try:
                    scope_rec = load_source_scope(paths.source_scope)
                    if paths.chapters.is_file():
                        cat = load_yaml_model(paths.chapters, ChapterCatalog)
                        val = validate_scope_catalog(scope_rec, cat)
                        if not val.is_valid:
                            return OperationResult(
                                status=OperationStatus.BLOCKED,
                                reason=f"{checkpoint_type.value} scope validation failed: {val.reason}",
                                approval_path=relative_approval,
                            )
                except Exception as err:
                    return OperationResult(
                        status=OperationStatus.BLOCKED,
                        reason=f"stale or invalid reports/source-scope.yaml: {err}",
                        approval_path=relative_approval,
                    )

            if checkpoint_type is CheckpointType.CRAWL_APPROVED:
                if "chapters.yaml" not in record.evidence_hashes:
                    return OperationResult(
                        status=OperationStatus.BLOCKED,
                        reason="legacy crawl approval missing chapters.yaml in evidence; run approve-crawl to regenerate",
                        approval_path=relative_approval,
                    )
                if record.scope != ApprovalScope.FULL:
                    return OperationResult(
                        status=OperationStatus.BLOCKED,
                        reason=f"crawl approval scope is {record.scope.value}, but full scope is required; run approve-crawl to regenerate",
                        approval_path=relative_approval,
                    )
                if "reports/crawl.yaml" not in record.evidence_hashes:
                    return OperationResult(
                        status=OperationStatus.BLOCKED,
                        reason="crawl approval missing reports/crawl.yaml in evidence; run approve-crawl to regenerate",
                        approval_path=relative_approval,
                    )
            elif checkpoint_type is CheckpointType.QA_APPROVED:
                if "chapters.yaml" not in record.evidence_hashes:
                    return OperationResult(
                        status=OperationStatus.BLOCKED,
                        reason="legacy QA approval missing chapters.yaml in evidence; run approve-qa to regenerate",
                        approval_path=relative_approval,
                    )
                if "state.yaml" not in record.evidence_hashes:
                    return OperationResult(
                        status=OperationStatus.BLOCKED,
                        reason="legacy QA approval missing state.yaml in evidence; run approve-qa to regenerate",
                        approval_path=relative_approval,
                    )
                if "reports/qa-report.yaml" not in record.evidence_hashes:
                    return OperationResult(
                        status=OperationStatus.BLOCKED,
                        reason="QA approval missing reports/qa-report.yaml in evidence; run approve-qa to regenerate",
                        approval_path=relative_approval,
                    )
    except (OSError, ValueError, yaml.YAMLError) as error:
        return OperationResult(
            status=OperationStatus.BLOCKED,
            reason=f"stale or invalid {checkpoint_type.value} checkpoint: {error}",
            approval_path=relative_approval,
        )
    return OperationResult(
        status=OperationStatus.OK,
        reason=f"{checkpoint_type.value} checkpoint is current",
        report_paths=[record.report_path],
        approval_path=relative_approval,
    )


def check_orchestrator_gate(
    workspace_root: Path,
    checkpoint_type: CheckpointType,
) -> OperationResult:
    """Run stricter gate checks for orchestrator transitions."""
    return check_gate(workspace_root, checkpoint_type, strict=True)


def approve_full_crawl(
    workspace_root: Path,
    report: CrawlReport | None = None,
) -> OperationResult:
    """Approve full-scope crawl evidence, enforcing all full-book criteria and tracking catalog + raw."""
    try:
        workspace_root = Path(workspace_root).resolve()
        paths = workspace_paths(workspace_root.parent, workspace_root.name)

        if report is None:
            if paths.crawl_report.is_file():
                report = load_yaml_model(paths.crawl_report, CrawlReport)
            else:
                from dich_truyen_agent.crawl_profiles import load_active_crawl_profile
                from dich_truyen_agent.crawl_reports import build_crawl_report
                from dich_truyen_agent.models import CrawlSettings

                metadata = load_yaml_model(paths.book, BookMetadata)
                project_root = find_project_root(workspace_root)
                profile_source = load_active_crawl_profile(
                    project_root, workspace_root, metadata.source_url
                )
                report = build_crawl_report(
                    workspace_root,
                    profile_source.profile,
                    CrawlSettings(max_chapters=0),
                )

        # Check full-book criteria
        from dich_truyen_agent.crawl_reports import approval_blockers

        blockers = approval_blockers(report)
        if blockers:
            return OperationResult(
                status=OperationStatus.BLOCKED,
                reason=f"crawl approval blocked due to findings: {blockers}",
                report_paths=[str(paths.crawl_report)],
            )

        if not paths.chapters.is_file():
            return OperationResult(
                status=OperationStatus.BLOCKED,
                reason="crawl approval blocked: chapters.yaml catalog is missing",
                report_paths=[str(paths.crawl_report)],
            )

        catalog = load_yaml_model(paths.chapters, ChapterCatalog)
        if not catalog.chapters:
            return OperationResult(
                status=OperationStatus.BLOCKED,
                reason="crawl approval blocked: catalog has no chapters",
                report_paths=[str(paths.crawl_report)],
            )

        metadata = (
            load_yaml_model(paths.book, BookMetadata) if paths.book.is_file() else None
        )
        if metadata and metadata.scope_managed:
            if not paths.source_scope.is_file():
                return OperationResult(
                    status=OperationStatus.BLOCKED,
                    reason="crawl approval blocked: scope_managed workspace is missing reports/source-scope.yaml",
                    report_paths=[str(paths.crawl_report)],
                )
            try:
                scope_rec = load_source_scope(paths.source_scope)
                scope_val = validate_scope_catalog(scope_rec, catalog)
                if not scope_val.is_valid:
                    return OperationResult(
                        status=OperationStatus.BLOCKED,
                        reason=f"crawl approval blocked: source scope validation failed: {scope_val.reason}",
                        report_paths=[str(paths.crawl_report)],
                    )
            except Exception as err:
                return OperationResult(
                    status=OperationStatus.BLOCKED,
                    reason=f"crawl approval blocked: invalid source scope record: {err}",
                    report_paths=[str(paths.crawl_report)],
                )

        evidence: list[str] = ["chapters.yaml", "reports/crawl.yaml"]
        if metadata and metadata.scope_managed:
            evidence.append("reports/source-scope.yaml")
        for tc in catalog.chapters:
            raw_rel = f"raw/{tc.raw_filename}"
            raw_file = validate_workspace_relative_path(workspace_root, raw_rel)
            if not raw_file.is_file():
                return OperationResult(
                    status=OperationStatus.BLOCKED,
                    reason=f"crawl approval blocked: raw chapter file missing: {raw_rel}",
                    report_paths=[str(paths.crawl_report)],
                )
            evidence.append(raw_rel)

        atomic_write_yaml(paths.crawl_report, report)

        return approve_checkpoint(
            workspace_root=workspace_root,
            checkpoint_type=CheckpointType.CRAWL_APPROVED,
            report_path="reports/crawl.yaml",
            evidence_paths=evidence,
            scope=ApprovalScope.FULL,
        )
    except Exception as error:
        return OperationResult(
            status=OperationStatus.ERROR,
            reason=f"crawl approval failed: {error}",
        )


def approve_current_qa(
    workspace_root: Path,
    report: QAReport | None = None,
    allow_warnings: bool = False,
) -> OperationResult:
    """Approve current QA evidence, tracking catalog, state, report, and all translations."""
    try:
        workspace_root = Path(workspace_root).resolve()
        paths = workspace_paths(workspace_root.parent, workspace_root.name)
        qa_report_path = paths.reports / "qa-report.yaml"

        if not paths.chapters.is_file():
            return OperationResult(
                status=OperationStatus.BLOCKED,
                reason="QA approval blocked: chapters.yaml catalog is missing",
                report_paths=["reports/qa-report.yaml"],
            )
        catalog = load_yaml_model(paths.chapters, ChapterCatalog)
        if not catalog.chapters:
            return OperationResult(
                status=OperationStatus.BLOCKED,
                reason="QA approval blocked: catalog has no chapters",
                report_paths=["reports/qa-report.yaml"],
            )

        if not paths.state.is_file():
            return OperationResult(
                status=OperationStatus.BLOCKED,
                reason="QA approval blocked: state.yaml is missing",
                report_paths=["reports/qa-report.yaml"],
            )

        metadata = (
            load_yaml_model(paths.book, BookMetadata) if paths.book.is_file() else None
        )
        if metadata and metadata.scope_managed:
            if not paths.source_scope.is_file():
                return OperationResult(
                    status=OperationStatus.BLOCKED,
                    reason="QA approval blocked: scope_managed workspace is missing reports/source-scope.yaml",
                    report_paths=["reports/qa-report.yaml"],
                )
            try:
                scope_rec = load_source_scope(paths.source_scope)
                scope_val = validate_scope_catalog(scope_rec, catalog)
                if not scope_val.is_valid:
                    return OperationResult(
                        status=OperationStatus.BLOCKED,
                        reason=f"QA approval blocked: source scope validation failed: {scope_val.reason}",
                        report_paths=["reports/qa-report.yaml"],
                    )
            except Exception as err:
                return OperationResult(
                    status=OperationStatus.BLOCKED,
                    reason=f"QA approval blocked: invalid source scope record: {err}",
                    report_paths=["reports/qa-report.yaml"],
                )

        if report is None:
            if qa_report_path.is_file():
                report = load_yaml_model(qa_report_path, QAReport)
            else:
                from dich_truyen_agent.qa import run_qa_check

                report = run_qa_check(workspace_root)

        error_count = report.summary.get("error_count", 0)
        if error_count > 0:
            return OperationResult(
                status=OperationStatus.BLOCKED,
                reason=f"QA approval blocked: workspace contains {error_count} critical errors. Run check-translation for details.",
                report_paths=["reports/qa-report.yaml"],
            )

        findings_count = report.summary.get("findings_count", len(report.findings))
        if findings_count > 0 and not allow_warnings:
            return OperationResult(
                status=OperationStatus.BLOCKED,
                reason=f"QA approval blocked: workspace contains {findings_count} findings and allow_warnings is False.",
                report_paths=["reports/qa-report.yaml"],
            )

        atomic_write_yaml(qa_report_path, report)

        evidence = ["chapters.yaml", "state.yaml", "reports/qa-report.yaml"]
        if metadata and metadata.scope_managed:
            evidence.append("reports/source-scope.yaml")
        for entry in catalog.chapters:
            trans_file = paths.translations / entry.translation_filename
            if not trans_file.is_file():
                return OperationResult(
                    status=OperationStatus.BLOCKED,
                    reason=f"QA approval blocked: missing translation file: translations/{entry.translation_filename}",
                    report_paths=["reports/qa-report.yaml"],
                )
            evidence.append(f"translations/{entry.translation_filename}")

        scope = ApprovalScope.FULL if findings_count == 0 else ApprovalScope.PARTIAL
        return approve_checkpoint(
            workspace_root=workspace_root,
            checkpoint_type=CheckpointType.QA_APPROVED,
            report_path="reports/qa-report.yaml",
            evidence_paths=evidence,
            scope=scope,
        )
    except Exception as error:
        return OperationResult(
            status=OperationStatus.ERROR,
            reason=f"QA approval failed: {error}",
        )
