from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup

from dich_truyen_agent.browser import PlaywrightRenderer
from dich_truyen_agent.crawl_profiles import load_active_crawl_profile
from dich_truyen_agent.crawler import (
    StaticCrawler,
    decode_html,
    discover_catalog,
    extract_chapter,
    to_chapter_catalog,
    validate_discovered_catalog,
)
from dich_truyen_agent.models import (
    BookMetadata,
    BookState,
    ChapterCatalog,
    ChapterState,
    CrawlSettings,
    OperationResult,
    OperationStatus,
    ProgressSummary,
    StageRecord,
    StageStatus,
    TranslationStyle,
)
from dich_truyen_agent.paths import validate_workspace_relative_path, workspace_paths
from dich_truyen_agent.scope import (
    build_source_scope,
    compute_source_digest,
    load_source_scope,
    save_source_scope,
    validate_scope_catalog,
)
from dich_truyen_agent.storage import (
    atomic_write_text,
    atomic_write_yaml,
    find_orphan_temp_files,
    load_yaml_model,
    sha256_file,
)
from dich_truyen_agent.styles import load_selected_style
from dich_truyen_agent.workspace import initialize_workspace


def is_recoverable_exception(exc: Exception) -> bool:
    """Classify if an HTTP exception is recoverable and worthy of retry."""
    if isinstance(
        exc,
        (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
        ),
    ):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


def detect_anti_bot_blocking(html: str, status_code: int = 200) -> str | None:
    """Scan HTML page content and status code for anti-bot or CAPTCHA blocking challenges."""
    if status_code in (403, 429):
        return f"access denied (HTTP {status_code})"

    lower_html = html.lower()
    markers = [
        "cloudflare protection",
        "captcha",
        "recaptcha",
        "hcaptcha",
        "security check",
        "verify you are human",
        "robot check",
        "anti-bot",
        "ddos protection",
        "please turn on javascript",
        "just a moment",
    ]
    for marker in markers:
        if marker in lower_html:
            return f"anti-bot block detected ({marker})"
    return None


def extract_title_from_index_html(html_content: str) -> str | None:
    """Extract usable book title from index HTML, rejecting generic titles."""
    if not html_content:
        return None
    soup = BeautifulSoup(html_content, "lxml")
    title_tag = soup.find("title")
    if not title_tag:
        return None
    raw_title = title_tag.get_text().strip()
    cleaned = re.split(r"最新章节|无弹窗|[-_|_]|–", raw_title)[0].strip()
    if not cleaned or cleaned.lower() in {"novel", "index", "home", "untitled"}:
        return None
    return cleaned


def extract_catalog_intro(
    html_content: str | None,
    chapter_link_selector: str | None = None,
    max_chars: int = 3000,
) -> str:
    """Extract bounded introductory text from index HTML, stripping chapter lists and scripts."""
    if not html_content or not html_content.strip():
        return ""
    soup = BeautifulSoup(html_content, "lxml")

    # 1. Remove unwanted tags
    for tag in soup.find_all(["script", "style", "link", "noscript", "meta"]):
        tag.decompose()

    # 2. Remove chapter link list container or links if selector is provided
    if chapter_link_selector:
        try:
            for link in soup.select(chapter_link_selector):
                link.decompose()
        except Exception:
            pass

    # 3. Extract text
    text = soup.get_text(separator="\n", strip=True)
    cleaned = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return cleaned[:max_chars]


async def discover_initial_title(
    project_root: Path,
    source_url: str,
    workspace_root: Path | None = None,
    static_crawler_class: Any = None,
    renderer_instance: Any = None,
) -> str | None:
    """Discover index page and extract book title using static crawler or Playwright fallback."""
    try:
        profile_source = load_active_crawl_profile(
            project_root, workspace_root or Path("."), source_url
        )
    except Exception:
        return None

    crawler_cls = static_crawler_class or StaticCrawler
    crawler = crawler_cls(CrawlSettings())
    html_content = None
    try:
        raw_bytes, http_charset = await crawler.fetch(source_url)
        decoded, _, _ = decode_html(
            raw_bytes, profile_source.profile.encoding.index, http_charset
        )
        if not detect_anti_bot_blocking(decoded):
            html_content = decoded
    except Exception:
        html_content = None
    finally:
        await crawler.close()

    if not html_content:
        try:
            renderer = renderer_instance or PlaywrightRenderer()
            html_content = await renderer.render(
                source_url, profile_source.profile, purpose="index"
            )
        except Exception:
            return None

    title = extract_title_from_index_html(html_content)
    if workspace_root and html_content:
        selector = getattr(profile_source.profile.index, "chapter_link_selector", None)
        intro_text = extract_catalog_intro(
            html_content, chapter_link_selector=selector, max_chars=3000
        )
        if intro_text:
            reports_dir = workspace_root / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            (reports_dir / "catalog_intro.txt").write_text(intro_text, encoding="utf-8")
    return title


async def crawl_book(
    books_root: Path,
    book_slug: str,
    source_url: str,
    project_root: Path,
    style_name: str | None = None,
    max_chapters: int = 0,
    scope_limit: int | None = None,
    chapter_delay_seconds: float = 3.0,
    sleeper_fn=None,
    static_crawler_class=None,
    renderer_instance=None,
) -> OperationResult:
    """Sequentially discover, validate, and download chapter bodies autonomously."""
    books_root = Path(books_root).resolve()
    project_root = Path(project_root).resolve()
    paths = workspace_paths(books_root, book_slug)

    if scope_limit is not None and scope_limit <= 0:
        return OperationResult(
            status=OperationStatus.BLOCKED,
            reason=f"scope_limit must be positive, got {scope_limit}",
        )
    if scope_limit is not None and max_chapters > 0:
        return OperationResult(
            status=OperationStatus.BLOCKED,
            reason="cannot specify both scope_limit and max_chapters",
        )

    # Initialize crawler settings
    settings = CrawlSettings(
        max_chapters=max_chapters,
        chapter_delay_seconds=chapter_delay_seconds,
    )

    crawler_cls = static_crawler_class or StaticCrawler
    crawler = crawler_cls(settings)

    # 1. Discover active profile
    try:
        profile_source = load_active_crawl_profile(project_root, paths.root, source_url)
    except Exception as e:
        await crawler.close()
        return OperationResult(
            status=OperationStatus.ERROR,
            reason=f"failed to load crawl profile: {e}",
            orphan_temp_paths=(
                [str(p) for p in find_orphan_temp_files(paths.root)]
                if paths.root.exists()
                else []
            ),
        )

    # 2. Workspace Initialization / Resume
    is_new = not paths.root.exists()
    has_empty_catalog = False
    book_metadata: BookMetadata | None = None
    existing_catalog: ChapterCatalog | None = None
    if not is_new:
        if paths.book.is_file():
            try:
                book_metadata = load_yaml_model(paths.book, BookMetadata)
            except Exception:
                pass
        try:
            existing_catalog = load_yaml_model(paths.chapters, ChapterCatalog)
            if not existing_catalog.chapters:
                has_empty_catalog = True
        except Exception:
            has_empty_catalog = True

    # Validate existing nonempty catalog against scope
    if not is_new and not has_empty_catalog and existing_catalog is not None:
        if book_metadata is not None and book_metadata.scope_managed:
            if not paths.source_scope.is_file():
                await crawler.close()
                return OperationResult(
                    status=OperationStatus.BLOCKED,
                    reason="scope-managed workspace is missing reports/source-scope.yaml; operator repair required",
                )
            try:
                scope_record = load_source_scope(paths.source_scope)
                val_res = validate_scope_catalog(scope_record, existing_catalog)
                if not val_res.is_valid:
                    await crawler.close()
                    return OperationResult(
                        status=OperationStatus.BLOCKED,
                        reason=f"scope record mismatch: {val_res.reason}; operator repair required",
                    )
                if (
                    scope_limit is not None
                    and scope_limit != scope_record.requested_limit
                ):
                    await crawler.close()
                    return OperationResult(
                        status=OperationStatus.BLOCKED,
                        reason=f"cannot change frozen scope limit from {scope_record.requested_limit} to {scope_limit}",
                    )
            except Exception as e:
                await crawler.close()
                return OperationResult(
                    status=OperationStatus.BLOCKED,
                    reason=f"failed to load source scope: {e}; operator repair required",
                )
        else:
            if scope_limit is not None:
                await crawler.close()
                return OperationResult(
                    status=OperationStatus.BLOCKED,
                    reason="cannot apply scope_limit to an existing legacy workspace with nonempty catalog",
                )

    rebuilt_from_scope = False
    try:
        if is_new or has_empty_catalog:
            # For new book or empty catalog, we fetch index to build catalog & metadata
            html_content = None
            try:
                raw_bytes, http_charset = await crawler.fetch(source_url)
                html_content, chosen_encoding, provenance = decode_html(
                    raw_bytes, profile_source.profile.encoding.index, http_charset
                )
                challenge = detect_anti_bot_blocking(html_content)
                if challenge:
                    raise ValueError(f"anti-bot block on index page: {challenge}")
            except Exception as e:
                # Fallback to Playwright for index page
                try:
                    fallback_renderer = renderer_instance or PlaywrightRenderer()
                    html_content = await fallback_renderer.render(
                        source_url,
                        profile_source.profile,
                        purpose="index",
                    )
                except Exception as playwright_err:
                    # Crash recovery: if index fetch fails but valid scope record exists, rebuild selected catalog
                    rebuilt_from_scope = False
                    if has_empty_catalog and paths.source_scope.is_file():
                        try:
                            scope_record = load_source_scope(paths.source_scope)
                            selected_discovered = scope_record.entries[
                                : scope_record.selected_count
                            ]
                            rebuilt_catalog = to_chapter_catalog(selected_discovered)
                            rebuilt_state = BookState(
                                chapters=[
                                    ChapterState(chapter_id=ch.chapter_id)
                                    for ch in rebuilt_catalog.chapters
                                ]
                            )
                            atomic_write_yaml(paths.chapters, rebuilt_catalog)
                            atomic_write_yaml(paths.state, rebuilt_state)
                            has_empty_catalog = False
                            rebuilt_from_scope = True
                        except Exception:
                            pass
                    if not rebuilt_from_scope and (has_empty_catalog or is_new):
                        await crawler.close()
                        return OperationResult(
                            status=OperationStatus.ERROR,
                            reason=f"failed to fetch book index (static fetch failed with: {e}, playwright fallback failed with: {playwright_err})",
                        )

            if not rebuilt_from_scope:
                # Discover and validate catalog
                discovered = discover_catalog(
                    html_content, source_url, profile_source.profile
                )
                if not discovered:
                    # Try Playwright fallback if we haven't already used it
                    if "fallback_renderer" not in locals():
                        try:
                            fallback_renderer = (
                                renderer_instance or PlaywrightRenderer()
                            )
                            html_content = await fallback_renderer.render(
                                source_url,
                                profile_source.profile,
                                purpose="index",
                            )
                            discovered = discover_catalog(
                                html_content, source_url, profile_source.profile
                            )
                        except Exception:
                            pass

                    if not discovered:
                        if has_empty_catalog and paths.source_scope.is_file():
                            try:
                                scope_record = load_source_scope(paths.source_scope)
                                selected_discovered = scope_record.entries[
                                    : scope_record.selected_count
                                ]
                                rebuilt_catalog = to_chapter_catalog(
                                    selected_discovered
                                )
                                rebuilt_state = BookState(
                                    chapters=[
                                        ChapterState(chapter_id=ch.chapter_id)
                                        for ch in rebuilt_catalog.chapters
                                    ]
                                )
                                atomic_write_yaml(paths.chapters, rebuilt_catalog)
                                atomic_write_yaml(paths.state, rebuilt_state)
                                has_empty_catalog = False
                                rebuilt_from_scope = True
                            except Exception:
                                pass
                        if not rebuilt_from_scope:
                            await crawler.close()
                            return OperationResult(
                                status=OperationStatus.BLOCKED,
                                reason="discovered catalog contains zero chapters; selector rule might be broken",
                            )

            if not rebuilt_from_scope:
                findings = validate_discovered_catalog(discovered)
                if findings["blockers"]:
                    await crawler.close()
                    return OperationResult(
                        status=OperationStatus.BLOCKED,
                        reason=f"catalog discovery blocked: {findings['blockers']}",
                    )

                if html_content:
                    catalog_intro_text = extract_catalog_intro(
                        html_content,
                        chapter_link_selector=getattr(
                            profile_source.profile.index, "chapter_link_selector", None
                        ),
                        max_chars=3000,
                    )
                    if catalog_intro_text:
                        paths.reports.mkdir(parents=True, exist_ok=True)
                        intro_file = paths.reports / "catalog_intro.txt"
                        intro_file.write_text(catalog_intro_text, encoding="utf-8")

                # Check if scope record already existed and source changed
                if paths.source_scope.is_file():
                    try:
                        existing_scope = load_source_scope(paths.source_scope)
                        if (
                            compute_source_digest(discovered)
                            != existing_scope.source_digest
                        ):
                            await crawler.close()
                            return OperationResult(
                                status=OperationStatus.BLOCKED,
                                reason="catalog-changed: source catalog digest differs from frozen scope record",
                            )
                    except Exception as e:
                        if "catalog-changed" in str(e):
                            raise

                is_scoped = (scope_limit is not None) or (
                    book_metadata is not None and book_metadata.scope_managed
                )
                if is_scoped:
                    try:
                        effective_limit = scope_limit
                        if effective_limit is None and paths.source_scope.is_file():
                            existing_scope = load_source_scope(paths.source_scope)
                            effective_limit = existing_scope.requested_limit
                        scope_record = build_source_scope(
                            discovered, source_url, limit=effective_limit
                        )
                    except Exception as exc:
                        await crawler.close()
                        return OperationResult(
                            status=OperationStatus.BLOCKED,
                            reason=f"failed to build source scope: {exc}",
                        )
                    selected_discovered = discovered[: scope_record.selected_count]
                    catalog = to_chapter_catalog(selected_discovered)
                    scope_managed = True
                else:
                    catalog = to_chapter_catalog(discovered)
                    scope_managed = False

                if is_new:
                    # Extract book title automatically
                    extracted = extract_title_from_index_html(html_content)
                    title = extracted if extracted else book_slug

                    metadata = BookMetadata(
                        book_slug=book_slug,
                        source_url=source_url,
                        title=title,
                        author="Unknown",
                        scope_managed=scope_managed,
                    )

                    # Setup style path
                    style_path = None
                    if style_name:
                        style_path = (
                            project_root / "templates" / "styles" / f"{style_name}.yaml"
                        )
                        if not style_path.exists():
                            style_path = (
                                project_root / "templates" / "styles" / f"{style_name}"
                            )
                    style = load_selected_style(project_root, style_path)

                    init_res = initialize_workspace(
                        books_root, metadata, catalog, style
                    )
                    if init_res.status is OperationStatus.BLOCKED:
                        await crawler.close()
                        return init_res

                    # Ensure source-scope is saved in initialized workspace
                    if is_scoped:
                        save_source_scope(paths.source_scope, scope_record)

                    # Install profile locally
                    snapshot_local = paths.root / "crawl-profile.yaml"
                    atomic_write_yaml(snapshot_local, profile_source.profile)
                else:
                    if is_scoped:
                        save_source_scope(paths.source_scope, scope_record)
                    if scope_managed:
                        if book_metadata is None and paths.book.is_file():
                            book_metadata = load_yaml_model(paths.book, BookMetadata)
                        if book_metadata is not None:
                            book_metadata.scope_managed = True
                            atomic_write_yaml(paths.book, book_metadata)
                    state = BookState(
                        chapters=[
                            ChapterState(chapter_id=chapter.chapter_id)
                            for chapter in catalog.chapters
                        ]
                    )
                    atomic_write_yaml(paths.chapters, catalog)
                    atomic_write_yaml(paths.state, state)
                    # Install profile locally if not present
                    snapshot_local = paths.root / "crawl-profile.yaml"
                    if not snapshot_local.exists():
                        atomic_write_yaml(snapshot_local, profile_source.profile)

        else:
            # Existing workspace check
            inspect_res = inspect_workspace_for_crawl(paths.root)
            if inspect_res.status is OperationStatus.BLOCKED:
                await crawler.close()
                return inspect_res

    except Exception as e:
        await crawler.close()
        return OperationResult(
            status=OperationStatus.ERROR,
            reason=f"workspace setup failed: {e}",
        )

    # 3. Reload current state and catalog
    try:
        catalog = load_yaml_model(paths.chapters, ChapterCatalog)
        state = load_yaml_model(paths.state, BookState)
    except Exception as e:
        await crawler.close()
        return OperationResult(
            status=OperationStatus.ERROR,
            reason=f"failed to load catalog or state: {e}",
        )

    # Determine scope: max_chapters limits chapter downloads only
    scope_limit = settings.max_chapters
    target_chapters = catalog.chapters
    if scope_limit > 0:
        target_chapters = catalog.chapters[:scope_limit]

    # Map target chapters to ChapterState records
    state_by_id = {c.chapter_id: c for c in state.chapters}

    # Fill in any missing chapter state records
    modified_state = False
    for tc in target_chapters:
        if tc.chapter_id not in state_by_id:
            c_state = ChapterState(chapter_id=tc.chapter_id)
            state.chapters.append(c_state)
            state_by_id[tc.chapter_id] = c_state
            modified_state = True

    if modified_state:
        atomic_write_yaml(paths.state, state)

    # 4. Sequential body download
    completed_in_run = 0
    total_completed = 0

    # Progress helper
    def get_progress() -> ProgressSummary:
        comp = sum(1 for ch in state.chapters if ch.raw.status is StageStatus.COMPLETED)
        return ProgressSummary(
            completed=comp,
            total=len(target_chapters),
            current_chapter_id=None,
        )

    renderer = renderer_instance or PlaywrightRenderer()
    sleep = sleeper_fn or asyncio.sleep

    try:
        for index, tc in enumerate(target_chapters):
            chapter_state = state_by_id[tc.chapter_id]

            # Resume: check completed raw artifacts
            if chapter_state.raw.status is StageStatus.COMPLETED:
                raw_file = validate_workspace_relative_path(
                    paths.root, chapter_state.raw.canonical_path or ""
                )
                if (
                    raw_file.is_file()
                    and sha256_file(raw_file) == chapter_state.raw.sha256
                ):
                    total_completed += 1
                    continue
                else:
                    # Invalidate completed status on hash mismatch
                    chapter_state.raw = StageRecord(status=StageStatus.PENDING)
                    atomic_write_yaml(paths.state, state)

            # Mark current chapter progress
            progress_summary = get_progress()
            progress_summary.current_chapter_id = tc.chapter_id

            # Crawl chapter logic with retries and fallback
            attempts = 0
            max_attempts = settings.max_attempts
            html_body = None
            encoding_info = ("utf-8", "fallback")
            use_playwright = False
            last_error = ""

            while attempts < max_attempts:
                attempts += 1
                try:
                    if use_playwright:
                        html_body = await renderer.render(
                            tc.source_url,
                            profile_source.profile,
                            purpose="chapter",
                        )
                        encoding_info = ("utf-8", "browser_render")
                    else:
                        raw_bytes, http_charset = await crawler.fetch(tc.source_url)
                        html_body, enc, prov = decode_html(
                            raw_bytes,
                            profile_source.profile.encoding.chapter,
                            http_charset,
                        )
                        encoding_info = (enc, prov)

                    # Check anti-bot challenges
                    challenge = detect_anti_bot_blocking(html_body)
                    if challenge:
                        if not use_playwright:
                            use_playwright = True
                            attempts -= 1  # Offset attempt counter to allow browser fallback immediately
                            continue
                        await crawler.close()
                        return OperationResult(
                            status=OperationStatus.BLOCKED,
                            reason=f"Chapter {tc.chapter_id} stopped: anti-bot/CAPTCHA challenge detected on attempt {attempts}: {challenge}",
                            progress=progress_summary,
                            orphan_temp_paths=[
                                str(p) for p in find_orphan_temp_files(paths.root)
                            ],
                        )

                    # Extraction validation
                    try:
                        # Extract chapter validates threshold internally
                        extracted = extract_chapter(
                            html_body,
                            tc.source_url,
                            profile_source.profile,
                            encoding_info,
                        )
                        break  # Extraction succeeded! Break retry loop
                    except Exception as extraction_err:
                        # Check if extraction failed due to missing rendered JS content
                        is_empty_or_small = (
                            "selector" in str(extraction_err).lower()
                            or "threshold" in str(extraction_err).lower()
                        )
                        if not use_playwright and is_empty_or_small:
                            # Switch transport to Playwright and try again immediately (counts as one retry step)
                            use_playwright = True
                            attempts -= 1  # Offset attempt counter to allow browser fallback immediately
                            continue
                        raise extraction_err

                except Exception as exc:
                    last_error = str(exc)
                    # Non-recoverable error stops batch immediately
                    if not is_recoverable_exception(exc) and not use_playwright:
                        if isinstance(
                            exc, httpx.HTTPStatusError
                        ) and exc.response.status_code in (403, 429):
                            use_playwright = True
                            attempts -= 1  # Offset attempt counter to allow browser fallback immediately
                            continue

                    if not is_recoverable_exception(exc):
                        chapter_state.raw = StageRecord(
                            status=StageStatus.ERROR,
                            error=f"Non-recoverable crawl error: {exc}",
                            updated_at=datetime.now(UTC),
                        )
                        atomic_write_yaml(paths.state, state)
                        await crawler.close()
                        return OperationResult(
                            status=OperationStatus.ERROR,
                            reason=f"Chapter {tc.chapter_id} sequential crawl stopped due to non-recoverable error: {exc}",
                            progress=progress_summary,
                            orphan_temp_paths=[
                                str(p) for p in find_orphan_temp_files(paths.root)
                            ],
                        )

                    # Backoff sleep before retry if recoverable
                    if attempts < max_attempts:
                        backoff = settings.backoff_seconds * (2 ** (attempts - 1))
                        await sleep(backoff)

            else:
                # Retries exhausted
                chapter_state.raw = StageRecord(
                    status=StageStatus.ERROR,
                    error=f"Crawl retries exhausted. Last error: {last_error}",
                    updated_at=datetime.now(UTC),
                )
                atomic_write_yaml(paths.state, state)
                await crawler.close()
                return OperationResult(
                    status=OperationStatus.ERROR,
                    reason=f"Chapter {tc.chapter_id} sequential crawl stopped after {max_attempts} exhausted attempts. Last error: {last_error}",
                    progress=progress_summary,
                    orphan_temp_paths=[
                        str(p) for p in find_orphan_temp_files(paths.root)
                    ],
                )

            # 5. Success: Save raw file atomically and update state
            raw_filename = tc.raw_filename
            relative_raw_path = f"raw/{raw_filename}"
            full_raw_path = paths.root / relative_raw_path

            # Format raw body cleanly: Title followed by paragraph text
            full_text_content = f"{extracted.title}\n\n{extracted.text}"
            atomic_write_text(full_raw_path, full_text_content)

            h = sha256_file(full_raw_path)
            chapter_state.raw = StageRecord(
                status=StageStatus.COMPLETED,
                canonical_path=relative_raw_path,
                sha256=h,
                updated_at=datetime.now(UTC),
            )
            atomic_write_yaml(paths.state, state)
            completed_in_run += 1
            total_completed += 1

            # Conservative pacing delay (politeness rule): sleep between successfully downloaded chapters
            # Do not sleep after the last target chapter
            if index < len(target_chapters) - 1:
                await sleep(settings.chapter_delay_seconds)

    finally:
        await crawler.close()
        if hasattr(renderer, "close"):
            await renderer.close()

    # Successful completion of download scope
    return OperationResult(
        status=OperationStatus.OK,
        reason=f"Crawl completed. Discovered: {len(catalog.chapters)}, Downloaded scope: {completed_in_run} in this run (Total completed: {total_completed}/{len(target_chapters)})",
        progress=get_progress(),
        orphan_temp_paths=[str(p) for p in find_orphan_temp_files(paths.root)],
    )


def inspect_workspace_for_crawl(workspace_root: Path) -> OperationResult:
    """Modified inspect_workspace focused on robust resume for crawl phase."""
    paths = workspace_paths(workspace_root.parent, workspace_root.name)
    try:
        load_yaml_model(paths.book, BookMetadata)
        load_yaml_model(paths.chapters, ChapterCatalog)
        load_yaml_model(paths.state, BookState)
        load_yaml_model(paths.style, TranslationStyle)
    except Exception as error:
        return OperationResult(
            status=OperationStatus.BLOCKED,
            reason=f"invalid crawl workspace: {error}",
            orphan_temp_paths=[str(p) for p in find_orphan_temp_files(paths.root)],
        )
    return OperationResult(
        status=OperationStatus.OK, reason="workspace crawl inspect passed"
    )
