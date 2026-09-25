from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dich_truyen_agent.orchestrator.runners.base import HarnessRunResult


@dataclass
class MockCall:
    phase: str
    workspace: Path
    prompt: str
    model: str | None
    timeout_seconds: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class MockRunner:
    """Scriptable mock harness runner for deterministic offline unit and integration tests."""

    def __init__(
        self,
        *,
        scripted_outcomes: dict[str, HarnessRunResult] | list[HarnessRunResult] | None = None,
        side_effects: list[Callable[[Path, str, dict[str, Any]], None]] | None = None,
    ) -> None:
        self.calls: list[MockCall] = []
        self._scripted_outcomes = scripted_outcomes
        self._side_effects = side_effects or []
        self._outcome_index = 0

    def add_side_effect(self, fn: Callable[[Path, str, dict[str, Any]], None]) -> None:
        self._side_effects.append(fn)

    def run_phase(
        self,
        *,
        phase: str,
        workspace: Path,
        prompt: str,
        model: str | None = None,
        timeout_seconds: int = 1800,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> HarnessRunResult:
        workspace_path = Path(workspace).resolve()
        now = datetime.now(UTC)

        call = MockCall(
            phase=phase,
            workspace=workspace_path,
            prompt=prompt,
            model=model,
            timeout_seconds=timeout_seconds,
            timestamp=now,
        )
        self.calls.append(call)

        # Trigger on_event started
        if on_event:
            try:
                on_event({"event": "started", "phase": phase, "prompt": prompt})
            except Exception:
                pass

        # Execute side effects
        context = {"phase": phase, "model": model, "timeout_seconds": timeout_seconds}
        for effect in self._side_effects:
            effect(workspace_path, prompt, context)

        # Log paths
        log_dir = workspace_path / "reports" / "harness"
        log_dir.mkdir(parents=True, exist_ok=True)
        stdout_file = log_dir / f"mock_{phase}_stdout.log"
        stderr_file = log_dir / f"mock_{phase}_stderr.log"
        stdout_file.write_text(f"Mock execution for phase {phase}\n", encoding="utf-8")
        stderr_file.write_text("", encoding="utf-8")

        # Determine outcome
        outcome: HarnessRunResult
        if isinstance(self._scripted_outcomes, dict) and phase in self._scripted_outcomes:
            outcome = self._scripted_outcomes[phase]
        elif isinstance(self._scripted_outcomes, list) and self._outcome_index < len(self._scripted_outcomes):
            outcome = self._scripted_outcomes[self._outcome_index]
            self._outcome_index += 1
        else:
            outcome = HarnessRunResult(
                exit_code=0,
                timed_out=False,
                cancelled=False,
                started_at=now,
                ended_at=now,
                stdout_path=stdout_file,
                stderr_path=stderr_file,
                argv=["mock", phase],
            )

        if on_event:
            try:
                on_event({
                    "event": "finished",
                    "phase": phase,
                    "exit_code": outcome.exit_code,
                    "timed_out": outcome.timed_out,
                })
            except Exception:
                pass

        return outcome
