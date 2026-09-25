from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml

from dich_truyen_agent.crawler import (
    decode_html,
    discover_catalog,
    extract_chapter,
    validate_discovered_catalog,
)
from dich_truyen_agent.models import (
    BookMetadata,
    ChapterCatalog,
    CrawlProfile,
    OperationResult,
    OperationStatus,
)
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.storage import load_yaml_model


DEFAULT_PROBE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/133.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def probe_crawl_profile(
    workspace_root: Path,
    candidate_profile_path: Path,
    *,
    client: httpx.Client | None = None,
) -> OperationResult:
    """Read-only audit of a candidate crawl profile against the workspace source URL."""
    try:
        workspace_root = Path(workspace_root).resolve()
        candidate_profile_path = Path(candidate_profile_path).resolve()
        paths = workspace_paths(workspace_root.parent, workspace_root.name)

        if not candidate_profile_path.is_file():
            return OperationResult(
                status=OperationStatus.BLOCKED,
                reason=f"candidate profile file not found: {candidate_profile_path}",
            )

        # 1. Validate candidate profile syntax and schema
        try:
            with candidate_profile_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            candidate = CrawlProfile.model_validate(data)
        except Exception as error:
            return OperationResult(
                status=OperationStatus.BLOCKED,
                reason=f"candidate profile schema validation failed: {error}",
            )

        if not paths.book.is_file():
            return OperationResult(
                status=OperationStatus.BLOCKED,
                reason="workspace metadata book.yaml is missing",
            )
        metadata = load_yaml_model(paths.book, BookMetadata)

        # 2. Domain check
        source_host = (urlparse(metadata.source_url).hostname or "").lower()
        candidate_domain = candidate.domain.lower()
        if candidate_domain != source_host and not source_host.endswith(f".{candidate_domain}"):
            return OperationResult(
                status=OperationStatus.BLOCKED,
                reason=f"domain mismatch: candidate domain '{candidate.domain}' does not match source host '{source_host}'",
            )

        # 3. Fetch index page
        close_client = False
        if client is None:
            active_client = httpx.Client(headers=DEFAULT_PROBE_HEADERS, follow_redirects=True, timeout=15.0)
            close_client = True
        else:
            active_client = client

        try:
            resp = active_client.get(metadata.source_url)
            if resp.status_code >= 400:
                return OperationResult(
                    status=OperationStatus.BLOCKED,
                    reason=f"failed to fetch source URL (HTTP {resp.status_code}): {metadata.source_url}",
                )
            http_charset = resp.encoding
            raw_bytes = resp.content
        finally:
            if close_client:
                active_client.close()

        index_encoding = candidate.encoding.index if candidate.encoding else None
        html_content, _, _ = decode_html(raw_bytes, explicit_encoding=index_encoding, http_charset=http_charset)

        # 4. Discover catalog
        discovered = discover_catalog(html_content, metadata.source_url, candidate)
        if not discovered:
            return OperationResult(
                status=OperationStatus.BLOCKED,
                reason="probe failed: index selector extracted zero chapters from source URL",
            )

        findings = validate_discovered_catalog(discovered)
        if findings.get("blockers"):
            return OperationResult(
                status=OperationStatus.BLOCKED,
                reason=f"probe failed: catalog discovery has blockers: {findings['blockers']}",
            )

        # 5. Check catalog URL order with existing catalog
        if paths.chapters.is_file():
            try:
                existing_catalog = load_yaml_model(paths.chapters, ChapterCatalog)
                if existing_catalog.chapters:
                    if len(discovered) < len(existing_catalog.chapters):
                        return OperationResult(
                            status=OperationStatus.BLOCKED,
                            reason="catalog-changed: candidate discovered fewer chapters than existing catalog",
                        )
                    for idx, ex_ch in enumerate(existing_catalog.chapters):
                        disc_ch = discovered[idx]
                        if disc_ch.source_url != ex_ch.source_url:
                            return OperationResult(
                                status=OperationStatus.BLOCKED,
                                reason=(
                                    f"catalog-changed: chapter {idx + 1} URL '{disc_ch.source_url}' "
                                    f"does not match existing catalog URL '{ex_ch.source_url}'"
                                ),
                            )
            except Exception as e:
                return OperationResult(
                    status=OperationStatus.BLOCKED,
                    reason=f"failed to compare with existing catalog: {e}",
                )

        # 6. Sample first, middle, last chapter extraction
        sample_indices = [0]
        if len(discovered) > 2:
            sample_indices.append(len(discovered) // 2)
        if len(discovered) > 1:
            sample_indices.append(len(discovered) - 1)

        unique_samples = []
        seen_indices = set()
        for i in sample_indices:
            if i not in seen_indices:
                unique_samples.append(discovered[i])
                seen_indices.add(i)

        if close_client:
            active_client = httpx.Client(headers=DEFAULT_PROBE_HEADERS, follow_redirects=True, timeout=15.0)

        try:
            min_chars = candidate.validation.min_chapter_characters if candidate.validation else 1
            for sample in unique_samples:
                ch_resp = active_client.get(sample.source_url)
                if ch_resp.status_code >= 400:
                    return OperationResult(
                        status=OperationStatus.BLOCKED,
                        reason=f"probe failed: sample chapter fetch failed (HTTP {ch_resp.status_code}): {sample.source_url}",
                    )
                ch_bytes = ch_resp.content
                ch_encoding = candidate.encoding.chapter if candidate.encoding else None
                ch_html, _, _ = decode_html(ch_bytes, explicit_encoding=ch_encoding, http_charset=ch_resp.encoding)
                try:
                    extracted = extract_chapter(ch_html, sample.source_url, candidate)
                except ValueError as ve:
                    return OperationResult(
                        status=OperationStatus.BLOCKED,
                        reason=f"probe failed: sample chapter extraction failed: {ve}",
                    )

                if not extracted.title or not extracted.title.strip():
                    return OperationResult(
                        status=OperationStatus.BLOCKED,
                        reason=f"probe failed: title selector returned empty for sample {sample.source_url}",
                    )
                if not extracted.text or not extracted.text.strip():
                    return OperationResult(
                        status=OperationStatus.BLOCKED,
                        reason=f"probe failed: content selector returned empty for sample {sample.source_url}",
                    )
                content_len = len(extracted.text.strip())
                if content_len < min_chars:
                    return OperationResult(
                        status=OperationStatus.BLOCKED,
                        reason=f"probe failed: sample content length {content_len} below threshold {min_chars} for {sample.source_url}",
                    )
        finally:
            if close_client:
                active_client.close()

        return OperationResult(
            status=OperationStatus.OK,
            reason="crawl profile probe passed",
            data={
                "discovered_count": len(discovered),
                "samples_checked": len(unique_samples),
            },
        )
    except Exception as error:
        return OperationResult(
            status=OperationStatus.ERROR,
            reason=f"probe crawl profile failed with error: {error}",
        )
