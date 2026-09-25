from __future__ import annotations

from pathlib import Path

import pytest

from dich_truyen_agent.orchestrator.attempts import AttemptJournal


def test_attempt_budget_survives_reopen(tmp_path: Path) -> None:
    journal_path = tmp_path / "attempts.json"
    journal = AttemptJournal(journal_path)
    assert journal.reserve("run-a", 7, limit=3) == 1
    assert AttemptJournal(journal_path).reserve("run-a", 7, limit=3) == 2
    assert AttemptJournal(journal_path).reserve("run-a", 7, limit=3) == 3

    # 4th attempt exceeds limit
    with pytest.raises(RuntimeError, match="attempt limit 3 reached"):
        AttemptJournal(journal_path).reserve("run-a", 7, limit=3)


def test_per_run_budget_isolation(tmp_path: Path) -> None:
    journal = AttemptJournal(tmp_path / "attempts.json")

    # run-a exhausts chapter 5 budget
    assert journal.reserve("run-a", 5, limit=2) == 1
    assert journal.reserve("run-a", 5, limit=2) == 2
    with pytest.raises(RuntimeError):
        journal.reserve("run-a", 5, limit=2)

    # run-b gets a fresh budget for chapter 5
    assert journal.reserve("run-b", 5, limit=2) == 1
    assert journal.get_attempts("run-b", 5) == 1
    assert journal.get_attempts("run-a", 5) == 2


def test_profile_repair_attempt_tracking(tmp_path: Path) -> None:
    journal = AttemptJournal(tmp_path / "attempts.json")

    assert journal.reserve("run-x", "profile_repair", limit=3) == 1
    assert journal.reserve("run-x", "profile_repair", limit=3) == 2
    assert journal.get_attempts("run-x", "profile_repair") == 2
