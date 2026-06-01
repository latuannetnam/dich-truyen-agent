from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from dich_truyen_agent.models import CrawlProfile, ProfileSource
from dich_truyen_agent.storage import atomic_write_yaml, load_yaml_model


def _validate_domain(domain: str) -> str:
    if (
        not domain
        or domain in {".", ".."}
        or "/" in domain
        or "\\" in domain
        or Path(domain).is_absolute()
    ):
        raise ValueError(f"invalid crawl profile domain: {domain!r}")
    return domain.lower()


def _source_host(source_url: str) -> str:
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"crawl source URL must use HTTP(S) with a host: {source_url!r}")
    return parsed.hostname.lower()


def _require_matching_domain(profile: CrawlProfile, expected_domain: str) -> None:
    if _validate_domain(profile.domain) != expected_domain:
        raise ValueError(
            f"crawl profile domain {profile.domain!r} does not match source domain "
            f"{expected_domain!r}"
        )


def shared_profile_path(project_root: Path, domain: str) -> Path:
    safe_domain = _validate_domain(domain)
    return project_root / "templates" / "crawl_profiles" / f"{safe_domain}.yaml"


def load_crawl_profile(path: Path) -> CrawlProfile:
    return load_yaml_model(path, CrawlProfile)


def load_active_crawl_profile(
    project_root: Path,
    workspace_root: Path,
    source_url: str,
) -> ProfileSource:
    domain = _source_host(source_url)
    shared_path = shared_profile_path(project_root, domain)
    local_path = workspace_root / "crawl-profile.yaml"
    active_path = local_path if local_path.exists() else shared_path
    if not active_path.exists():
        raise ValueError(f"no crawl profile matches source domain {domain!r}")
    profile = load_crawl_profile(active_path)
    _require_matching_domain(profile, domain)
    return ProfileSource(
        shared_path=shared_path,
        local_path=local_path,
        active_path=active_path,
        is_local_override=active_path == local_path,
        profile=profile,
    )


def snapshot_local_crawl_profile(
    workspace_root: Path,
    profile: CrawlProfile,
) -> Path:
    destination = workspace_root / "crawl-profile.yaml"
    atomic_write_yaml(destination, profile)
    return destination


def promote_local_crawl_profile(project_root: Path, workspace_root: Path) -> Path:
    local_path = workspace_root / "crawl-profile.yaml"
    profile = load_crawl_profile(local_path)
    destination = shared_profile_path(project_root, profile.domain)
    if destination.exists():
        _require_matching_domain(load_crawl_profile(destination), profile.domain.lower())
    atomic_write_yaml(destination, profile)
    return destination
