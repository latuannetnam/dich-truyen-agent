from pathlib import Path

import pytest
from pydantic import ValidationError
from yaml import YAMLError

from dich_truyen_agent.models import TranslationStyle
from dich_truyen_agent.storage import load_yaml_model
from dich_truyen_agent.styles import load_selected_style, load_style, snapshot_style


def test_default_style_loads_from_bundled_template() -> None:
    style = load_selected_style(Path.cwd())
    assert style.name == "tien_hiep"


def test_custom_style_snapshots_atomically(tmp_path: Path) -> None:
    source = tmp_path / "custom.yaml"
    source.write_text(
        "name: custom\ndescription: Custom\nguidelines: []\n"
        "vocabulary: {}\ntone: formal\nexamples: []\n",
        encoding="utf-8",
    )
    workspace_root = tmp_path / "book"
    workspace_root.mkdir()
    style = load_style(source)

    result = snapshot_style(workspace_root, style)

    assert result.reason == "style snapshot saved"
    assert load_yaml_model(workspace_root / "style.yaml", TranslationStyle) == style


@pytest.mark.parametrize(
    "content",
    [
        "!!python/object:builtins.object {}\n",
        "name: broken: yaml\n",
        "name: incomplete\n",
    ],
)
def test_style_loader_rejects_unsafe_malformed_or_invalid_yaml(
    tmp_path: Path, content: str
) -> None:
    source = tmp_path / "style.yaml"
    source.write_text(content, encoding="utf-8")
    with pytest.raises((YAMLError, ValidationError)):
        load_style(source)


def test_style_loads_without_craft_fields_backward_compat(tmp_path: Path) -> None:
    source = tmp_path / "old.yaml"
    source.write_text(
        "name: old\ndescription: Old\nguidelines: []\n"
        "vocabulary: {}\ntone: formal\nexamples: []\n",
        encoding="utf-8",
    )
    style = load_style(source)
    assert style.genre_register == ""
    assert style.emotion_guidelines == []
    assert style.voice_guidelines == []
    assert style.rhythm_guidelines == []


def test_style_loads_with_craft_fields(tmp_path: Path) -> None:
    source = tmp_path / "new.yaml"
    source.write_text(
        "name: new\ndescription: New\nguidelines: []\n"
        "vocabulary: {}\ntone: modern\nexamples: []\n"
        "register: modern-colloquial\n"
        "emotion_guidelines:\n- Truyen tai cam xuc\n"
        "voice_guidelines:\n- Giong noi rieng\n"
        "rhythm_guidelines:\n- Cau ngan trong canh hanh dong\n",
        encoding="utf-8",
    )
    style = load_style(source)
    assert style.genre_register == "modern-colloquial"
    assert style.emotion_guidelines == ["Truyen tai cam xuc"]
    assert style.voice_guidelines == ["Giong noi rieng"]
    assert style.rhythm_guidelines == ["Cau ngan trong canh hanh dong"]


def test_snapshot_isolated_from_template_changes(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    template = project_root / "templates" / "styles" / "tien_hiep.yaml"
    template.parent.mkdir(parents=True)
    template.write_text(
        "name: initial\ndescription: Initial\nguidelines: []\n"
        "vocabulary: {}\ntone: formal\nexamples: []\n",
        encoding="utf-8",
    )
    workspace_root = tmp_path / "book"
    workspace_root.mkdir()
    snapshot_style(workspace_root, load_selected_style(project_root))
    template.write_text(
        "name: changed\ndescription: Changed\nguidelines: []\n"
        "vocabulary: {}\ntone: formal\nexamples: []\n",
        encoding="utf-8",
    )

    snapshot = load_yaml_model(workspace_root / "style.yaml", TranslationStyle)
    assert snapshot.name == "initial"
