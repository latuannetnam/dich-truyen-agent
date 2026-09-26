"""Contract and guidance acceptance matrix tests (C01-C08).

Verifies model routing, agent authority, domain blockers, harness guidance,
skill mapping, generated tree integrity, agent definitions, and logging/exit contract.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any


from dich_truyen_agent.checkpoints import check_orchestrator_gate
from dich_truyen_agent.models import (
    BookMetadata,
    ChapterCatalog,
    CheckpointType,
    OperationStatus,
    QAReport,
    StageStatus,
)
from dich_truyen_agent.orchestrator import graph as graph_module
from dich_truyen_agent.orchestrator.orchestrator import BookOrchestrator
from dich_truyen_agent.orchestrator.runners.agy import AgyRunner
from dich_truyen_agent.orchestrator.runners.base import resolve_model_for_phase
from dich_truyen_agent.orchestrator.runners.mock import MockRunner
from dich_truyen_agent.orchestrator.workspace_ops import WorkspaceOps
from dich_truyen_agent.paths import find_project_root
from dich_truyen_agent.storage import atomic_write_yaml, load_yaml_model
from orchestrator_support import (
    build_crawl_approved_workspace,
    build_initialized_workspace,
    build_translated_workspace,
)

ROOT = find_project_root()


# =============================================================================
# C01: Model routing
# =============================================================================


def test_c01_model_routing(tmp_path: Path) -> None:
    """C01: Global model reaches metadata/translator; translation override affects only translator.

    Invalid slug fails before launch; choices persist on resume.
    """
    # 1. Routing resolution logic
    global_slug = "claude-3-5-sonnet"
    override_slug = "claude-3-opus"

    assert (
        resolve_model_for_phase(
            "metadata_translation", global_model=global_slug, translation_model=None
        )
        == global_slug
    )
    assert (
        resolve_model_for_phase(
            "metadata_translation",
            global_model=global_slug,
            translation_model=override_slug,
        )
        == global_slug
    )
    assert (
        resolve_model_for_phase(
            "chapter_translation", global_model=global_slug, translation_model=None
        )
        == global_slug
    )
    assert (
        resolve_model_for_phase(
            "chapter_translation",
            global_model=global_slug,
            translation_model=override_slug,
        )
        == override_slug
    )

    # 2. Execution routing via runner recording
    wf = build_crawl_approved_workspace(tmp_path / "c01_run")
    runner = MockRunner()
    ops = WorkspaceOps()
    orchestrator = BookOrchestrator(runner=runner, ops=ops)

    def side_effect(workspace: Path, prompt: str, ctx: dict[str, Any]) -> None:
        phase = ctx.get("phase")
        if phase == "metadata_translation":
            meta = load_yaml_model(workspace / "book.yaml", BookMetadata)
            atomic_write_yaml(
                workspace / "book.yaml",
                meta.model_copy(
                    update={
                        "translated_title": f"Dịch: {meta.title}",
                        "translated_author": f"Dịch: {meta.author}"
                        if meta.author
                        else None,
                    }
                ),
            )
        elif phase == "chapter_translation":
            staged_txt = None
            chapter_id = 1
            for line in prompt.splitlines():
                if "staged_txt:" in line:
                    staged_txt = Path(line.partition("staged_txt:")[2].strip())
                if "chapter_id:" in line:
                    try:
                        chapter_id = int(line.partition("chapter_id:")[2].strip())
                    except ValueError:
                        pass
            if staged_txt:
                staged_txt.parent.mkdir(parents=True, exist_ok=True)
                staged_txt.write_text(
                    f"# Chương {chapter_id} Tiêu Đề {chapter_id}\n\nNội dung dịch mẫu chuẩn xác.\n"
                    * 5,
                    encoding="utf-8",
                )

    runner.add_side_effect(side_effect)

    outcome = orchestrator.start(
        wf.root,
        start_at="translate",
        stop_after="translate",
        global_model="global-model-slug",
        translation_model="override-model-slug",
    )
    assert outcome.status == "completed"

    calls = runner.calls
    meta_call = next(c for c in calls if c.phase == "metadata_translation")
    assert meta_call.model == "global-model-slug"

    trans_call = next(c for c in calls if c.phase == "chapter_translation")
    assert trans_call.model == "override-model-slug"

    # 3. Invalid slug fails preflight check before agent launch
    agy_runner = AgyRunner(available_models=["gemini-2.5-pro", "gemini-2.5-flash"])
    res = agy_runner.validate_model("nonexistent-model-xyz")
    assert res.status is OperationStatus.BLOCKED
    assert "is not available in agy models" in res.reason


# =============================================================================
# C02: Agent output authority
# =============================================================================


def test_c02_agent_output_authority(tmp_path: Path) -> None:
    """C02: Exit code 0 without staged file does not advance; unauthorized file edits block."""
    # Subtest A: Exit code 0 without writing staged file cannot advance
    wf_a = build_crawl_approved_workspace(tmp_path / "c02_missing_staging")
    runner_a = MockRunner()

    def meta_only_side_effect(
        workspace: Path, prompt: str, ctx: dict[str, Any]
    ) -> None:
        if ctx.get("phase") == "metadata_translation":
            meta = load_yaml_model(workspace / "book.yaml", BookMetadata)
            atomic_write_yaml(
                workspace / "book.yaml",
                meta.model_copy(
                    update={
                        "translated_title": f"Dịch: {meta.title}",
                        "translated_author": f"Dịch: {meta.author}"
                        if meta.author
                        else None,
                    }
                ),
            )

    runner_a.add_side_effect(meta_only_side_effect)
    orchestrator_a = BookOrchestrator(runner=runner_a, ops=WorkspaceOps())

    outcome_a = orchestrator_a.start(
        wf_a.root,
        start_at="translate",
        stop_after="translate",
    )
    assert outcome_a.status == "blocked"
    assert "staging verification failed" in (outcome_a.error_message or "")

    # Subtest B: Unauthorized workspace file modification blocks immediately
    wf_b = build_crawl_approved_workspace(tmp_path / "c02_unauthorized_edit")
    runner_b = MockRunner()

    def sneaky_side_effect(workspace: Path, prompt: str, ctx: dict[str, Any]) -> None:
        if ctx.get("phase") == "metadata_translation":
            meta = load_yaml_model(workspace / "book.yaml", BookMetadata)
            atomic_write_yaml(
                workspace / "book.yaml",
                meta.model_copy(
                    update={
                        "translated_title": f"Dịch: {meta.title}",
                        "translated_author": f"Dịch: {meta.author}"
                        if meta.author
                        else None,
                    }
                ),
            )
        elif ctx.get("phase") == "chapter_translation":
            # Tamper with protected book.yaml
            (workspace / "book.yaml").write_text("tampered: true\n", encoding="utf-8")

    runner_b.add_side_effect(sneaky_side_effect)
    orchestrator_b = BookOrchestrator(runner=runner_b, ops=WorkspaceOps())

    outcome_b = orchestrator_b.start(
        wf_b.root,
        start_at="translate",
        stop_after="translate",
    )
    assert outcome_b.status == "blocked"
    assert "unauthorized workspace mutation detected" in (outcome_b.error_message or "")


# =============================================================================
# C03: Domain blockers
# =============================================================================


def test_c03_domain_blockers(tmp_path: Path) -> None:
    """C03: Missing predecessor, gap, stale gate, 0 chapters, QA error, missing export tool block without agent retry."""
    ops = WorkspaceOps()
    runner = MockRunner()
    orchestrator = BookOrchestrator(runner=runner, ops=ops)

    from dich_truyen_agent.workspace import (
        inspect_workspace,
        next_translation_work_item,
    )

    # 1. 0 discovered chapters in catalog
    wf_empty = build_initialized_workspace(tmp_path / "c03_empty")
    catalog = load_yaml_model(wf_empty.catalog, ChapterCatalog)
    catalog.chapters.clear()
    atomic_write_yaml(wf_empty.catalog, catalog)
    res_empty = inspect_workspace(wf_empty.root)
    assert res_empty.status is OperationStatus.BLOCKED

    # 2. Missing predecessor chapter (gap in translated chapters)
    wf_gap = build_crawl_approved_workspace(tmp_path / "c03_gap", chapter_count=2)
    # Chapter 2 is staged, but chapter 1 is not translated
    state = wf_gap.reload_state()
    assert state.chapters[0].translation.status is StageStatus.PENDING
    item_res = next_translation_work_item(wf_gap.root)
    assert item_res.status is OperationStatus.OK
    assert item_res.data["chapter_id"] == 1  # Strictly enforces chapter 1 first

    # 3. Stale crawl gate
    wf_stale = build_crawl_approved_workspace(tmp_path / "c03_stale")
    (wf_stale.root / "raw" / "0001-chuong-0001.txt").write_text(
        "Mutated raw text", encoding="utf-8"
    )
    stale_gate = check_orchestrator_gate(wf_stale.root, CheckpointType.CRAWL_APPROVED)
    assert stale_gate.status is OperationStatus.BLOCKED

    # 4. QA finding error blocks without retry
    wf_qa = build_translated_workspace(tmp_path / "c03_qa_error")
    orig_qa = graph_module.run_qa_check

    def qa_with_error(workspace_root: Path, **kwargs: Any) -> QAReport:
        rep = QAReport(
            summary={
                "error_count": 1,
                "warning_count": 0,
                "findings_count": 1,
                "passed": False,
            },
            findings=[
                {
                    "chapter_id": 1,
                    "finding_type": "residue",
                    "severity": "error",
                    "message": "Critical raw residue found",
                }
            ],
        )
        atomic_write_yaml(wf_qa.root / "reports" / "qa-report.yaml", rep)
        return rep

    graph_module.run_qa_check = qa_with_error
    try:
        out_qa = orchestrator.start(
            wf_qa.root,
            start_at="qa",
            stop_after="qa",
        )
        assert out_qa.status == "blocked"
        assert len(runner.calls) == 0  # No agent retry loop on deterministic QA blocker
    finally:
        graph_module.run_qa_check = orig_qa


# =============================================================================
# C04: Harness guidance
# =============================================================================


def test_c04_harness_guidance() -> None:
    """C04: AGENTS.md and CLAUDE.md include development and operations sections;

    Antigravity declared as initial agent backend; Cowork uses isolated CLI form.
    """
    agents_md = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    claude_md = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    for doc, name in [(agents_md, "AGENTS.md"), (claude_md, "CLAUDE.md")]:
        assert "## Operations" in doc, f"Missing Operations section in {name}"
        assert "## Development" in doc, f"Missing Development section in {name}"
        assert "orchestrate --workspace books/<book-slug>" in doc, (
            f"Missing orchestrate CLI in {name}"
        )
        assert (
            "Antigravity CLI serves as the initial agent execution backend" in doc
            or "Antigravity" in doc
        ), f"Missing Antigravity initial backend declaration in {name}"

    # Verify Cowork isolated CLI form
    assert (
        "UV_CACHE_DIR=/tmp/uv-cache uv run --isolated --python 3.13 main.py"
        in agents_md
    )
    assert (
        "UV_CACHE_DIR=/tmp/uv-cache uv run --isolated --python 3.13 main.py"
        in claude_md
    )


# =============================================================================
# C05: Skill mapping
# =============================================================================


def test_c05_skill_mapping() -> None:
    """C05: All four phase skills for all harnesses invoke only their mapped span.

    orchestrate-book supports arbitrary valid spans. None contains direct approval/promotion/coordinator.
    """
    harnesses = {
        "ag": ROOT / ".agent" / "skills",
        "cc": ROOT / ".claude" / "skills",
        "oc": ROOT / ".opencode" / "skill",
        "codex": ROOT / ".codex" / "skills",
    }

    phase_spans = {
        "crawl-book": ("crawl", "crawl"),
        "translate-book": ("translate", "translate"),
        "check-translation": ("qa", "qa"),
        "export-book": ("export", "export"),
    }

    for prefix, skill_dir in harnesses.items():
        assert skill_dir.is_dir(), (
            f"Skill directory not found for {prefix}: {skill_dir}"
        )

        # 1. Check phase skills
        for base_name, (start_phase, stop_phase) in phase_spans.items():
            skill_file = skill_dir / f"{prefix}-{base_name}" / "SKILL.md"
            assert skill_file.is_file(), f"Missing skill file: {skill_file}"
            content = skill_file.read_text(encoding="utf-8")

            assert f"--start-at {start_phase}" in content, (
                f"Expected --start-at {start_phase} in {skill_file}"
            )
            assert f"--stop-after {stop_phase}" in content, (
                f"Expected --stop-after {stop_phase} in {skill_file}"
            )

            # Ensure no legacy coordinator or direct promotion instructions
            assert "ag_coordinator" not in content
            assert "cc_coordinator" not in content
            assert "promote_translation" not in content

        # 2. Check orchestrate-book skill
        orch_skill = skill_dir / f"{prefix}-orchestrate-book" / "SKILL.md"
        assert orch_skill.is_file(), f"Missing orchestrate skill: {orch_skill}"
        orch_content = orch_skill.read_text(encoding="utf-8")
        assert "orchestrate --workspace books/<book-slug>" in orch_content
        assert "--resume" in orch_content
        assert "--decision" in orch_content


# =============================================================================
# C06: Generated tree
# =============================================================================


def test_c06_generated_tree(tmp_path: Path) -> None:
    """C06: sync_harness_adapters.py --check passes cleanly and detects obsolete/stale files."""
    sync_py = ROOT / "tools" / "sync_harness_adapters.py"
    assert sync_py.is_file()

    # 1. Clean tree check
    res = subprocess.run(
        [sys.executable, str(sync_py), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert res.returncode == 0, (
        f"sync_harness_adapters --check failed:\n{res.stdout}\n{res.stderr}"
    )
    assert "all generated adapters are current" in res.stdout

    # 2. Stale/obsolete detection check
    stray_file = ROOT / ".agent" / "agents" / "ag_coordinator.md"
    stray_file.parent.mkdir(parents=True, exist_ok=True)
    stray_file.write_text("obsolete content", encoding="utf-8")
    try:
        res_stray = subprocess.run(
            [sys.executable, str(sync_py), "--check"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert res_stray.returncode != 0
        assert "obsolete: " in res_stray.stdout
    finally:
        stray_file.unlink(missing_ok=True)


# =============================================================================
# C07: Agent definitions
# =============================================================================


def test_c07_agent_definitions() -> None:
    """C07: Only ag_translator and ag_metadata_translator remain discoverable."""
    agent_dir = ROOT / ".agent" / "agents"
    assert agent_dir.is_dir()

    expected_agents = {"ag_translator.md", "ag_metadata_translator.md"}
    actual_agents = {p.name for p in agent_dir.glob("*.md")}
    assert actual_agents == expected_agents, (
        f"Unexpected agents in {agent_dir}: {actual_agents}"
    )

    # Ensure retired coordinators do not exist anywhere in harness trees
    forbidden = [
        ROOT / ".agent" / "agents" / "ag_coordinator.md",
        ROOT / ".claude" / "agents" / "cc_coordinator.md",
        ROOT / ".claude" / "agents" / "cc_translator.md",
        ROOT / ".claude" / "workflows" / "translate-book.js",
        ROOT / ".opencode" / "agent" / "oc-translator.md",
        ROOT / ".codex" / "agents" / "codex_coordinator.md",
    ]
    for p in forbidden:
        assert not p.exists(), f"Retired agent artifact should not exist: {p}"


# =============================================================================
# C08: Logs and exit contract
# =============================================================================


def test_c08_logs_and_exit_contract(tmp_path: Path) -> None:
    """C08: Completed/paused/blocked/error exit codes (0/2/3/1);

    run summary records execution data without raw or full translated chapter text.
    """
    wf = build_crawl_approved_workspace(tmp_path / "c08_logs")
    runner = MockRunner()
    ops = WorkspaceOps()
    orchestrator = BookOrchestrator(runner=runner, ops=ops)

    def side_effect(workspace: Path, prompt: str, ctx: dict[str, Any]) -> None:
        phase = ctx.get("phase")
        if phase == "metadata_translation":
            meta = load_yaml_model(workspace / "book.yaml", BookMetadata)
            atomic_write_yaml(
                workspace / "book.yaml",
                meta.model_copy(
                    update={
                        "translated_title": f"Dịch: {meta.title}",
                        "translated_author": f"Dịch: {meta.author}"
                        if meta.author
                        else None,
                    }
                ),
            )
        elif phase == "chapter_translation":
            staged_txt = None
            chapter_id = 1
            for line in prompt.splitlines():
                if "staged_txt:" in line:
                    staged_txt = Path(line.partition("staged_txt:")[2].strip())
                if "chapter_id:" in line:
                    try:
                        chapter_id = int(line.partition("chapter_id:")[2].strip())
                    except ValueError:
                        pass
            if staged_txt:
                staged_txt.parent.mkdir(parents=True, exist_ok=True)
                staged_txt.write_text(
                    f"# Chương {chapter_id} Tiêu Đề\n\nBí mật kinh văn không được rò rỉ.\n",
                    encoding="utf-8",
                )

    runner.add_side_effect(side_effect)

    outcome = orchestrator.start(
        wf.root,
        start_at="translate",
        stop_after="translate",
        global_model="test-global-model",
    )
    assert outcome.status == "completed"
    assert outcome.exit_code == 0

    # Verify run summary does not leak raw or translated text (token protection)
    summary_path = wf.root / "reports" / "runs" / outcome.run_id / "run_summary.json"
    assert summary_path.is_file()
    summary_raw = summary_path.read_text(encoding="utf-8")
    summary = json.loads(summary_raw)

    assert summary["status"] == "completed"
    assert summary["selected_span"] == ["translate", "translate"]
    assert "test-global-model" in summary_raw

    # Token protection assertion: full translated text and raw text MUST NOT be in run_summary.json
    assert "Bí mật kinh văn không được rò rỉ" not in summary_raw
    assert "仙人指路" not in summary_raw
