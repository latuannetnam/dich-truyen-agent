import json
from pathlib import Path
from datetime import UTC, datetime

import pytest
import yaml

from dich_truyen_agent.checkpoints import approve_checkpoint
from dich_truyen_agent.models import (
    BookMetadata,
    BookGlossary,
    BookState,
    ChapterCatalog,
    ChapterCatalogEntry,
    CheckpointType,
    GlossaryConflict,
    GlossaryConflictReport,
    GlossaryContext,
    GlossaryTerm,
    OperationStatus,
    StageRecord,
    StageStatus,
    TranslationStyle,
)
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.storage import atomic_write_yaml, load_yaml_model, sha256_file
from dich_truyen_agent.workspace import (
    initialize_workspace,
    prepare_translation_context,
    promote_chapter_translation,
    get_next_pending_translation,
)


@pytest.fixture
def test_workspace(
    books_root: Path,
    metadata: BookMetadata,
    style: TranslationStyle,
) -> Path:
    # Initialize workspace with 3 sequential chapters
    catalog = ChapterCatalog(
        chapters=[
            ChapterCatalogEntry(
                chapter_id=1,
                slug="chuong-0001",
                source_url="http://example.com/1",
                original_title="第1章 仙人指路",
                raw_filename="0001-chuong-0001.txt",
                translation_filename="0001-chuong-0001.txt",
            ),
            ChapterCatalogEntry(
                chapter_id=2,
                slug="chuong-0002",
                source_url="http://example.com/2",
                original_title="第2章 炼气入体",
                raw_filename="0002-chuong-0002.txt",
                translation_filename="0002-chuong-0002.txt",
            ),
            ChapterCatalogEntry(
                chapter_id=3,
                slug="chuong-0003",
                source_url="http://example.com/3",
                original_title="第3章 宗门大比",
                raw_filename="0003-chuong-0003.txt",
                translation_filename="0003-chuong-0003.txt",
            ),
        ]
    )
    initialize_workspace(books_root, metadata, catalog, style)
    paths = workspace_paths(books_root, metadata.book_slug)
    
    # Write raw chapter texts
    (paths.raw / "0001-chuong-0001.txt").write_text("仙人指路", encoding="utf-8")
    (paths.raw / "0002-chuong-0002.txt").write_text("炼气入体", encoding="utf-8")
    (paths.raw / "0003-chuong-0003.txt").write_text("宗门大比", encoding="utf-8")
    
    # Set raw statuses to COMPLETED in state
    state = load_yaml_model(paths.state, BookState)
    for c_state in state.chapters:
        raw_name = f"{c_state.chapter_id:04d}-chuong-{c_state.chapter_id:04d}.txt"
        c_state.raw = StageRecord(
            status=StageStatus.COMPLETED,
            canonical_path=f"raw/{raw_name}",
            sha256=sha256_file(paths.raw / raw_name),
            updated_at=datetime.now(UTC),
        )
    atomic_write_yaml(paths.state, state)
    
    return paths.root


def test_prepare_context_blocks_without_crawl_approved(test_workspace: Path) -> None:
    # Fails because gate is not approved yet
    result = prepare_translation_context(test_workspace, 1)
    assert result.status is OperationStatus.BLOCKED
    assert "missing crawl-approved" in result.reason


def test_prepare_context_blocks_with_invalid_chapter(test_workspace: Path) -> None:
    # Approve crawl checkpoint
    paths = workspace_paths(test_workspace.parent, test_workspace.name)
    report = paths.reports / "crawl.yaml"
    report.write_text("review", encoding="utf-8")
    approve_checkpoint(
        test_workspace,
        CheckpointType.CRAWL_APPROVED,
        "reports/crawl.yaml",
        ["raw/0001-chuong-0001.txt"],
    )

    result = prepare_translation_context(test_workspace, 999)
    assert result.status is OperationStatus.ERROR
    assert "not found in catalog" in result.reason


def test_prepare_context_resolves_fallback_on_first_chapter(test_workspace: Path) -> None:
    # Approve crawl checkpoint
    paths = workspace_paths(test_workspace.parent, test_workspace.name)
    report = paths.reports / "crawl.yaml"
    report.write_text("review", encoding="utf-8")
    approve_checkpoint(
        test_workspace,
        CheckpointType.CRAWL_APPROVED,
        "reports/crawl.yaml",
        ["raw/0001-chuong-0001.txt"],
    )

    result = prepare_translation_context(test_workspace, 1)
    assert result.status is OperationStatus.OK
    
    payload = json.loads(result.reason)
    assert payload["chapter_id"] == 1
    assert payload["title_cn"] == "第1章 仙人指路"
    assert payload["prev_translation_path"] is None
    assert payload["is_fallback"] is True
    assert "no predecessor" in payload["fallback_reason"]


def test_prepare_context_writes_relevant_glossary_context(test_workspace: Path) -> None:
    paths = workspace_paths(test_workspace.parent, test_workspace.name)
    report = paths.reports / "crawl.yaml"
    report.write_text("review", encoding="utf-8")
    approve_checkpoint(
        test_workspace,
        CheckpointType.CRAWL_APPROVED,
        "reports/crawl.yaml",
        ["raw/0001-chuong-0001.txt"],
    )

    atomic_write_yaml(
        paths.glossary,
        BookGlossary(
            terms={
                "仙人": GlossaryTerm(
                    translation="Tiên Nhân",
                    category="character",
                    source="manual",
                    is_canonical=True,
                ),
                "炼气": GlossaryTerm(
                    translation="Luyện Khí",
                    category="cultivation",
                    source="manual",
                    is_canonical=True,
                ),
            }
        ),
    )
    atomic_write_yaml(
        paths.glossary_conflicts,
        GlossaryConflictReport(
            conflicts=[
                GlossaryConflict(
                    term="仙人",
                    existing_translation="Tiên Nhân",
                    existing_source="manual",
                    proposed_translation="Tiên Ông",
                    proposed_source="chapter_2_proposal",
                    chapter_id=2,
                )
            ]
        ),
    )

    result = prepare_translation_context(test_workspace, 1)

    assert result.status is OperationStatus.OK
    payload = json.loads(result.reason)
    context_path = Path(payload["glossary_context_path"])
    assert context_path == paths.staging / "chuong-0001-glossary-context.yaml"
    context = load_yaml_model(context_path, GlossaryContext)
    assert context.chapter_id == 1
    assert set(context.terms) == {"仙人"}
    assert context.terms["仙人"].translation == "Tiên Nhân"
    assert context.terms["仙人"].rejected_aliases == ["Tiên Ông"]


def test_prepare_context_out_of_order_blocks(test_workspace: Path) -> None:
    paths = workspace_paths(test_workspace.parent, test_workspace.name)
    report = paths.reports / "crawl.yaml"
    report.write_text("review", encoding="utf-8")
    approve_checkpoint(
        test_workspace,
        CheckpointType.CRAWL_APPROVED,
        "reports/crawl.yaml",
        ["raw/0001-chuong-0001.txt", "raw/0002-chuong-0002.txt"],
    )

    # Trying to translate Chapter 2 before Chapter 1 is completed
    result = prepare_translation_context(test_workspace, 2)
    assert result.status is OperationStatus.BLOCKED
    assert "preceding chapter 1 translation is not completed" in result.reason


def test_promote_chapter_validation_and_success(test_workspace: Path) -> None:
    paths = workspace_paths(test_workspace.parent, test_workspace.name)
    staged_txt = paths.staging / "chuong-0001-staged.txt"
    staged_yaml = paths.staging / "chuong-0001-proposals.yaml"
    
    # 1. Blocks if staged file not found
    result = promote_chapter_translation(test_workspace, 1)
    assert result.status is OperationStatus.ERROR
    assert "staged translation file not found" in result.reason
    
    # Write staged translation
    staged_txt.write_text("Chương 1: Tiên Nhân Chỉ Lộ\nHắn nhẹ nhàng bước lên...", encoding="utf-8")
    
    # Write staged proposals (invalid YAML)
    staged_yaml.write_text("invalid: - proposals: : yaml", encoding="utf-8")
    result = promote_chapter_translation(test_workspace, 1)
    assert result.status is OperationStatus.ERROR
    assert "invalid staged proposals YAML syntax" in result.reason
    
    # Write valid proposals
    proposals = {
        "修炼": {"translation": "tu luyện", "category": "other", "note": "cultivate"}
    }
    staged_yaml.write_text(yaml.safe_dump(proposals), encoding="utf-8")
    
    # Promote successfully
    result = promote_chapter_translation(test_workspace, 1)
    assert result.status is OperationStatus.OK
    assert "promoted successfully" in result.reason
    
    # Check outputs exist and are promoted
    promoted_file = paths.translations / "0001-chuong-0001.txt"
    assert promoted_file.is_file()
    assert promoted_file.read_text(encoding="utf-8").startswith("Chương 1: Tiên Nhân Chỉ Lộ")
    
    # State is updated
    state = load_yaml_model(paths.state, BookState)
    ch1_state = next(c for c in state.chapters if c.chapter_id == 1)
    assert ch1_state.translation.status is StageStatus.COMPLETED
    assert ch1_state.translation.canonical_path == "translations/0001-chuong-0001.txt"
    assert ch1_state.translation.sha256 == sha256_file(promoted_file)
    
    # Glossary proposals merged
    glossary = load_yaml_model(paths.glossary, BookGlossary)
    assert "修炼" in glossary.terms
    assert glossary.terms["修炼"].translation == "tu luyện"
    assert glossary.terms["修炼"].source == "chapter_1_proposal"
    
    # Staging cleaned
    assert not staged_txt.exists()
    assert not staged_yaml.exists()


def test_promote_chapter_blocks_conflicting_glossary_proposal(test_workspace: Path) -> None:
    paths = workspace_paths(test_workspace.parent, test_workspace.name)
    staged_txt = paths.staging / "chuong-0001-staged.txt"
    staged_yaml = paths.staging / "chuong-0001-proposals.yaml"

    atomic_write_yaml(
        paths.glossary,
        BookGlossary(
            terms={
                "修炼": GlossaryTerm(
                    translation="tu luyện",
                    category="cultivation",
                    source="manual",
                    is_canonical=True,
                )
            }
        ),
    )
    staged_txt.write_text("# Chương 1\n\nHắn bắt đầu tu hành.", encoding="utf-8")
    staged_yaml.write_text(
        yaml.safe_dump(
            {"修炼": {"translation": "tu hành", "category": "cultivation"}},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    result = promote_chapter_translation(test_workspace, 1)

    assert result.status is OperationStatus.BLOCKED
    assert "glossary consistency blocked" in result.reason
    assert not (paths.translations / "0001-chuong-0001.txt").exists()
    assert staged_txt.exists()
    assert staged_yaml.exists()
    state = load_yaml_model(paths.state, BookState)
    ch1_state = next(c for c in state.chapters if c.chapter_id == 1)
    assert ch1_state.translation.status is StageStatus.PENDING
    conflict_report = load_yaml_model(paths.glossary_conflicts, GlossaryConflictReport)
    assert len(conflict_report.conflicts) == 1
    assert conflict_report.conflicts[0].term == "修炼"
    assert conflict_report.conflicts[0].proposed_translation == "tu hành"


def test_promote_chapter_blocks_rejected_alias_in_staged_text(test_workspace: Path) -> None:
    paths = workspace_paths(test_workspace.parent, test_workspace.name)
    staged_txt = paths.staging / "chuong-0001-staged.txt"

    atomic_write_yaml(
        paths.glossary,
        BookGlossary(
            terms={
                "仙人": GlossaryTerm(
                    translation="Tiên Nhân",
                    category="character",
                    source="manual",
                    is_canonical=True,
                )
            }
        ),
    )
    atomic_write_yaml(
        paths.glossary_conflicts,
        GlossaryConflictReport(
            conflicts=[
                GlossaryConflict(
                    term="仙人",
                    existing_translation="Tiên Nhân",
                    existing_source="manual",
                    proposed_translation="Tiên Ông",
                    proposed_source="chapter_2_proposal",
                    chapter_id=2,
                )
            ]
        ),
    )
    staged_txt.write_text("# Chương 1\n\nTiên Ông chỉ đường cho hắn.", encoding="utf-8")

    result = promote_chapter_translation(test_workspace, 1)

    assert result.status is OperationStatus.BLOCKED
    assert "rejected glossary alias" in result.reason
    assert not (paths.translations / "0001-chuong-0001.txt").exists()
    assert staged_txt.exists()
    state = load_yaml_model(paths.state, BookState)
    ch1_state = next(c for c in state.chapters if c.chapter_id == 1)
    assert ch1_state.translation.status is StageStatus.PENDING


def test_get_next_pending_translation(test_workspace: Path) -> None:
    paths = workspace_paths(test_workspace.parent, test_workspace.name)
    
    # Approve crawl checkpoint
    report = paths.reports / "crawl.yaml"
    report.write_text("review", encoding="utf-8")
    approve_checkpoint(
        test_workspace,
        CheckpointType.CRAWL_APPROVED,
        "reports/crawl.yaml",
        ["raw/0001-chuong-0001.txt", "raw/0002-chuong-0002.txt", "raw/0003-chuong-0003.txt"],
    )
    
    # Initially next pending is Chapter 1
    result = get_next_pending_translation(test_workspace)
    assert result.status is OperationStatus.OK
    payload = json.loads(result.reason)
    assert payload["chapter_id"] == 1
    
    # Staging and promoting Chapter 1
    (paths.staging / "chuong-0001-staged.txt").write_text("Chương 1: Tiên Nhân Chỉ Lộ\nNội dung chương 1...", encoding="utf-8")
    promote_chapter_translation(test_workspace, 1)
    
    # Next pending is Chapter 2
    result = get_next_pending_translation(test_workspace)
    assert result.status is OperationStatus.OK
    payload = json.loads(result.reason)
    assert payload["chapter_id"] == 2
    
    # Simulating gap (Chapter 3 is completed but Chapter 2 is pending)
    # This shouldn't happen under normal sequential orchestration, but we verify gap detection blocks
    state = load_yaml_model(paths.state, BookState)
    ch3_state = next(c for c in state.chapters if c.chapter_id == 3)
    ch3_state.translation = StageRecord(
        status=StageStatus.COMPLETED,
        canonical_path="translations/0003-chuong-0003.txt",
        sha256="0"*64,
        updated_at=datetime.now(UTC),
    )
    # Write a dummy file to satisfy validation if inspect runs
    (paths.translations / "0003-chuong-0003.txt").write_text("Chương 3: Tông Môn Đại Tỷ\n...", encoding="utf-8")
    ch3_state.translation.sha256 = sha256_file(paths.translations / "0003-chuong-0003.txt")
    atomic_write_yaml(paths.state, state)
    
    # Next pending is Chapter 2, but progress check fails on Chapter 2 due to ordering constraint block
    result = get_next_pending_translation(test_workspace)
    # Since Chapter 2 is pending but Chapter 3 is completed, wait, does that block?
    # Yes, get_next_pending_translation checks from catalog order:
    # First pending is Chapter 2.
    # Check prior chapters: Chapter 1 is completed.
    # Is it blocked? No, because all chapters BEFORE 2 are completed!
    # But if we query next pending when Chapter 3 is pending but Chapter 2 is not completed, and we try to translate Chapter 3:
    # Yes! If we query get_next_pending_translation, it returns Chapter 2 is pending.
    # What if Chapter 2 is PENDING, but Chapter 3 was completed?
    # get_next_pending_translation(test_workspace) will return Chapter 2 (payload), which is correct.
    # Let's verify out-of-order check: if we try to translate Chapter 3:
    result = prepare_translation_context(test_workspace, 3)
    assert result.status is OperationStatus.BLOCKED
    assert "preceding chapter 2 translation is not completed" in result.reason
