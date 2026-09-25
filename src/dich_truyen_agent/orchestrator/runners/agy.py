from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
from typing import Any

from dich_truyen_agent.models import OperationResult, OperationStatus
from dich_truyen_agent.orchestrator.process import ProcessResult, run_process
from dich_truyen_agent.orchestrator.runners.base import HarnessRunResult


class AgyRunner:
    """Antigravity CLI harness runner adapter."""

    def __init__(
        self,
        *,
        executable: str = "agy",
        allow_permission_bypass: bool = False,
        available_models: list[str] | None = None,
        process_runner: Callable[..., ProcessResult] | None = None,
    ) -> None:
        self.executable = executable
        self.allow_permission_bypass = allow_permission_bypass
        self._available_models = available_models
        self._cached_available_models: list[str] | None = None
        self.process_runner = process_runner or run_process

    def build_command(
        self,
        agent_name: str | None,
        prompt: str,
        model: str | None = None,
        timeout_seconds: int = 1800,
        *,
        allow_permission_bypass: bool = False,
    ) -> list[str]:
        """Build command vector without a shell, preserving model, agent, and permission flags."""
        cmd = [self.executable]
        if agent_name:
            cmd.extend(["--agent", agent_name])
        if model:
            cmd.extend(["--model", model])
        if allow_permission_bypass or self.allow_permission_bypass:
            cmd.append("--dangerously-skip-permissions")
        cmd.extend(["--print", prompt, "--output-format", "json"])
        return cmd

    def get_available_models(self) -> list[str]:
        """Query target agy installation for available model slugs."""
        if self._available_models is not None:
            return list(self._available_models)
        if self._cached_available_models is not None:
            return list(self._cached_available_models)

        try:
            res = subprocess.run(
                [self.executable, "models"],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0:
                lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
                # Strip any potential table headers or decoration
                models = [m for m in lines if not m.startswith("-") and not m.lower().startswith("model")]
                self._cached_available_models = models
                return list(models)
        except Exception:
            pass
        return []

    def validate_model(self, model: str | None) -> OperationResult:
        """Validate an explicitly requested model slug against available models."""
        if model is None:
            return OperationResult(
                status=OperationStatus.OK,
                reason="no model specified; using CLI default",
            )

        available = self.get_available_models()
        if available and model not in available:
            return OperationResult(
                status=OperationStatus.BLOCKED,
                reason=f"requested model '{model}' is not available in agy models",
                data={"available_models": available, "requested_model": model},
            )

        return OperationResult(
            status=OperationStatus.OK,
            reason=f"model '{model}' is available",
            data={"model": model},
        )

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
        """Execute a phase prompt using supervised agy subprocess."""
        workspace = Path(workspace).resolve()
        now = datetime.now(UTC)

        # 1. Model preflight check
        if model is not None:
            validation = self.validate_model(model)
            if validation.status is OperationStatus.BLOCKED:
                log_dir = workspace / "reports" / "harness"
                log_dir.mkdir(parents=True, exist_ok=True)
                stdout_path = log_dir / f"{phase}_preflight_stdout.log"
                stderr_path = log_dir / f"{phase}_preflight_stderr.log"
                stderr_path.write_text(f"Preflight error: {validation.reason}\n", encoding="utf-8")
                stdout_path.write_text("", encoding="utf-8")
                return HarnessRunResult(
                    exit_code=1,
                    timed_out=False,
                    cancelled=False,
                    started_at=now,
                    ended_at=now,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    failure_detail=validation.reason,
                    argv=[],
                    data={"preflight_failed": True, "reason": validation.reason},
                )

        # 2. Select agent persona based on phase
        agent_name: str | None = None
        if phase in ("translate", "chapter_translation"):
            agent_name = "ag_translator"
        elif phase in ("metadata", "metadata_translation"):
            agent_name = "ag_metadata_translator"

        # 3. Build command vector
        argv = self.build_command(
            agent_name=agent_name,
            prompt=prompt,
            model=model,
            timeout_seconds=timeout_seconds,
        )

        # 4. Prepare log files
        timestamp_str = now.strftime("%Y%m%d_%H%M%S")
        log_dir = workspace / "reports" / "harness"
        log_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = log_dir / f"{phase}_{timestamp_str}_stdout.log"
        stderr_path = log_dir / f"{phase}_{timestamp_str}_stderr.log"

        # 5. Supervise process
        proc_result = self.process_runner(
            argv,
            cwd=workspace,
            timeout_seconds=timeout_seconds,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            on_event=on_event,
        )

        # 6. Extract CLI metadata from stdout if available
        parsed_data: dict[str, Any] = {}
        if stdout_path.is_file():
            try:
                content = stdout_path.read_text(encoding="utf-8").strip()
                if content.startswith("{") and content.endswith("}"):
                    parsed_data = json.loads(content)
            except Exception:
                pass

        return HarnessRunResult(
            exit_code=proc_result.exit_code,
            timed_out=proc_result.timed_out,
            cancelled=proc_result.cancelled,
            started_at=proc_result.started_at,
            ended_at=proc_result.finished_at,
            stdout_path=proc_result.stdout_path,
            stderr_path=proc_result.stderr_path,
            failure_detail=proc_result.failure_detail,
            argv=argv,
            data=parsed_data,
        )
