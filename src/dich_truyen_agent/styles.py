from __future__ import annotations

from pathlib import Path

from dich_truyen_agent.models import OperationResult, OperationStatus, TranslationStyle
from dich_truyen_agent.storage import atomic_write_yaml, load_yaml_model


def load_style(path: Path) -> TranslationStyle:
    return load_yaml_model(path, TranslationStyle)


def load_selected_style(
    project_root: Path, custom_style_path: Path | None = None
) -> TranslationStyle:
    selected_path = (
        custom_style_path
        if custom_style_path is not None
        else project_root / "templates" / "styles" / "tien_hiep.yaml"
    )
    return load_style(selected_path)


def snapshot_style(workspace_root: Path, style: TranslationStyle) -> OperationResult:
    destination = workspace_root / "style.yaml"
    atomic_write_yaml(destination, style)
    return OperationResult(
        status=OperationStatus.OK,
        reason="style snapshot saved",
        report_paths=["style.yaml"],
    )
