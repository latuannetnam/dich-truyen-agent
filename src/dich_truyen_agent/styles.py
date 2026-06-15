from __future__ import annotations

from pathlib import Path

from dich_truyen_agent.models import OperationResult, OperationStatus, TranslationStyle
from dich_truyen_agent.storage import atomic_write_yaml, load_yaml_model


def load_style(path: Path) -> TranslationStyle:
    return load_yaml_model(path, TranslationStyle)


def resolve_style_path(
    project_root: Path, custom_style: Path | None = None
) -> Path:
    styles_dir = project_root / "templates" / "styles"
    if custom_style is None:
        return styles_dir / "general.yaml"
    if custom_style.exists():
        return custom_style
    # Bare profile name (e.g. Path("mat_the")) -> templates/styles/<name>.yaml
    named = styles_dir / f"{custom_style.name}.yaml"
    if named.exists():
        return named
    raise ValueError(
        f"unknown style profile {custom_style.name!r}; "
        f"no file at {custom_style} and no bundled profile found at {named}"
    )


def load_selected_style(
    project_root: Path, custom_style_path: Path | None = None
) -> TranslationStyle:
    return load_style(resolve_style_path(project_root, custom_style_path))


def snapshot_style(workspace_root: Path, style: TranslationStyle) -> OperationResult:
    destination = workspace_root / "style.yaml"
    atomic_write_yaml(destination, style)
    return OperationResult(
        status=OperationStatus.OK,
        reason="style snapshot saved",
        report_paths=["style.yaml"],
    )
