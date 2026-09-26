from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from dich_truyen_agent.cli import build_parser, run_orchestrate
from dich_truyen_agent.orchestrator.models import RunOutcome
from orchestrator_support import build_initialized_workspace


def test_cli_url_slug_style_limit_derives_workspace(tmp_path: Path) -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "orchestrate",
            "--url",
            "https://example.com/novel/index.html",
            "--slug",
            "derived-novel",
            "--style",
            "tien_hiep",
            "--limit",
            "3",
        ]
    )

    with patch("dich_truyen_agent.cli.BookOrchestrator") as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch.start.return_value = RunOutcome(
            status="completed",
            run_id="test-run-id",
            selected_span=("auto", "export"),
            current_phase="export",
            exit_code=0,
        )
        mock_orch_cls.return_value = mock_orch

        outcome = run_orchestrate(args)
        assert outcome.status == "completed"
        assert mock_orch.start.call_count == 1
        cfg = mock_orch.start.call_args[0][0]
        assert cfg.book_slug == "derived-novel"
        assert cfg.source_url == "https://example.com/novel/index.html"
        assert cfg.style == "tien_hiep"
        assert cfg.scope_limit == 3


def test_cli_rejects_mismatching_workspace_and_slug(tmp_path: Path) -> None:
    parser = build_parser()
    ws = tmp_path / "books" / "novel-a"
    args = parser.parse_args(
        [
            "orchestrate",
            "--workspace",
            str(ws),
            "--slug",
            "novel-b",
        ]
    )
    outcome = run_orchestrate(args)
    assert outcome.status == "blocked"
    assert outcome.exit_code == 3
    assert (
        "mismatch" in (outcome.error_message or "").lower()
        or "slug" in (outcome.error_message or "").lower()
    )


def test_cli_new_workspace_requires_style_and_url(tmp_path: Path) -> None:
    parser = build_parser()
    # Missing style
    args1 = parser.parse_args(
        [
            "orchestrate",
            "--slug",
            "new-novel-1",
            "--url",
            "https://example.com/novel/index.html",
        ]
    )
    outcome1 = run_orchestrate(args1)
    assert outcome1.status == "blocked"
    assert outcome1.exit_code == 3
    assert "style" in (outcome1.error_message or "").lower()

    # Missing url
    args2 = parser.parse_args(
        [
            "orchestrate",
            "--slug",
            "new-novel-2",
            "--style",
            "general",
        ]
    )
    outcome2 = run_orchestrate(args2)
    assert outcome2.status == "blocked"
    assert outcome2.exit_code == 3
    assert "url" in (outcome2.error_message or "").lower()


def test_cli_rejects_invalid_limit() -> None:
    parser = build_parser()
    args1 = parser.parse_args(
        [
            "orchestrate",
            "--slug",
            "limit-novel-1",
            "--url",
            "https://example.com/novel/index.html",
            "--style",
            "general",
            "--limit",
            "0",
        ]
    )
    outcome1 = run_orchestrate(args1)
    assert outcome1.status == "blocked"
    assert outcome1.exit_code == 3

    args2 = parser.parse_args(
        [
            "orchestrate",
            "--slug",
            "limit-novel-2",
            "--url",
            "https://example.com/novel/index.html",
            "--style",
            "general",
            "--limit",
            "-5",
        ]
    )
    outcome2 = run_orchestrate(args2)
    assert outcome2.status == "blocked"
    assert outcome2.exit_code == 3


def test_cli_existing_workspace_rejects_conflicting_url(tmp_path: Path) -> None:
    wf = build_initialized_workspace(tmp_path / "books" / "conflict-novel")
    parser = build_parser()
    args = parser.parse_args(
        [
            "orchestrate",
            "--workspace",
            str(wf.root),
            "--url",
            "https://different-source.com/novel.html",
        ]
    )
    outcome = run_orchestrate(args)
    assert outcome.status == "blocked"
    assert outcome.exit_code == 3
    assert "url" in (outcome.error_message or "").lower()


def test_cli_existing_workspace_rejects_title_or_author(tmp_path: Path) -> None:
    wf = build_initialized_workspace(tmp_path / "books" / "meta-novel")
    parser = build_parser()
    args = parser.parse_args(
        [
            "orchestrate",
            "--workspace",
            str(wf.root),
            "--title",
            "Attempted New Title",
        ]
    )
    outcome = run_orchestrate(args)
    assert outcome.status == "blocked"
    assert outcome.exit_code == 3
    assert "title" in (outcome.error_message or "").lower()


def test_cli_resume_rejects_creation_options_and_overrides(tmp_path: Path) -> None:
    wf = build_initialized_workspace(tmp_path / "books" / "resume-reject-novel")
    parser = build_parser()

    # --resume combined with --url
    args1 = parser.parse_args(
        [
            "orchestrate",
            "--workspace",
            str(wf.root),
            "--resume",
            "--url",
            "https://example.com/novel.html",
        ]
    )
    outcome1 = run_orchestrate(args1)
    assert outcome1.status == "blocked"
    assert outcome1.exit_code == 3

    # --resume combined with --limit
    args2 = parser.parse_args(
        [
            "orchestrate",
            "--workspace",
            str(wf.root),
            "--resume",
            "--limit",
            "5",
        ]
    )
    outcome2 = run_orchestrate(args2)
    assert outcome2.status == "blocked"
    assert outcome2.exit_code == 3

    # --resume combined with --timeout override
    args3 = parser.parse_args(
        [
            "orchestrate",
            "--workspace",
            str(wf.root),
            "--resume",
            "--timeout",
            "999",
        ]
    )
    outcome3 = run_orchestrate(args3)
    assert outcome3.status == "blocked"
    assert outcome3.exit_code == 3


def test_cli_yes_flag_maps_to_auto_approve() -> None:
    parser = build_parser()
    args1 = parser.parse_args(
        [
            "orchestrate",
            "--slug",
            "novel-y",
            "--url",
            "https://example.com/novel/index.html",
            "--style",
            "general",
            "-y",
        ]
    )
    assert args1.auto_approve is True

    args2 = parser.parse_args(
        [
            "orchestrate",
            "--slug",
            "novel-yes",
            "--url",
            "https://example.com/novel/index.html",
            "--style",
            "general",
            "--yes",
        ]
    )
    assert args2.auto_approve is True


def test_cli_tty_approval_prompt_approve_and_reject(tmp_path: Path) -> None:
    wf = build_initialized_workspace(tmp_path / "books" / "prompt-novel")
    parser = build_parser()
    args = parser.parse_args(
        [
            "orchestrate",
            "--workspace",
            str(wf.root),
        ]
    )

    paused_outcome = RunOutcome(
        status="paused",
        run_id="run-123",
        selected_span=("auto", "export"),
        current_phase="crawl_decision",
        pending_approval="crawl_approval",
        approval_report_path="reports/crawl.yaml",
        approval_report_hash="hash-abc",
        exit_code=2,
    )
    completed_outcome = RunOutcome(
        status="completed",
        run_id="run-123",
        selected_span=("auto", "export"),
        current_phase="export",
        exit_code=0,
    )

    with (
        patch("dich_truyen_agent.cli.BookOrchestrator") as mock_orch_cls,
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("builtins.input", side_effect=["y"]),
    ):
        mock_orch = MagicMock()
        mock_orch.start.return_value = paused_outcome
        mock_orch.resume.return_value = completed_outcome
        mock_orch_cls.return_value = mock_orch

        outcome = run_orchestrate(args)
        assert outcome.status == "completed"
        assert mock_orch.resume.call_count == 1
        assert mock_orch.resume.call_args[1]["decision"] == "approve"

    # Test reject 'n'
    rejected_outcome = RunOutcome(
        status="blocked",
        run_id="run-123",
        selected_span=("auto", "export"),
        current_phase="crawl_decision",
        exit_code=3,
    )
    with (
        patch("dich_truyen_agent.cli.BookOrchestrator") as mock_orch_cls,
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("builtins.input", side_effect=["n"]),
    ):
        mock_orch = MagicMock()
        mock_orch.start.return_value = paused_outcome
        mock_orch.resume.return_value = rejected_outcome
        mock_orch_cls.return_value = mock_orch

        outcome = run_orchestrate(args)
        assert outcome.status == "blocked"
        assert mock_orch.resume.call_count == 1
        assert mock_orch.resume.call_args[1]["decision"] == "reject"


def test_cli_tty_blank_input_defers_with_exit_two(tmp_path: Path) -> None:
    wf = build_initialized_workspace(tmp_path / "books" / "defer-novel")
    parser = build_parser()
    args = parser.parse_args(
        [
            "orchestrate",
            "--workspace",
            str(wf.root),
        ]
    )

    paused_outcome = RunOutcome(
        status="paused",
        run_id="run-123",
        selected_span=("auto", "export"),
        current_phase="crawl_decision",
        pending_approval="crawl_approval",
        approval_report_path="reports/crawl.yaml",
        approval_report_hash="hash-abc",
        exit_code=2,
    )

    with (
        patch("dich_truyen_agent.cli.BookOrchestrator") as mock_orch_cls,
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("builtins.input", side_effect=[""]),
    ):
        mock_orch = MagicMock()
        mock_orch.start.return_value = paused_outcome
        mock_orch_cls.return_value = mock_orch

        outcome = run_orchestrate(args)
        assert outcome.status == "paused"
        assert outcome.exit_code == 2
        assert mock_orch.resume.call_count == 0


def test_cli_non_tty_and_json_never_prompt(tmp_path: Path) -> None:
    wf = build_initialized_workspace(tmp_path / "books" / "non-tty-novel")
    parser = build_parser()
    paused_outcome = RunOutcome(
        status="paused",
        run_id="run-123",
        selected_span=("auto", "export"),
        current_phase="crawl_decision",
        pending_approval="crawl_approval",
        approval_report_path="reports/crawl.yaml",
        approval_report_hash="hash-abc",
        exit_code=2,
    )

    # non-TTY stdin
    args = parser.parse_args(["orchestrate", "--workspace", str(wf.root)])
    with (
        patch("dich_truyen_agent.cli.BookOrchestrator") as mock_orch_cls,
        patch("sys.stdin.isatty", return_value=False),
        patch("sys.stdout.isatty", return_value=True),
        patch("builtins.input") as mock_input,
    ):
        mock_orch = MagicMock()
        mock_orch.start.return_value = paused_outcome
        mock_orch_cls.return_value = mock_orch

        outcome = run_orchestrate(args)
        assert outcome.status == "paused"
        assert mock_input.call_count == 0

    # --json flag
    args_json = parser.parse_args(
        ["orchestrate", "--workspace", str(wf.root), "--json"]
    )
    with (
        patch("dich_truyen_agent.cli.BookOrchestrator") as mock_orch_cls,
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("builtins.input") as mock_input,
    ):
        mock_orch = MagicMock()
        mock_orch.start.return_value = paused_outcome
        mock_orch_cls.return_value = mock_orch

        outcome = run_orchestrate(args_json)
        assert outcome.status == "paused"
        assert mock_input.call_count == 0


def test_cli_warning_under_yes_defers_without_prompt(tmp_path: Path) -> None:
    wf = build_initialized_workspace(tmp_path / "books" / "yes-warning-novel")
    parser = build_parser()
    args = parser.parse_args(
        [
            "orchestrate",
            "--workspace",
            str(wf.root),
            "--yes",
        ]
    )

    paused_outcome = RunOutcome(
        status="paused",
        run_id="run-123",
        selected_span=("auto", "export"),
        current_phase="crawl_decision",
        pending_approval="crawl_approval",
        approval_report_path="reports/crawl.yaml",
        approval_report_hash="hash-abc",
        exit_code=2,
    )

    with (
        patch("dich_truyen_agent.cli.BookOrchestrator") as mock_orch_cls,
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("builtins.input") as mock_input,
    ):
        mock_orch = MagicMock()
        mock_orch.start.return_value = paused_outcome
        mock_orch_cls.return_value = mock_orch

        outcome = run_orchestrate(args)
        assert outcome.status == "paused"
        assert outcome.exit_code == 2
        assert mock_input.call_count == 0
        assert mock_orch.resume.call_count == 0


def test_cli_repeated_interrupt_halts_to_prevent_infinite_loop(tmp_path: Path) -> None:
    wf = build_initialized_workspace(tmp_path / "books" / "loop-novel")
    parser = build_parser()
    args = parser.parse_args(
        [
            "orchestrate",
            "--workspace",
            str(wf.root),
        ]
    )

    paused_outcome = RunOutcome(
        status="paused",
        run_id="run-loop",
        selected_span=("auto", "export"),
        current_phase="crawl_decision",
        pending_approval="crawl_approval",
        approval_report_path="reports/crawl.yaml",
        approval_report_hash="hash-same",
        exit_code=2,
    )

    with (
        patch("dich_truyen_agent.cli.BookOrchestrator") as mock_orch_cls,
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("builtins.input", side_effect=["y", "y"]),
    ):
        mock_orch = MagicMock()
        # Resume returns the exact same paused outcome
        mock_orch.start.return_value = paused_outcome
        mock_orch.resume.return_value = paused_outcome
        mock_orch_cls.return_value = mock_orch

        outcome = run_orchestrate(args)
        assert outcome.status == "paused"
        # Should only have called resume once before detecting the repeat
        assert mock_orch.resume.call_count == 1


def test_cli_two_distinct_gates_interactive_approval(tmp_path: Path) -> None:
    wf = build_initialized_workspace(tmp_path / "books" / "two-gates-novel")
    parser = build_parser()
    args = parser.parse_args(
        [
            "orchestrate",
            "--workspace",
            str(wf.root),
        ]
    )

    gate1_outcome = RunOutcome(
        status="paused",
        run_id="run-two-gates",
        selected_span=("auto", "export"),
        current_phase="crawl_decision",
        pending_approval="crawl_approval",
        approval_report_path="reports/crawl.yaml",
        approval_report_hash="hash-crawl",
        exit_code=2,
    )
    gate2_outcome = RunOutcome(
        status="paused",
        run_id="run-two-gates",
        selected_span=("auto", "export"),
        current_phase="qa_decision",
        pending_approval="qa_approval",
        approval_report_path="reports/qa-report.yaml",
        approval_report_hash="hash-qa",
        exit_code=2,
    )
    final_completed = RunOutcome(
        status="completed",
        run_id="run-two-gates",
        selected_span=("auto", "export"),
        current_phase="export",
        exit_code=0,
    )

    with (
        patch("dich_truyen_agent.cli.BookOrchestrator") as mock_orch_cls,
        patch("sys.stdin.isatty", return_value=True),
        patch("sys.stdout.isatty", return_value=True),
        patch("builtins.input", side_effect=["y", "y"]),
    ):
        mock_orch = MagicMock()
        mock_orch.start.return_value = gate1_outcome
        mock_orch.resume.side_effect = [gate2_outcome, final_completed]
        mock_orch_cls.return_value = mock_orch

        outcome = run_orchestrate(args)
        assert outcome.status == "completed"
        assert mock_orch.resume.call_count == 2
