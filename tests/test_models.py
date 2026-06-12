from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from dich_truyen_agent.models import (
    BookState,
    ChapterCatalog,
    ChapterCatalogEntry,
    ChapterState,
    CheckpointRecord,
    CrawlProfile,
    OperationResult,
    OperationStatus,
    StageRecord,
    StageStatus,
    TranslationSettings,
)


def catalog_entry(chapter_id: int = 1, suffix: str = "one") -> ChapterCatalogEntry:
    return ChapterCatalogEntry(
        chapter_id=chapter_id,
        slug=f"chapter-{suffix}",
        source_url=f"https://example.com/{suffix}",
        original_title=f"Chapter {suffix}",
        raw_filename=f"{chapter_id:04d}-{suffix}.txt",
        translation_filename=f"{chapter_id:04d}-{suffix}.txt",
    )


def test_catalog_round_trips() -> None:
    catalog = ChapterCatalog(chapters=[catalog_entry()])
    assert ChapterCatalog.model_validate(catalog.model_dump()) == catalog


@pytest.mark.parametrize("field", ["chapter_id", "raw_filename", "translation_filename"])
def test_catalog_rejects_duplicate_identity_fields(field: str) -> None:
    first = catalog_entry()
    second = catalog_entry(2, "two")
    setattr(second, field, getattr(first, field))
    with pytest.raises(ValidationError):
        ChapterCatalog(chapters=[first, second])


def test_state_rejects_duplicate_chapter_ids() -> None:
    state = ChapterState(chapter_id=1)
    with pytest.raises(ValidationError):
        BookState(chapters=[state, state])


def test_unknown_checkpoint_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CheckpointRecord(
            checkpoint_type="unexpected",
            approved_at=datetime.now(UTC),
            report_path="reports/review.yaml",
        )


def test_operation_result_is_compact() -> None:
    result = OperationResult(status=OperationStatus.OK, reason="ready")
    assert "chapter_body" not in OperationResult.model_fields
    assert set(result.model_dump()) == {
        "status",
        "reason",
        "progress",
        "report_paths",
        "approval_path",
        "orphan_temp_paths",
        "data",
    }
    assert result.data == {}


def test_translation_settings_default_batch_size() -> None:
    settings = TranslationSettings(_env_file=None)
    assert settings.batch_size == 5


def test_translation_settings_reads_environment_batch_size(monkeypatch) -> None:
    monkeypatch.setenv("DICH_TRUYEN_TRANSLATION_BATCH_SIZE", "12")

    settings = TranslationSettings(_env_file=None)

    assert settings.batch_size == 12


def test_translation_settings_reads_dotenv_batch_size(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DICH_TRUYEN_TRANSLATION_BATCH_SIZE=8\n", encoding="utf-8")

    settings = TranslationSettings(_env_file=env_file)

    assert settings.batch_size == 8


def test_translation_settings_rejects_invalid_batch_size(monkeypatch) -> None:
    monkeypatch.setenv("DICH_TRUYEN_TRANSLATION_BATCH_SIZE", "0")

    with pytest.raises(ValidationError):
        TranslationSettings(_env_file=None)


def test_completed_stage_record_requires_hash_and_path() -> None:
    with pytest.raises(ValidationError):
        StageRecord(status=StageStatus.COMPLETED)


def test_crawl_profile_defaults_to_browser_disabled() -> None:
    profile = CrawlProfile(
        domain="example.com",
        index={"chapter_link_selector": ".chapters a"},
        chapter={"title_selector": "h1", "content_selector": "#content"},
    )

    assert profile.browser.enabled is False
    assert profile.browser.strategy is None
    assert profile.browser.viewport.width == 1280
    assert profile.browser.viewport.height == 800
    assert profile.browser.navigation.wait_until == "domcontentloaded"
    assert profile.browser.navigation.timeout_milliseconds == 30000
    assert profile.browser.actions == []


def test_crawl_browser_profile_accepts_declarative_warmups_and_actions() -> None:
    profile = CrawlProfile(
        domain="www.69shuba.com",
        index={"chapter_link_selector": "#catalog a"},
        chapter={"title_selector": "h1", "content_selector": ".txtnav"},
        browser={
            "enabled": True,
            "strategy": "noop",
            "launch_args": ["--disable-blink-features=AutomationControlled"],
            "user_agent": "Mozilla/5.0",
            "init_scripts": ["delete Object.getPrototypeOf(navigator).webdriver;"],
            "challenge": {
                "title_markers": ["just a moment", "正在验证"],
                "max_wait_seconds": 15,
                "poll_seconds": 1.0,
            },
            "session": {
                "warmups": [
                    {
                        "url_pattern": r"https?://(?:www\.)?69shuba\.com/txt/(?P<book_id>\d+)/\d+",
                        "warmup_url": "https://www.69shuba.com/book/{book_id}/",
                    }
                ]
            },
            "actions": [
                {
                    "purpose": "index",
                    "action": "click",
                    "selector": ".catalog-all",
                    "wait_for_selector": ".clist .u-chapter li a",
                    "timeout_milliseconds": 10000,
                }
            ],
        },
    )

    assert profile.browser.enabled is True
    assert profile.browser.strategy == "noop"
    assert profile.browser.session.warmups[0].warmup_url.endswith("{book_id}/")
    assert profile.browser.actions[0].purpose == "index"
    assert profile.browser.actions[0].wait_for_selector == ".clist .u-chapter li a"


def test_crawl_browser_profile_rejects_invalid_action_type() -> None:
    with pytest.raises(ValidationError):
        CrawlProfile(
            domain="example.com",
            index={"chapter_link_selector": ".chapters a"},
            chapter={"title_selector": "h1", "content_selector": "#content"},
            browser={"actions": [{"action": "hover", "selector": ".x"}]},
        )


def test_crawl_browser_profile_rejects_click_without_selector() -> None:
    with pytest.raises(ValidationError, match="selector"):
        CrawlProfile(
            domain="example.com",
            index={"chapter_link_selector": ".chapters a"},
            chapter={"title_selector": "h1", "content_selector": "#content"},
            browser={"actions": [{"action": "click"}]},
        )


def test_crawl_browser_profile_rejects_unknown_warmup_placeholder() -> None:
    with pytest.raises(ValidationError, match="unknown warmup placeholder"):
        CrawlProfile(
            domain="example.com",
            index={"chapter_link_selector": ".chapters a"},
            chapter={"title_selector": "h1", "content_selector": "#content"},
            browser={
                "session": {
                    "warmups": [
                        {
                            "url_pattern": r"https://example\.com/book/(?P<book_id>\d+)",
                            "warmup_url": "https://example.com/book/{chapter_id}/",
                        }
                    ]
                }
            },
        )
