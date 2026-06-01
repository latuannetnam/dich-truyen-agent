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


def test_init_book_resume_uses_workspace_style_snapshot(tmp_path: Path) -> None:
    style = tmp_path / "style.yaml"
    style.write_text(
        "name: custom\ndescription: Custom\nguidelines: []\n"
        "vocabulary: {}\ntone: formal\nexamples: []\n",
        encoding="utf-8",
    )
    command = [
        "init-book",
        "--books-root",
        str(tmp_path / "books"),
        "--slug",
        "demo",
        "--source-url",
        "https://example.com/book",
        "--title",
        "Demo",
        "--style",
        str(style),
    ]
    assert run_command(build_parser().parse_args(command)).status is OperationStatus.OK
    style.unlink()

    result = run_command(build_parser().parse_args([*command, "--resume"]))

    assert result.status is OperationStatus.OK
    assert result.reason == "workspace is valid"


def test_skill_skeletons_are_honest_phase_one_contracts() -> None:
    skills_root = Path(".agent") / "skills"
    for skill_name in (
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


def test_cli_help_lists_phase_two_commands(capsys) -> None:
    parser = build_parser()
    parser.print_help()
    output = capsys.readouterr().out
    for command in (
        "crawl-book",
        "validate-crawl-profile",
        "promote-crawl-profile",
        "approve-crawl",
    ):
        assert command in output


def test_cli_validate_crawl_profile(tmp_path: Path) -> None:
    # Setup dummy workspace
    workspace = tmp_path / "books" / "demo-book"
    workspace.mkdir(parents=True)
    (workspace / "reports" / "results").mkdir(parents=True)
    
    # Write metadata
    from dich_truyen_agent.models import BookMetadata
    from dich_truyen_agent.storage import atomic_write_yaml
    metadata = BookMetadata(
        book_slug="demo-book",
        source_url="https://www.piaotia.com/html/8/8717/index.html",
        title="Demo Book",
    )
    atomic_write_yaml(workspace / "book.yaml", metadata)
    
    # Write crawl profile
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        "schema_version: 1\n"
        "domain: www.piaotia.com\n"
        "index:\n"
        "  chapter_link_selector: '.chapters a'\n"
        "  pagination_selector: null\n"
        "  list_section_selectors: []\n"
        "chapter:\n"
        "  title_selector: h1\n"
        "  content_selector: '#content'\n"
        "  remove_selectors: []\n"
        "encoding:\n"
        "  index: gbk\n"
        "  chapter: gbk\n"
        "validation:\n"
        "  min_chapter_characters: 10\n",
        encoding="utf-8"
    )
    
    args = build_parser().parse_args([
        "validate-crawl-profile",
        "--workspace",
        str(workspace),
        "--profile",
        str(profile_path),
    ])
    res = run_command(args)
    assert res.status is OperationStatus.OK
    assert "is valid" in res.reason
