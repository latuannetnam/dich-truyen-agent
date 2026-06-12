from __future__ import annotations

import asyncio
import inspect
import math
import re
from collections.abc import Awaitable, Callable
from typing import Any

from dich_truyen_agent.browser_strategies import get_browser_strategy
from dich_truyen_agent.models import (
    CrawlBrowserActionProfile,
    CrawlBrowserSessionWarmupProfile,
    CrawlProfile,
)


class PlaywrightRenderer:
    """Stateful Playwright renderer adapter driven by crawl profile browser settings."""

    def __init__(
        self,
        *,
        playwright_factory: Callable[[], Awaitable[Any]] | None = None,
        sleeper: Callable[[float], Awaitable[None] | None] | None = None,
    ) -> None:
        self._playwright_factory = playwright_factory
        self._sleeper = sleeper or asyncio.sleep
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._established_sessions: set[str] = set()

    async def render(self, url: str, profile: CrawlProfile, *, purpose: str = "chapter") -> str:
        """Render a URL using headless Playwright browser and return the HTML content."""
        try:
            await self._ensure_page(profile)
            strategy = get_browser_strategy(profile.browser.strategy)
            await self._establish_sessions(url, profile)
            await strategy.before_goto(self._page, url, profile)
            await self._goto(url, profile, purpose=purpose)
            await self._wait_for_challenge(profile)
            await self._run_actions(profile, purpose)
            await strategy.after_goto(self._page, url, profile)
            return await self._page.content()
        except Exception:
            await self.close()
            raise

    async def _start_playwright(self):
        if self._playwright_factory is not None:
            return await self._playwright_factory()
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise RuntimeError(
                "Playwright library is not installed. To use browser fallback, "
                "please install browser dependencies: uv run playwright install chromium"
            ) from e
        return await async_playwright().start()

    async def _ensure_page(self, profile: CrawlProfile) -> None:
        if self._playwright:
            return
        self._playwright = await self._start_playwright()
        try:
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=profile.browser.launch_args,
            )
        except Exception as e:
            await self.close()
            raise RuntimeError(
                "Chromium browser binary is missing. Please run: "
                "uv run playwright install chromium"
            ) from e

        context_options: dict[str, Any] = {
            "viewport": {
                "width": profile.browser.viewport.width,
                "height": profile.browser.viewport.height,
            }
        }
        if profile.browser.user_agent:
            context_options["user_agent"] = profile.browser.user_agent
        self._context = await self._browser.new_context(**context_options)
        self._page = await self._context.new_page()
        for script in profile.browser.init_scripts:
            await self._page.add_init_script(script)

    async def _establish_sessions(self, url: str, profile: CrawlProfile) -> None:
        for warmup in profile.browser.session.warmups:
            warmup_url = self._resolve_warmup_url(warmup, url)
            if warmup_url is None or warmup_url in self._established_sessions:
                continue
            await self._goto(warmup_url, profile, purpose="warmup")
            await self._wait_for_challenge(profile)
            self._established_sessions.add(warmup_url)

    def _resolve_warmup_url(
        self,
        warmup: CrawlBrowserSessionWarmupProfile,
        url: str,
    ) -> str | None:
        if warmup.url_pattern is None:
            return warmup.warmup_url
        match = re.match(warmup.url_pattern, url)
        if not match:
            return None
        return warmup.warmup_url.format(**match.groupdict())

    async def _goto(self, url: str, profile: CrawlProfile, *, purpose: str) -> None:
        navigation = profile.browser.navigation
        response_markers = []
        if purpose == "index":
            response_markers = profile.browser.index.wait_for_response_url_contains
        if response_markers:
            async with self._page.expect_response(
                lambda response: any(marker in response.url for marker in response_markers),
                timeout=navigation.timeout_milliseconds,
            ):
                await self._page.goto(
                    url,
                    wait_until=navigation.wait_until,
                    timeout=navigation.timeout_milliseconds,
                )
            return
        await self._page.goto(
            url,
            wait_until=navigation.wait_until,
            timeout=navigation.timeout_milliseconds,
        )

    async def _wait_for_challenge(self, profile: CrawlProfile) -> None:
        challenge = profile.browser.challenge
        if not challenge.title_markers or challenge.max_wait_seconds <= 0:
            return
        markers = [marker.lower() for marker in challenge.title_markers]
        iterations = max(1, math.ceil(challenge.max_wait_seconds / challenge.poll_seconds))
        for _ in range(iterations):
            title = (await self._page.title()).lower()
            if not any(marker in title for marker in markers):
                return
            maybe_awaitable = self._sleeper(challenge.poll_seconds)
            if inspect.isawaitable(maybe_awaitable):
                await maybe_awaitable

    async def _run_actions(self, profile: CrawlProfile, purpose: str) -> None:
        for action in profile.browser.actions:
            if action.purpose not in {"all", purpose}:
                continue
            await self._run_action(action)

    async def _run_action(self, action: CrawlBrowserActionProfile) -> None:
        if action.action == "click":
            element = await self._page.query_selector(action.selector)
            if element is None:
                return
            await element.click()
            if action.wait_for_selector:
                await self._page.wait_for_selector(
                    action.wait_for_selector,
                    timeout=action.timeout_milliseconds,
                )
            return
        if action.action == "wait_for_selector":
            await self._page.wait_for_selector(
                action.selector,
                timeout=action.timeout_milliseconds,
            )
            return
        if action.action == "wait_for_response_url_contains":
            await self._page.wait_for_response(
                lambda response: action.url_contains in response.url,
                timeout=action.timeout_milliseconds,
            )
            return
        raise ValueError(f"unsupported browser action: {action.action}")

    async def close(self) -> None:
        """Close browser resources."""
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        self._context = None
        self._page = None
        self._established_sessions.clear()
