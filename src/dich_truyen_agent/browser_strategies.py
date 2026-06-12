from __future__ import annotations

from typing import Any, Protocol

from dich_truyen_agent.models import CrawlProfile


class BrowserStrategy(Protocol):
    async def before_goto(self, page: Any, url: str, profile: CrawlProfile) -> None:
        """Run before the renderer navigates to the requested URL."""

    async def after_goto(self, page: Any, url: str, profile: CrawlProfile) -> None:
        """Run after the renderer navigates to the requested URL."""


class NoopBrowserStrategy:
    async def before_goto(self, page: Any, url: str, profile: CrawlProfile) -> None:
        del page, url, profile

    async def after_goto(self, page: Any, url: str, profile: CrawlProfile) -> None:
        del page, url, profile


_STRATEGIES: dict[str, BrowserStrategy] = {
    "noop": NoopBrowserStrategy(),
}


def get_browser_strategy(name: str | None) -> BrowserStrategy:
    if name is None:
        return _STRATEGIES["noop"]
    try:
        return _STRATEGIES[name]
    except KeyError as exc:
        raise ValueError(f"unknown crawl browser strategy: {name}") from exc
