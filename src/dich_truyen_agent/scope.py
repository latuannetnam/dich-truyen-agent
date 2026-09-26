from __future__ import annotations

import hashlib
import json
from pathlib import Path

from dich_truyen_agent.crawler import validate_discovered_catalog
from dich_truyen_agent.models import (
    ChapterCatalog,
    DiscoveredChapter,
    PersistedModel,
    SourceScopeRecord,
)
from dich_truyen_agent.storage import atomic_write_yaml, load_yaml_model


class ScopeValidationResult(PersistedModel):
    is_valid: bool
    reason: str | None = None

    def __bool__(self) -> bool:
        return self.is_valid


def compute_source_digest(entries: list[DiscoveredChapter]) -> str:
    canonical_entries = [
        {
            "position": e.position,
            "source_id": e.source_id,
            "source_url": e.source_url,
            "original_title": e.original_title,
            "parsed_ordinal": e.parsed_ordinal,
        }
        for e in entries
    ]
    payload = json.dumps(canonical_entries, sort_keys=True, ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def build_source_scope(
    discovered: list[DiscoveredChapter],
    source_url: str,
    limit: int | None = None,
) -> SourceScopeRecord:
    if not discovered:
        raise ValueError("discovered chapters must not be empty")

    validation = validate_discovered_catalog(discovered)
    if validation.get("blockers"):
        blockers = validation["blockers"]
        raise ValueError(f"discovered catalog has validation blockers: {blockers}")

    source_count = len(discovered)
    if limit is not None:
        if limit <= 0:
            raise ValueError(f"limit must be positive, got {limit}")
        if limit > source_count:
            raise ValueError(
                f"limit ({limit}) cannot exceed source chapters count ({source_count})"
            )
        mode = "prefix"
        selected = discovered[:limit]
        requested_limit = limit
    else:
        mode = "full"
        selected = discovered
        requested_limit = None

    source_digest = compute_source_digest(discovered)
    selected_chapter_ids = [c.position for c in selected]
    selected_urls = [c.source_url for c in selected]

    return SourceScopeRecord(
        source_url=source_url,
        mode=mode,
        requested_limit=requested_limit,
        source_count=source_count,
        source_digest=source_digest,
        selected_count=len(selected),
        selected_chapter_ids=selected_chapter_ids,
        selected_urls=selected_urls,
        entries=discovered,
    )


def save_source_scope(path: Path, scope: SourceScopeRecord) -> None:
    atomic_write_yaml(path, scope)


def load_source_scope(path: Path) -> SourceScopeRecord:
    return load_yaml_model(path, SourceScopeRecord)


def validate_scope_catalog(
    record: SourceScopeRecord,
    catalog: ChapterCatalog,
) -> ScopeValidationResult:
    expected_digest = compute_source_digest(record.entries)
    if expected_digest != record.source_digest:
        return ScopeValidationResult(
            is_valid=False,
            reason=f"source digest mismatch: expected {expected_digest}, got {record.source_digest}",
        )

    validation = validate_discovered_catalog(record.entries)
    if validation.get("blockers"):
        return ScopeValidationResult(
            is_valid=False,
            reason=f"source catalog has validation blockers: {validation['blockers']}",
        )

    if len(catalog.chapters) != record.selected_count:
        return ScopeValidationResult(
            is_valid=False,
            reason=(
                f"catalog chapter count ({len(catalog.chapters)}) does not match "
                f"scope selected_count ({record.selected_count})"
            ),
        )

    catalog_ids = [c.chapter_id for c in catalog.chapters]
    if catalog_ids != record.selected_chapter_ids:
        return ScopeValidationResult(
            is_valid=False,
            reason=(
                f"catalog chapter IDs {catalog_ids} do not match scope selected IDs "
                f"{record.selected_chapter_ids}"
            ),
        )

    catalog_urls = [c.source_url for c in catalog.chapters]
    if catalog_urls != record.selected_urls:
        return ScopeValidationResult(
            is_valid=False,
            reason="catalog source URLs do not match scope selected URLs",
        )

    expected_titles = [
        e.original_title for e in record.entries[: record.selected_count]
    ]
    catalog_titles = [c.original_title for c in catalog.chapters]
    if catalog_titles != expected_titles:
        return ScopeValidationResult(
            is_valid=False,
            reason="catalog original titles do not match scope selected titles",
        )

    return ScopeValidationResult(is_valid=True)
