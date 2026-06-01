from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml

from dich_truyen_agent.models import (
    ApprovalScope,
    CheckpointRecord,
    CheckpointType,
    OperationResult,
    OperationStatus,
)
from dich_truyen_agent.paths import validate_workspace_relative_path, workspace_paths
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
    workspace_root: Path, checkpoint_type: CheckpointType
) -> OperationResult:
    workspace_root = workspace_root.resolve()
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
