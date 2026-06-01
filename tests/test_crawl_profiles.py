from pathlib import Path

import pytest
from pydantic import ValidationError
from yaml import YAMLError

from dich_truyen_agent.crawl_profiles import (
    load_active_crawl_profile,
    load_crawl_profile,
    promote_local_crawl_profile,
    shared_profile_path,
    snapshot_local_crawl_profile,
)
from dich_truyen_agent.models import CrawlProfile, CrawlSettings
from dich_truyen_agent.paths import workspace_paths


def profile_yaml(
    *,
    domain: str = "example.com",
    content_selector: str = "#content",
    extra: str = "",
) -> str:
    return (
        "schema_version: 1\n"
        f"domain: {domain}\n"
        "index:\n"
        "  chapter_link_selector: '.chapters a'\n"
        "  pagination_selector: null\n"
        "  list_section_selectors: []\n"
        "chapter:\n"
        "  title_selector: h1\n"
        f"  content_selector: '{content_selector}'\n"
        "  remove_selectors: [script, '.navigation']\n"
        "encoding:\n"
        "  index: gbk\n"
        "  chapter: gb2312\n"
        "validation:\n"
        "  min_chapter_characters: 20\n"
        f"{extra}"
    )


def write_shared_profile(project_root: Path, content: str | None = None) -> Path:
    path = project_root / "templates" / "crawl_profiles" / "example.com.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(content or profile_yaml(), encoding="utf-8")
    return path


def test_crawl_settings_lock_safe_defaults() -> None:
    settings = CrawlSettings(max_chapters=0)
    assert settings.max_chapters == 0
    assert settings.chapter_delay_seconds == 3


def test_workspace_paths_include_crawl_profile_and_report(books_root: Path) -> None:
    paths = workspace_paths(books_root, "demo-book")
    assert paths.crawl_profile == paths.root / "crawl-profile.yaml"
    assert paths.crawl_report == paths.reports / "crawl.yaml"


def test_shared_profile_loads_for_matching_http_source(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    workspace_root = tmp_path / "book"
    shared = write_shared_profile(project_root)

    source = load_active_crawl_profile(
        project_root, workspace_root, "https://example.com/book/index.html"
    )

    assert source.shared_path == shared
    assert source.local_path == workspace_root / "crawl-profile.yaml"
    assert source.active_path == shared
    assert source.is_local_override is False
    assert source.profile.domain == "example.com"


def test_local_override_wins_without_mutating_shared_until_explicit_promotion(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    workspace_root = tmp_path / "book"
    shared = write_shared_profile(project_root)
    original_shared = shared.read_bytes()
    local_profile = CrawlProfile.model_validate(
        {
            **load_crawl_profile(shared).model_dump(),
            "chapter": {
                **load_crawl_profile(shared).chapter.model_dump(),
                "content_selector": "#book-local-content",
            },
        }
    )

    local_path = snapshot_local_crawl_profile(workspace_root, local_profile)
    active = load_active_crawl_profile(
        project_root, workspace_root, "https://example.com/book/index.html"
    )

    assert active.active_path == local_path
    assert active.is_local_override is True
    assert active.profile.chapter.content_selector == "#book-local-content"
    assert shared.read_bytes() == original_shared

    promoted = promote_local_crawl_profile(project_root, workspace_root)

    assert promoted == shared
    assert load_crawl_profile(shared) == local_profile


@pytest.mark.parametrize(
    "content",
    [
        "!!python/object:builtins.object {}\n",
        "schema_version: [broken\n",
        profile_yaml(extra="unexpected: true\n"),
    ],
)
def test_profile_loader_rejects_unsafe_malformed_or_unknown_fields(
    tmp_path: Path, content: str
) -> None:
    path = tmp_path / "crawl-profile.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises((YAMLError, ValidationError)):
        load_crawl_profile(path)


@pytest.mark.parametrize(
    "domain",
    ["", ".", "..", "../example.com", r"..\example.com", "nested/example.com"],
)
def test_shared_profile_path_rejects_unsafe_domain(tmp_path: Path, domain: str) -> None:
    with pytest.raises(ValueError):
        shared_profile_path(tmp_path, domain)


def test_active_profile_rejects_wrong_domain(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    workspace_root = tmp_path / "book"
    write_shared_profile(project_root, profile_yaml(domain="evil.example"))

    with pytest.raises(ValueError, match="domain"):
        load_active_crawl_profile(
            project_root, workspace_root, "https://example.com/book/index.html"
        )


def test_active_local_override_rejects_wrong_domain(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    workspace_root = tmp_path / "book"
    write_shared_profile(project_root)
    workspace_root.mkdir()
    (workspace_root / "crawl-profile.yaml").write_text(
        profile_yaml(domain="evil.example"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="domain"):
        load_active_crawl_profile(
            project_root, workspace_root, "https://example.com/book/index.html"
        )


@pytest.mark.parametrize(
    "source_url",
    ["file:///tmp/book", "https://example.com.evil.test/book", "https:///book"],
)
def test_active_profile_rejects_unsupported_or_unmatched_urls(
    tmp_path: Path, source_url: str
) -> None:
    with pytest.raises(ValueError):
        load_active_crawl_profile(tmp_path, tmp_path / "book", source_url)
