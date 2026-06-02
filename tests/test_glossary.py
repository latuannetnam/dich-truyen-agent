import pytest
from pathlib import Path
from pydantic import ValidationError

from dich_truyen_agent.models import (
    GlossaryTerm,
    BookGlossary,
    GlossaryConflict,
    GlossaryConflictReport,
    OperationStatus,
)
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.workspace import initialize_workspace, inspect_workspace


def test_glossary_models():
    # Valid term
    term = GlossaryTerm(
        translation="Lâm Phong",
        category="character",
        source="initial_generation",
        is_canonical=False,
        note="Main character",
    )
    assert term.translation == "Lâm Phong"
    assert term.category == "character"
    assert term.is_canonical is False

    # Invalid category is allowed (since it's a string), but empty/missing required is rejected
    with pytest.raises(ValidationError):
        GlossaryTerm(category="character", source="manual")  # missing translation

    # Book glossary
    glossary = BookGlossary(
        terms={
            "林枫": term
        }
    )
    assert glossary.terms["林枫"].translation == "Lâm Phong"

    # Invalid extra field
    with pytest.raises(ValidationError):
        BookGlossary(terms={"林枫": term}, extra_field="forbidden")

    # Valid conflict
    conflict = GlossaryConflict(
        term="林枫",
        existing_translation="Lâm Phong",
        existing_source="manual",
        proposed_translation="Lâm Phong 2",
        proposed_source="chapter_1_proposal",
        chapter_id=1,
    )
    assert conflict.term == "林枫"
    assert conflict.chapter_id == 1

    # Invalid conflict (negative/zero chapter_id)
    with pytest.raises(ValidationError):
        GlossaryConflict(
            term="林枫",
            existing_translation="Lâm Phong",
            existing_source="manual",
            proposed_translation="Lâm Phong 2",
            proposed_source="chapter_1_proposal",
            chapter_id=0,
        )


def test_glossary_paths(books_root):
    paths = workspace_paths(books_root, "demo-book")
    assert paths.glossary == paths.root / "glossary.yaml"
    assert paths.glossary_snapshots == paths.root / "checkpoints" / "glossary-snapshots"
    assert paths.glossary_conflicts == paths.root / "reports" / "glossary-conflicts.yaml"


def test_initialize_workspace_creates_glossary_snapshots_dir(books_root, metadata, catalog, style):
    result = initialize_workspace(books_root, metadata, catalog, style)
    assert result.status == OperationStatus.OK

    paths = workspace_paths(books_root, metadata.book_slug)
    assert paths.glossary_snapshots.is_dir()

    inspect_result = inspect_workspace(paths.root)
    assert inspect_result.status == OperationStatus.OK


def test_initial_glossary_generation(books_root, metadata, catalog, style):
    from dich_truyen_agent.glossary import initialize_glossary_file
    from dich_truyen_agent.storage import load_yaml_model
    
    initialize_workspace(books_root, metadata, catalog, style)
    paths = workspace_paths(books_root, metadata.book_slug)
    
    terms_extracted = {
        "林枫": {"translation": "Lâm Phong", "category": "character", "note": "Main character"},
        "青云宗": {"translation": "Thanh Vân Tông", "category": "sect"}
    }
    
    result = initialize_glossary_file(paths.root, terms_extracted)
    assert result.status == OperationStatus.OK
    assert paths.glossary.is_file()
    
    glossary = load_yaml_model(paths.glossary, BookGlossary)
    assert "林枫" in glossary.terms
    assert glossary.terms["林枫"].translation == "Lâm Phong"
    assert glossary.terms["林枫"].category == "character"
    assert glossary.terms["林枫"].source == "initial_generation"
    assert glossary.terms["林枫"].is_canonical is False
    
    assert "青云宗" in glossary.terms
    assert glossary.terms["青云宗"].translation == "Thanh Vân Tông"
    assert glossary.terms["青云宗"].category == "sect"
    assert glossary.terms["青云宗"].is_canonical is False


def test_glossary_cli_generate_glossary(books_root, metadata, catalog, style, tmp_path):
    from dich_truyen_agent.cli import build_parser, run_command
    from dich_truyen_agent.storage import load_yaml_model
    import yaml
    
    initialize_workspace(books_root, metadata, catalog, style)
    paths = workspace_paths(books_root, metadata.book_slug)
    
    # Create a terms input file
    input_file = tmp_path / "terms.yaml"
    terms_data = {
        "林枫": {"translation": "Lâm Phong", "category": "character", "note": "Main character"}
    }
    with input_file.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(terms_data, stream)
        
    parser = build_parser()
    args = parser.parse_args([
        "generate-glossary",
        "--books-root", str(books_root),
        "--slug", metadata.book_slug,
        "--terms-input", str(input_file)
    ])
    
    result = run_command(args)
    assert result.status == OperationStatus.OK
    assert paths.glossary.is_file()
    
    glossary = load_yaml_model(paths.glossary, BookGlossary)
    assert "林枫" in glossary.terms
    assert glossary.terms["林枫"].translation == "Lâm Phong"


def test_merge_proposals_and_snapshots(books_root, metadata, catalog, style):
    from dich_truyen_agent.glossary import initialize_glossary_file, merge_glossary_proposals
    from dich_truyen_agent.storage import load_yaml_model
    
    initialize_workspace(books_root, metadata, catalog, style)
    paths = workspace_paths(books_root, metadata.book_slug)
    
    # Initialize with 1 term
    initialize_glossary_file(paths.root, {
        "林枫": {"translation": "Lâm Phong", "category": "character"}
    })
    
    # Proposals for chapter 1
    proposals_ch1 = {
        "林枫": GlossaryTerm(translation="Lâm Phong", category="character", source="ch1", note="Updated note"),
        "苏颜": GlossaryTerm(translation="Tô Nhan", category="character", source="ch1")
    }
    
    result = merge_glossary_proposals(paths.root, 1, proposals_ch1)
    assert result.status == OperationStatus.OK
    
    # Verify snapshot
    snapshot_path = paths.glossary_snapshots / "chapter-0001.yaml"
    assert snapshot_path.is_file()
    snapshot_glossary = load_yaml_model(snapshot_path, BookGlossary)
    assert "苏颜" not in snapshot_glossary.terms  # Snapshot taken BEFORE merge
    assert "林枫" in snapshot_glossary.terms
    
    # Verify merged glossary
    glossary = load_yaml_model(paths.glossary, BookGlossary)
    assert "苏颜" in glossary.terms
    assert glossary.terms["苏颜"].translation == "Tô Nhan"
    assert glossary.terms["苏颜"].source == "chapter_1_proposal"
    assert glossary.terms["林枫"].note == "Updated note"  # Note updated


def test_conflict_reporting_and_locks(books_root, metadata, catalog, style):
    from dich_truyen_agent.glossary import initialize_glossary_file, merge_glossary_proposals
    from dich_truyen_agent.storage import load_yaml_model, atomic_write_yaml
    
    initialize_workspace(books_root, metadata, catalog, style)
    paths = workspace_paths(books_root, metadata.book_slug)
    
    # Initialize glossary
    initialize_glossary_file(paths.root, {
        "林枫": {"translation": "Lâm Phong", "category": "character"}
    })
    
    # Manually lock the term (simulate by direct edit)
    glossary = load_yaml_model(paths.glossary, BookGlossary)
    glossary.terms["林枫"].is_canonical = True
    glossary.terms["林枫"].translation = "Lâm Phong Locked"
    atomic_write_yaml(paths.glossary, glossary)
    
    # Proposals containing mismatching term
    proposals = {
        "林枫": GlossaryTerm(translation="Lâm Phong New", category="character", source="ch2")
    }
    
    result = merge_glossary_proposals(paths.root, 2, proposals)
    assert result.status == OperationStatus.OK
    assert paths.glossary_conflicts.is_file()
    
    # Assert existing canonical term is PRESERVED
    glossary = load_yaml_model(paths.glossary, BookGlossary)
    assert glossary.terms["林枫"].translation == "Lâm Phong Locked"
    
    # Assert conflict report populated
    conflict_report = load_yaml_model(paths.glossary_conflicts, GlossaryConflictReport)
    assert len(conflict_report.conflicts) == 1
    assert conflict_report.conflicts[0].term == "林枫"
    assert conflict_report.conflicts[0].existing_translation == "Lâm Phong Locked"
    assert conflict_report.conflicts[0].proposed_translation == "Lâm Phong New"
    assert conflict_report.conflicts[0].chapter_id == 2


def test_glossary_cli_merge_and_lock(books_root, metadata, catalog, style, tmp_path):
    from dich_truyen_agent.cli import build_parser, run_command
    from dich_truyen_agent.glossary import initialize_glossary_file
    from dich_truyen_agent.storage import load_yaml_model
    import yaml
    
    initialize_workspace(books_root, metadata, catalog, style)
    paths = workspace_paths(books_root, metadata.book_slug)
    
    # Initialize glossary with 1 term
    initialize_glossary_file(paths.root, {
        "林枫": {"translation": "Lâm Phong", "category": "character"}
    })
    
    # proposals file
    prop_file = tmp_path / "proposals.yaml"
    with prop_file.open("w", encoding="utf-8") as stream:
        yaml.safe_dump({
            "林枫": {"translation": "Lâm Phong", "category": "character"},
            "青云宗": {"translation": "Thanh Vân Tông", "category": "sect"}
        }, stream)
        
    parser = build_parser()
    
    # Run merge proposals
    args_merge = parser.parse_args([
        "merge-proposals",
        "--workspace", str(paths.root),
        "--chapter-id", "1",
        "--proposals", str(prop_file)
    ])
    result_merge = run_command(args_merge)
    assert result_merge.status == OperationStatus.OK
    
    # Assert merged successfully
    glossary = load_yaml_model(paths.glossary, BookGlossary)
    assert "青云宗" in glossary.terms
    assert glossary.terms["青云宗"].translation == "Thanh Vân Tông"
    assert glossary.terms["青云宗"].is_canonical is False
    
    # Run lock term
    args_lock = parser.parse_args([
        "lock-term",
        "--workspace", str(paths.root),
        "--term", "青云宗"
    ])
    result_lock = run_command(args_lock)
    assert result_lock.status == OperationStatus.OK
    
    # Assert locked successfully
    glossary = load_yaml_model(paths.glossary, BookGlossary)
    assert glossary.terms["青云宗"].is_canonical is True
    assert glossary.terms["青云宗"].source == "manual"


def test_real_book_glossary_lifecycle():
    from dich_truyen_agent.glossary import initialize_glossary_file, merge_glossary_proposals, lock_glossary_term
    from dich_truyen_agent.storage import load_yaml_model
    import shutil
    
    real_book_root = Path("books/jian-lai-phase2-check")
    if not real_book_root.is_dir():
        pytest.skip("books/jian-lai-phase2-check not found on disk")
    paths = workspace_paths(Path("books"), "jian-lai-phase2-check")
    
    # 1. Verify inspect_workspace succeeds initially on real book
    inspect_result = inspect_workspace(real_book_root)
    assert inspect_result.status == OperationStatus.OK
    
    # Setup cleanup block
    created_files = []
    
    try:
        # Create glossary-snapshots dir explicitly
        paths.glossary_snapshots.mkdir(parents=True, exist_ok=True)
        
        # 2. Write initial glossary file
        terms_extracted = {
            "陈平安": {"translation": "Trần Bình An", "category": "character", "note": "Main character"},
            "落魄山": {"translation": "Lạc Phách Sơn", "category": "location"}
        }
        
        result_init = initialize_glossary_file(real_book_root, terms_extracted)
        assert result_init.status == OperationStatus.OK
        assert paths.glossary.is_file()
        created_files.append(paths.glossary)
        
        # 3. Simulate progressive merges
        proposals_ch1 = {
            "陈平安": GlossaryTerm(translation="Trần Bình An", category="character", source="ch1"),
            "宁姚": GlossaryTerm(translation="Ninh Dao", category="character", source="ch1")
        }
        
        result_merge = merge_glossary_proposals(real_book_root, 1, proposals_ch1)
        assert result_merge.status == OperationStatus.OK
        assert (paths.glossary_snapshots / "chapter-0001.yaml").is_file()
        
        # Verify merged glossary
        glossary = load_yaml_model(paths.glossary, BookGlossary)
        assert "宁姚" in glossary.terms
        assert glossary.terms["宁姚"].translation == "Ninh Dao"
        
        # 4. Lock term
        result_lock = lock_glossary_term(real_book_root, "宁姚")
        assert result_lock.status == OperationStatus.OK
        
        glossary = load_yaml_model(paths.glossary, BookGlossary)
        assert glossary.terms["宁姚"].is_canonical is True
        
        # 5. Mismatching merge (trigger conflict)
        proposals_ch2 = {
            "宁姚": GlossaryTerm(translation="Ninh Dao New", category="character", source="ch2")
        }
        result_conflict = merge_glossary_proposals(real_book_root, 2, proposals_ch2)
        assert result_conflict.status == OperationStatus.OK
        assert paths.glossary_conflicts.is_file()
        created_files.append(paths.glossary_conflicts)
        
        # Check canonical preserved
        glossary = load_yaml_model(paths.glossary, BookGlossary)
        assert glossary.terms["宁姚"].translation == "Ninh Dao"
        
        conflict_report = load_yaml_model(paths.glossary_conflicts, GlossaryConflictReport)
        assert len(conflict_report.conflicts) == 1
        assert conflict_report.conflicts[0].term == "宁姚"
        
    finally:
        # Strict Cleanup to preserve git state of books/jian-lai-phase2-check
        for file_path in created_files:
            if file_path.is_file():
                file_path.unlink()
        if paths.glossary_snapshots.is_dir():
            shutil.rmtree(paths.glossary_snapshots)





