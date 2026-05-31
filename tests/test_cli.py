from pathlib import Path

from dich_truyen_agent.cli import build_parser, run_command
from dich_truyen_agent.models import OperationResult, OperationStatus
from dich_truyen_agent.storage import load_yaml_model


def test_help_lists_phase_one_commands(capsys) -> None:
    parser = build_parser()
    parser.print_help()
    output = capsys.readouterr().out
    for command in (
        "init-book",
        "inspect-workspace",
        "approve-checkpoint",
        "check-gate",
        "validate-style",
    ):
        assert command in output


def test_init_book_writes_compact_result(tmp_path: Path) -> None:
    args = build_parser().parse_args(
        [
            "init-book",
            "--books-root",
            str(tmp_path / "books"),
            "--slug",
            "demo",
            "--source-url",
            "https://example.com/book",
            "--title",
            "Demo",
        ]
    )

    result = run_command(args)
    result_path = tmp_path / "books" / "demo" / "reports" / "results" / "init-book.yaml"

    assert result.status is OperationStatus.OK
    assert load_yaml_model(result_path, OperationResult) == result
    serialized = result_path.read_text(encoding="utf-8")
    assert "chapter_body" not in serialized
    assert "verbose" not in serialized


def test_validate_style_is_compact(tmp_path: Path) -> None:
    style = tmp_path / "style.yaml"
    style.write_text(
        "name: custom\ndescription: Custom\nguidelines: []\n"
        "vocabulary: {}\ntone: formal\nexamples: []\n",
        encoding="utf-8",
    )
    args = build_parser().parse_args(["validate-style", "--style", str(style)])
    result = run_command(args)
    assert result.status is OperationStatus.OK
    assert result.reason == "style is valid: custom"


def test_skill_skeletons_are_honest_phase_one_contracts() -> None:
    skills_root = Path(".codex") / "skills"
    for skill_name in (
        "crawl-book",
        "translate-book",
        "check-translation",
        "export-book",
    ):
        text = (skills_root / skill_name / "SKILL.md").read_text(encoding="utf-8")
        assert f'name: "{skill_name}"' in text
        assert "description:" in text
        assert "short-description:" in text
        assert "books/<book-slug>/" in text
        assert "reports/results/" in text
        assert "checkpoint" in text.lower()
        assert "not implemented by Phase 1" in text
