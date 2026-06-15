from pathlib import Path

import pytest
from pydantic import ValidationError
from yaml import YAMLError

from dich_truyen_agent.models import TranslationStyle
from dich_truyen_agent.storage import load_yaml_model
from dich_truyen_agent.styles import load_selected_style, load_style, snapshot_style


def _write_profile(project_root: Path, name: str) -> None:
    template = project_root / "templates" / "styles" / f"{name}.yaml"
    template.parent.mkdir(parents=True, exist_ok=True)
    template.write_text(
        f"name: {name}\ndescription: {name}\nguidelines: []\n"
        "vocabulary: {}\ntone: neutral\nexamples: []\n",
        encoding="utf-8",
    )


def test_default_style_loads_from_bundled_template() -> None:
    style = load_selected_style(Path.cwd())
    assert style.name == "general"


def test_default_style_is_general(tmp_path: Path) -> None:
    _write_profile(tmp_path, "general")
    style = load_selected_style(tmp_path)
    assert style.name == "general"


def test_style_resolves_bare_profile_name(tmp_path: Path) -> None:
    _write_profile(tmp_path, "mat_the")
    style = load_selected_style(tmp_path, Path("mat_the"))
    assert style.name == "mat_the"


def test_style_resolves_explicit_existing_path(tmp_path: Path) -> None:
    source = tmp_path / "custom.yaml"
    source.write_text(
        "name: custom\ndescription: c\nguidelines: []\n"
        "vocabulary: {}\ntone: neutral\nexamples: []\n",
        encoding="utf-8",
    )
    style = load_selected_style(tmp_path, source)
    assert style.name == "custom"


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


def test_style_resolution_raises_for_unknown_profile(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown style profile"):
        load_selected_style(tmp_path, Path("does_not_exist"))


def test_bundled_general_profile_is_valid() -> None:
    style = load_selected_style(Path.cwd())
    assert style.name == "general"
    assert style.genre_register
    assert style.emotion_guidelines
    assert style.rhythm_guidelines


def test_mat_the_profile_is_valid_and_modern() -> None:
    style = load_style(Path.cwd() / "templates" / "styles" / "mat_the.yaml")
    assert style.name == "mat_the"
    assert "hiện đại" in style.genre_register or "modern" in style.genre_register
    assert style.emotion_guidelines
    assert style.rhythm_guidelines


def test_do_thi_profile_is_valid() -> None:
    style = load_style(Path.cwd() / "templates" / "styles" / "do_thi.yaml")
    assert style.name == "do_thi"
    assert style.genre_register
    assert style.emotion_guidelines
    assert style.rhythm_guidelines


def test_tien_hiep_profile_has_register_and_craft() -> None:
    style = load_style(Path.cwd() / "templates" / "styles" / "tien_hiep.yaml")
    assert style.name == "tien_hiep"
    assert style.genre_register
    assert style.emotion_guidelines
    assert style.voice_guidelines
    assert style.rhythm_guidelines
    # existing archaic content preserved
    assert style.tone == "archaic"
    assert "修炼" in style.vocabulary


def test_snapshot_isolated_from_template_changes(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    template = project_root / "templates" / "styles" / "general.yaml"
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
