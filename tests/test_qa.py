from pathlib import Path
import pytest

from dich_truyen_agent.models import (
    BookMetadata,
    BookGlossary,
    BookState,
    ChapterCatalog,
    ChapterCatalogEntry,
    ChapterState,
    CheckpointType,
    GlossaryConflict,
    GlossaryConflictReport,
    GlossaryTerm,
    OperationStatus,
    QAFindingType,
    StageStatus,
    TranslationStyle,
)
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.qa import run_qa_check
from dich_truyen_agent.storage import atomic_write_yaml, load_yaml_model
from dich_truyen_agent.workspace import initialize_workspace


@pytest.fixture
def qa_workspace(
    books_root: Path,
    metadata: BookMetadata,
    style: TranslationStyle,
) -> Path:
    # Set up a catalog with 2 chapters
    catalog = ChapterCatalog(
        chapters=[
            ChapterCatalogEntry(
                chapter_id=1,
                slug="chuong-1",
                source_url="https://example.com/c1",
                original_title="Chuong 1",
                raw_filename="0001-c1.txt",
                translation_filename="0001-c1.txt",
            ),
            ChapterCatalogEntry(
                chapter_id=2,
                slug="chuong-2",
                source_url="https://example.com/c2",
                original_title="Chuong 2",
                raw_filename="0002-c2.txt",
                translation_filename="0002-c2.txt",
            ),
        ]
    )
    initialize_workspace(books_root, metadata, catalog, style)
    paths = workspace_paths(books_root, metadata.book_slug)

    # Initialize book state to make them PENDING initially
    book_state = BookState(
        chapters=[
            ChapterState(chapter_id=1),
            ChapterState(chapter_id=2),
        ]
    )
    atomic_write_yaml(paths.state, book_state)
    return paths.root


def test_qa_blocks_missing_or_incomplete_translations(qa_workspace: Path) -> None:
    # Both chapters are initially pending and missing translation files
    report = run_qa_check(qa_workspace)
    assert not report.summary["passed"]
    assert report.summary["error_count"] > 0

    # Ensure findings identify state issues
    state_findings = [f for f in report.findings if f.finding_type == QAFindingType.STRUCTURAL]
    assert len(state_findings) > 0
    assert any("translation state is not completed" in f.message for f in state_findings)


def test_qa_validates_clean_translations(qa_workspace: Path) -> None:
    paths = workspace_paths(qa_workspace.parent, qa_workspace.name)

    # Populate raw and clean translated texts
    (paths.raw / "0001-c1.txt").write_text("Hello Chinese novel world.", encoding="utf-8")
    (paths.raw / "0002-c2.txt").write_text("Another Chinese raw chapter.", encoding="utf-8")

    (paths.translations / "0001-c1.txt").write_text("Thế giới tiểu thuyết.", encoding="utf-8")
    (paths.translations / "0002-c2.txt").write_text("Một chương truyện thô khác.", encoding="utf-8")

    # Update state to completed
    book_state = BookState(
        chapters=[
            ChapterState(
                chapter_id=1,
                translation={"status": StageStatus.COMPLETED, "canonical_path": "translations/0001-c1.txt", "sha256": "dummy1"}
            ),
            ChapterState(
                chapter_id=2,
                translation={"status": StageStatus.COMPLETED, "canonical_path": "translations/0002-c2.txt", "sha256": "dummy2"}
            ),
        ]
    )
    atomic_write_yaml(paths.state, book_state)

    # Run check
    report = run_qa_check(qa_workspace)
    assert report.summary["passed"]
    assert report.summary["error_count"] == 0
    assert report.summary["warning_count"] == 0


def test_qa_detects_empty_files_and_out_of_order_gaps(qa_workspace: Path) -> None:
    paths = workspace_paths(qa_workspace.parent, qa_workspace.name)

    # Create empty translated file for Chapter 1
    (paths.raw / "0001-c1.txt").write_text("Raw", encoding="utf-8")
    (paths.translations / "0001-c1.txt").write_text("   \n  ", encoding="utf-8")

    # Leave Chapter 2 completely missing
    book_state = BookState(
        chapters=[
            ChapterState(
                chapter_id=1,
                translation={"status": StageStatus.COMPLETED, "canonical_path": "translations/0001-c1.txt", "sha256": "dummy1"}
            ),
            ChapterState(chapter_id=2),
        ]
    )
    atomic_write_yaml(paths.state, book_state)

    report = run_qa_check(qa_workspace)
    assert not report.summary["passed"]
    assert any("Translated file is empty" in f.message for f in report.findings)


def test_qa_detects_gap_in_catalog(qa_workspace: Path) -> None:
    paths = workspace_paths(qa_workspace.parent, qa_workspace.name)

    # Catalog missing Chapter 2 (contains 1 and 3)
    catalog = ChapterCatalog(
        chapters=[
            ChapterCatalogEntry(
                chapter_id=1,
                slug="chuong-1",
                source_url="https://example.com/c1",
                original_title="Chuong 1",
                raw_filename="0001-c1.txt",
                translation_filename="0001-c1.txt",
            ),
            ChapterCatalogEntry(
                chapter_id=3,
                slug="chuong-3",
                source_url="https://example.com/c3",
                original_title="Chuong 3",
                raw_filename="0003-c3.txt",
                translation_filename="0003-c3.txt",
            ),
        ]
    )
    atomic_write_yaml(paths.chapters, catalog)

    report = run_qa_check(qa_workspace)
    assert any("Out-of-order gap: Chapter 2" in f.message for f in report.findings)


def test_qa_detects_incompleteness_unbalanced_brackets_missing_ends(qa_workspace: Path) -> None:
    paths = workspace_paths(qa_workspace.parent, qa_workspace.name)

    # Populate raw and incomplete translation
    (paths.raw / "0001-c1.txt").write_text("Raw", encoding="utf-8")
    # Unbalanced quotes & parentheses, missing ending punctuation
    (paths.translations / "0001-c1.txt").write_text('“Chào thế giới (tiểu thuyết " nói vậy', encoding="utf-8")

    book_state = BookState(
        chapters=[
            ChapterState(
                chapter_id=1,
                translation={"status": StageStatus.COMPLETED, "canonical_path": "translations/0001-c1.txt", "sha256": "dummy1"}
            )
        ]
    )
    atomic_write_yaml(paths.state, book_state)

    # Force catalog to only have Chapter 1
    catalog = ChapterCatalog(
        chapters=[
            ChapterCatalogEntry(
                chapter_id=1,
                slug="chuong-1",
                source_url="https://example.com/c1",
                original_title="Chuong 1",
                raw_filename="0001-c1.txt",
                translation_filename="0001-c1.txt",
            )
        ]
    )
    atomic_write_yaml(paths.chapters, catalog)

    report = run_qa_check(qa_workspace)
    assert report.summary["warning_count"] > 0

    warnings = [f.message for f in report.findings if f.severity == "warning"]
    assert any("Unbalanced standard double quotes" in w for w in warnings)
    assert any("Unbalanced parentheses" in w for w in warnings)
    assert any("missing terminal punctuation" in w for w in warnings)


def test_qa_detects_chinese_residue(qa_workspace: Path) -> None:
    paths = workspace_paths(qa_workspace.parent, qa_workspace.name)

    # Raw content
    (paths.raw / "0001-c1.txt").write_text("Chinese raw text.", encoding="utf-8")
    # Translation contains Chinese character '仙' and CJK comma '，'
    (paths.translations / "0001-c1.txt").write_text("Thế giới 仙 nhân，rất đẹp.", encoding="utf-8")

    # Update state and catalog to 1 chapter
    book_state = BookState(
        chapters=[
            ChapterState(
                chapter_id=1,
                translation={"status": StageStatus.COMPLETED, "canonical_path": "translations/0001-c1.txt", "sha256": "dummy1"}
            )
        ]
    )
    atomic_write_yaml(paths.state, book_state)

    catalog = ChapterCatalog(
        chapters=[
            ChapterCatalogEntry(
                chapter_id=1,
                slug="chuong-1",
                source_url="https://example.com/c1",
                original_title="Chuong 1",
                raw_filename="0001-c1.txt",
                translation_filename="0001-c1.txt",
            )
        ]
    )
    atomic_write_yaml(paths.chapters, catalog)

    report = run_qa_check(qa_workspace)
    assert report.summary["warning_count"] > 0
    residue_findings = [f for f in report.findings if f.finding_type == QAFindingType.RESIDUE]
    assert len(residue_findings) == 2  # one for '仙', one for '，'
    assert residue_findings[0].details["char"] == "仙"
    assert residue_findings[1].details["char"] == "，"


def test_qa_detects_abnormal_length_ratio(qa_workspace: Path) -> None:
    paths = workspace_paths(qa_workspace.parent, qa_workspace.name)

    # 1. Ratio too low (< 0.6): Raw is long, translation is extremely short
    (paths.raw / "0001-c1.txt").write_text("A very long original Chinese novel chapter with many details." * 20, encoding="utf-8")
    (paths.translations / "0001-c1.txt").write_text("Ngắn.", encoding="utf-8")

    # 2. Ratio too high (> 2.0): Raw is short, translation is extremely long
    (paths.raw / "0002-c2.txt").write_text("Raw", encoding="utf-8")
    (paths.translations / "0002-c2.txt").write_text("Một bản dịch tiếng Việt vô cùng dài dòng văn tự lặp đi lặp lại rất nhiều lần để tạo độ dài." * 20, encoding="utf-8")

    book_state = BookState(
        chapters=[
            ChapterState(
                chapter_id=1,
                translation={"status": StageStatus.COMPLETED, "canonical_path": "translations/0001-c1.txt", "sha256": "dummy1"}
            ),
            ChapterState(
                chapter_id=2,
                translation={"status": StageStatus.COMPLETED, "canonical_path": "translations/0002-c2.txt", "sha256": "dummy2"}
            ),
        ]
    )
    atomic_write_yaml(paths.state, book_state)

    report = run_qa_check(qa_workspace)
    length_findings = [f for f in report.findings if f.finding_type == QAFindingType.LENGTH]
    assert len(length_findings) == 2
    assert any("Abnormal character length ratio" in f.message for f in length_findings)


def test_qa_detects_glossary_conflicts(qa_workspace: Path) -> None:
    paths = workspace_paths(qa_workspace.parent, qa_workspace.name)

    # Setup clean workspace details
    (paths.raw / "0001-c1.txt").write_text("Raw", encoding="utf-8")
    (paths.translations / "0001-c1.txt").write_text("Bản dịch sạch.", encoding="utf-8")

    book_state = BookState(
        chapters=[
            ChapterState(
                chapter_id=1,
                translation={"status": StageStatus.COMPLETED, "canonical_path": "translations/0001-c1.txt", "sha256": "dummy1"}
            )
        ]
    )
    atomic_write_yaml(paths.state, book_state)

    catalog = ChapterCatalog(
        chapters=[
            ChapterCatalogEntry(
                chapter_id=1,
                slug="chuong-1",
                source_url="https://example.com/c1",
                original_title="Chuong 1",
                raw_filename="0001-c1.txt",
                translation_filename="0001-c1.txt",
            )
        ]
    )
    atomic_write_yaml(paths.chapters, catalog)

    # Create glossary conflict report
    conflict_report = GlossaryConflictReport(
        conflicts=[
            GlossaryConflict(
                term="剑来",
                existing_translation="Kiếm Lai",
                existing_source="manual",
                proposed_translation="Kiếm Đến",
                proposed_source="chapter_1_proposal",
                chapter_id=1,
            )
        ]
    )
    atomic_write_yaml(paths.glossary_conflicts, conflict_report)

    report = run_qa_check(qa_workspace)
    glossary_findings = [f for f in report.findings if f.finding_type == QAFindingType.GLOSSARY]
    assert len(glossary_findings) == 1
    assert glossary_findings[0].severity == "error"
    assert "Unresolved glossary conflict" in glossary_findings[0].message
    assert glossary_findings[0].details["term"] == "剑来"
    assert report.summary["passed"] is False


def test_qa_detects_rejected_glossary_alias_usage(qa_workspace: Path) -> None:
    paths = workspace_paths(qa_workspace.parent, qa_workspace.name)

    (paths.raw / "0001-c1.txt").write_text("剑来", encoding="utf-8")
    (paths.translations / "0001-c1.txt").write_text("Kiếm Đến xuất hiện.", encoding="utf-8")

    book_state = BookState(
        chapters=[
            ChapterState(
                chapter_id=1,
                translation={"status": StageStatus.COMPLETED, "canonical_path": "translations/0001-c1.txt", "sha256": "dummy1"}
            )
        ]
    )
    atomic_write_yaml(paths.state, book_state)
    catalog = ChapterCatalog(
        chapters=[
            ChapterCatalogEntry(
                chapter_id=1,
                slug="chuong-1",
                source_url="https://example.com/c1",
                original_title="Chuong 1",
                raw_filename="0001-c1.txt",
                translation_filename="0001-c1.txt",
            )
        ]
    )
    atomic_write_yaml(paths.chapters, catalog)
    atomic_write_yaml(
        paths.glossary,
        BookGlossary(
            terms={
                "剑来": GlossaryTerm(
                    translation="Kiếm Lai",
                    category="item",
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
                    term="剑来",
                    existing_translation="Kiếm Lai",
                    existing_source="manual",
                    proposed_translation="Kiếm Đến",
                    proposed_source="chapter_1_proposal",
                    chapter_id=1,
                )
            ]
        ),
    )

    report = run_qa_check(qa_workspace)

    glossary_findings = [f for f in report.findings if f.finding_type == QAFindingType.GLOSSARY]
    assert any("Rejected glossary alias" in f.message for f in glossary_findings)
    alias_finding = next(f for f in glossary_findings if "Rejected glossary alias" in f.message)
    assert alias_finding.severity == "error"
    assert alias_finding.details["term"] == "剑来"
    assert alias_finding.details["expected_translation"] == "Kiếm Lai"
    assert alias_finding.details["rejected_alias"] == "Kiếm Đến"


def test_cli_check_and_approve_qa(qa_workspace: Path, capsys) -> None:
    from dich_truyen_agent.cli import build_parser, run_command
    from dich_truyen_agent.models import CheckpointRecord
    paths = workspace_paths(qa_workspace.parent, qa_workspace.name)

    # 1. Clean workspace setup
    (paths.raw / "0001-c1.txt").write_text("Hello Chinese novel world.", encoding="utf-8")
    (paths.raw / "0002-c2.txt").write_text("Another Chinese raw chapter.", encoding="utf-8")

    (paths.translations / "0001-c1.txt").write_text("Thế giới tiểu thuyết.", encoding="utf-8")
    (paths.translations / "0002-c2.txt").write_text("Một chương truyện thô khác.", encoding="utf-8")

    # Update state to completed
    book_state = BookState(
        chapters=[
            ChapterState(
                chapter_id=1,
                translation={"status": StageStatus.COMPLETED, "canonical_path": "translations/0001-c1.txt", "sha256": "dummy1"}
            ),
            ChapterState(
                chapter_id=2,
                translation={"status": StageStatus.COMPLETED, "canonical_path": "translations/0002-c2.txt", "sha256": "dummy2"}
            ),
        ]
    )
    atomic_write_yaml(paths.state, book_state)

    # 2. Run CLI command check-translation
    args_check = build_parser().parse_args(["check-translation", "--workspace", str(qa_workspace)])
    res_check = run_command(args_check)
    assert res_check.status is OperationStatus.OK
    assert "QA check completed" in res_check.reason
    assert (paths.reports / "qa-report.yaml").is_file()

    # Capture stdout
    stdout = capsys.readouterr().out
    assert "### Translation QA Findings Summary" in stdout
    assert "✨ No issues found! Workspace is ready for approval." in stdout

    # 3. Run CLI command approve-qa
    args_approve = build_parser().parse_args(["approve-qa", "--workspace", str(qa_workspace)])
    res_approve = run_command(args_approve)
    assert res_approve.status is OperationStatus.OK
    assert "checkpoint approved" in res_approve.reason
    assert (qa_workspace / "checkpoints" / "qa-approved.yaml").is_file()

    # Verify checkpoint contents
    checkpoint = load_yaml_model(qa_workspace / "checkpoints" / "qa-approved.yaml", CheckpointRecord)
    assert checkpoint.checkpoint_type == CheckpointType.QA_APPROVED
    assert set(checkpoint.evidence_hashes.keys()) == {
        "chapters.yaml",
        "state.yaml",
        "reports/qa-report.yaml",
        "translations/0001-c1.txt",
        "translations/0002-c2.txt",
    }


def test_approve_current_qa_rejects_errors(qa_workspace: Path) -> None:
    from dich_truyen_agent.checkpoints import approve_current_qa
    from dich_truyen_agent.models import QAReport
    report = QAReport(
        summary={"error_count": 2, "warning_count": 0, "findings_count": 2},
        findings=[],
    )
    result = approve_current_qa(qa_workspace, report)
    assert result.status is OperationStatus.BLOCKED
    assert "critical errors" in result.reason.lower() or "error" in result.reason.lower()


def test_approve_current_qa_rejects_warnings_without_allow_warnings(qa_workspace: Path) -> None:
    from dich_truyen_agent.checkpoints import approve_current_qa
    from dich_truyen_agent.models import QAReport, QAFinding, QAFindingType
    report = QAReport(
        summary={"error_count": 0, "warning_count": 1, "findings_count": 1},
        findings=[
            QAFinding(
                chapter_id=1,
                finding_type=QAFindingType.LENGTH,
                severity="warning",
                message="Length mismatch",
            )
        ],
    )
    result = approve_current_qa(qa_workspace, report, allow_warnings=False)
    assert result.status is OperationStatus.BLOCKED
    assert "allow_warnings" in result.reason or "findings" in result.reason


def test_approve_current_qa_allows_warnings_with_allow_warnings(qa_workspace: Path) -> None:
    from dich_truyen_agent.checkpoints import approve_current_qa
    from dich_truyen_agent.models import (
        ApprovalScope,
        CheckpointRecord,
        QAFinding,
        QAFindingType,
        QAReport,
    )
    paths = workspace_paths(qa_workspace.parent, qa_workspace.name)
    (paths.raw / "0001-c1.txt").write_text("Raw 1", encoding="utf-8")
    (paths.raw / "0002-c2.txt").write_text("Raw 2", encoding="utf-8")
    (paths.translations / "0001-c1.txt").write_text("Dịch 1", encoding="utf-8")
    (paths.translations / "0002-c2.txt").write_text("Dịch 2", encoding="utf-8")

    report = QAReport(
        summary={"error_count": 0, "warning_count": 1, "findings_count": 1},
        findings=[
            QAFinding(
                chapter_id=1,
                finding_type=QAFindingType.LENGTH,
                severity="warning",
                message="Length mismatch",
            )
        ],
    )
    result = approve_current_qa(qa_workspace, report, allow_warnings=True)
    assert result.status is OperationStatus.OK
    checkpoint = load_yaml_model(qa_workspace / "checkpoints" / "qa-approved.yaml", CheckpointRecord)
    assert checkpoint.scope == ApprovalScope.PARTIAL


def test_qa_evidence_tracks_catalog_state_report_and_translations(qa_workspace: Path) -> None:
    from dich_truyen_agent.checkpoints import approve_current_qa, check_gate
    from dich_truyen_agent.models import QAReport
    paths = workspace_paths(qa_workspace.parent, qa_workspace.name)
    (paths.raw / "0001-c1.txt").write_text("Raw 1", encoding="utf-8")
    (paths.raw / "0002-c2.txt").write_text("Raw 2", encoding="utf-8")
    (paths.translations / "0001-c1.txt").write_text("Dịch 1", encoding="utf-8")
    (paths.translations / "0002-c2.txt").write_text("Dịch 2", encoding="utf-8")

    report = QAReport(
        summary={"error_count": 0, "warning_count": 0, "findings_count": 0},
        findings=[],
    )

    res = approve_current_qa(qa_workspace, report, allow_warnings=False)
    assert res.status is OperationStatus.OK
    assert check_gate(qa_workspace, CheckpointType.QA_APPROVED).status is OperationStatus.OK

    # 1. Mutate chapters.yaml -> blocked
    orig_catalog = paths.chapters.read_bytes()
    paths.chapters.write_bytes(orig_catalog + b"\n# mutated")
    assert check_gate(qa_workspace, CheckpointType.QA_APPROVED).status is OperationStatus.BLOCKED
    paths.chapters.write_bytes(orig_catalog)
    assert check_gate(qa_workspace, CheckpointType.QA_APPROVED).status is OperationStatus.OK

    # 2. Mutate state.yaml -> blocked
    orig_state = paths.state.read_bytes()
    paths.state.write_bytes(orig_state + b"\n# mutated")
    assert check_gate(qa_workspace, CheckpointType.QA_APPROVED).status is OperationStatus.BLOCKED
    paths.state.write_bytes(orig_state)
    assert check_gate(qa_workspace, CheckpointType.QA_APPROVED).status is OperationStatus.OK

    # 3. Mutate qa-report.yaml -> blocked
    qa_rep_path = paths.reports / "qa-report.yaml"
    orig_rep = qa_rep_path.read_bytes()
    qa_rep_path.write_bytes(orig_rep + b"\n# mutated")
    assert check_gate(qa_workspace, CheckpointType.QA_APPROVED).status is OperationStatus.BLOCKED
    qa_rep_path.write_bytes(orig_rep)
    assert check_gate(qa_workspace, CheckpointType.QA_APPROVED).status is OperationStatus.OK

    # 4. Mutate a translation file -> blocked
    trans1 = paths.translations / "0001-c1.txt"
    orig_trans = trans1.read_bytes()
    trans1.write_bytes(b"Mutated translation text")
    assert check_gate(qa_workspace, CheckpointType.QA_APPROVED).status is OperationStatus.BLOCKED
    trans1.write_bytes(orig_trans)
    assert check_gate(qa_workspace, CheckpointType.QA_APPROVED).status is OperationStatus.OK

