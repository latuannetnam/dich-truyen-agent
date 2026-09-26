from pathlib import Path
from typing import Any
import pytest
from dich_truyen_agent.models import BookMetadata
from dich_truyen_agent.orchestrator.graph import GraphRunner
from dich_truyen_agent.orchestrator.models import OrchestratorConfig
from dich_truyen_agent.orchestrator.runners.mock import MockRunner
from dich_truyen_agent.orchestrator.workspace_ops import WorkspaceOps
from dich_truyen_agent.storage import atomic_write_yaml, load_yaml_model
from orchestrator_support import build_crawl_approved_workspace


def test_metadata_node_passes_catalog_intro_path_when_author_unknown(tmp_path: Path):
    wf = build_crawl_approved_workspace(tmp_path / "ws", chapter_count=1)
    ops = WorkspaceOps()
    runner = MockRunner()

    # Set author to Unknown and clear translations
    meta = load_yaml_model(wf.book, BookMetadata)
    atomic_write_yaml(
        wf.book,
        meta.model_copy(
            update={"author": "Unknown", "translated_title": None, "translated_author": None}
        ),
    )

    # Create catalog_intro.txt in reports
    reports_dir = wf.root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    intro_file = reports_dir / "catalog_intro.txt"
    intro_file.write_text("仙府长生\n作者：长亭空省\n修仙凡人流", encoding="utf-8")

    def side_effect(workspace: Path, prompt: str, ctx: dict[str, Any]) -> None:
        if ctx.get("phase") == "metadata_translation":
            assert "catalog_intro.txt" in prompt
            assert "Source author: Unknown" in prompt
            b_meta = load_yaml_model(wf.book, BookMetadata)
            updated = b_meta.model_copy(
                update={
                    "author": "长亭空省",
                    "translated_title": "Tiên Phủ Trường Sinh",
                    "translated_author": "Trường Đình Không Tỉnh",
                }
            )
            atomic_write_yaml(wf.book, updated)
        elif ctx.get("phase") == "chapter_translation":
            for line in prompt.splitlines():
                if "staged_txt:" in line:
                    staged_txt = Path(line.partition("staged_txt:")[2].strip())
                    staged_txt.parent.mkdir(parents=True, exist_ok=True)
                    staged_txt.write_text("# Chương 1: Tiêu đề\n\nNội dung dịch chuẩn chất lượng.\n", encoding="utf-8")
                    break

    runner.add_side_effect(side_effect)

    config = OrchestratorConfig(
        workspace_root=wf.root,
        start_at="translate",
        stop_after="translate",
        batch_size=1,
    )
    graph_runner = GraphRunner(ops, runner, config)
    outcome = graph_runner.run()
    assert outcome.status == "completed"

    final_meta = load_yaml_model(wf.book, BookMetadata)
    assert final_meta.author == "长亭空省"
    assert final_meta.translated_title == "Tiên Phủ Trường Sinh"
    assert final_meta.translated_author == "Trường Đình Không Tỉnh"


def test_metadata_node_omits_catalog_intro_when_author_already_known(tmp_path: Path):
    wf = build_crawl_approved_workspace(tmp_path / "ws2", chapter_count=1)
    ops = WorkspaceOps()
    runner = MockRunner()

    meta = load_yaml_model(wf.book, BookMetadata)
    atomic_write_yaml(
        wf.book,
        meta.model_copy(
            update={"author": "长亭空省", "translated_title": None, "translated_author": None}
        ),
    )

    def side_effect(workspace: Path, prompt: str, ctx: dict[str, Any]) -> None:
        if ctx.get("phase") == "metadata_translation":
            assert "catalog_intro.txt" not in prompt
            assert "Source author: 长亭空省" in prompt
            b_meta = load_yaml_model(wf.book, BookMetadata)
            updated = b_meta.model_copy(
                update={
                    "translated_title": "Tiên Phủ Trường Sinh",
                    "translated_author": "Trường Đình Không Tỉnh",
                }
            )
            atomic_write_yaml(wf.book, updated)
        elif ctx.get("phase") == "chapter_translation":
            for line in prompt.splitlines():
                if "staged_txt:" in line:
                    staged_txt = Path(line.partition("staged_txt:")[2].strip())
                    staged_txt.parent.mkdir(parents=True, exist_ok=True)
                    staged_txt.write_text("# Chương 1: Tiêu đề\n\nNội dung dịch chuẩn chất lượng.\n", encoding="utf-8")
                    break

    runner.add_side_effect(side_effect)

    config = OrchestratorConfig(
        workspace_root=wf.root,
        start_at="translate",
        stop_after="translate",
        batch_size=1,
    )
    graph_runner = GraphRunner(ops, runner, config)
    outcome = graph_runner.run()
    assert outcome.status == "completed"
