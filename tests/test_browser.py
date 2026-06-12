from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from dich_truyen_agent.browser import PlaywrightRenderer
from dich_truyen_agent.models import CrawlProfile


class FakeElement:
    def __init__(self) -> None:
        self.click_count = 0

    async def click(self) -> None:
        self.click_count += 1


class FakeResponseWait:
    def __init__(self, page: FakePage, label: str) -> None:
        self.page = page
        self.label = label

    async def __aenter__(self) -> FakeResponseWait:
        self.page.response_waits.append(self.label)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


@dataclass
class FakePage:
    html: str = "<html><title>Ready</title><body>ok</body></html>"
    title_values: list[str] = field(default_factory=lambda: ["Ready"])
    init_scripts: list[str] = field(default_factory=list)
    goto_calls: list[dict] = field(default_factory=list)
    waited_selectors: list[dict] = field(default_factory=list)
    response_waits: list[str] = field(default_factory=list)
    elements: dict[str, FakeElement] = field(default_factory=dict)

    async def add_init_script(self, script: str) -> None:
        self.init_scripts.append(script)

    async def goto(self, url: str, *, wait_until: str, timeout: int) -> None:
        self.goto_calls.append({"url": url, "wait_until": wait_until, "timeout": timeout})

    async def title(self) -> str:
        if len(self.title_values) > 1:
            return self.title_values.pop(0)
        return self.title_values[0]

    async def content(self) -> str:
        return self.html

    async def query_selector(self, selector: str):
        return self.elements.get(selector)

    async def wait_for_selector(self, selector: str, *, timeout: int) -> None:
        self.waited_selectors.append({"selector": selector, "timeout": timeout})

    def expect_response(self, predicate, *, timeout: int):
        class Response:
            url = "https://example.com/api/clist"

        assert predicate(Response())
        return FakeResponseWait(self, f"expect_response timeout={timeout}")

    async def wait_for_response(self, predicate, *, timeout: int) -> None:
        class Response:
            url = "https://example.com/api/clist"

        assert predicate(Response())
        self.response_waits.append(f"wait_for_response timeout={timeout}")


class FakeContext:
    def __init__(self, page: FakePage) -> None:
        self.page = page

    async def new_page(self) -> FakePage:
        return self.page


class FakeBrowser:
    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.context_options = None
        self.closed = False

    async def new_context(self, **kwargs) -> FakeContext:
        self.context_options = kwargs
        return FakeContext(self.page)

    async def close(self) -> None:
        self.closed = True


class FakeChromium:
    def __init__(self, browser: FakeBrowser) -> None:
        self.browser = browser
        self.launch_options = None

    async def launch(self, **kwargs) -> FakeBrowser:
        self.launch_options = kwargs
        return self.browser


class FakePlaywright:
    def __init__(self, chromium: FakeChromium) -> None:
        self.chromium = chromium
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


async def no_sleep(seconds: float) -> None:
    del seconds


def profile_with_browser() -> CrawlProfile:
    return CrawlProfile(
        domain="www.69shuba.com",
        index={"chapter_link_selector": "#catalog a"},
        chapter={"title_selector": "h1", "content_selector": ".txtnav"},
        browser={
            "enabled": True,
            "launch_args": ["--disable-blink-features=AutomationControlled"],
            "user_agent": "Mozilla/5.0",
            "viewport": {"width": 1280, "height": 800},
            "init_scripts": ["delete Object.getPrototypeOf(navigator).webdriver;"],
            "challenge": {
                "title_markers": ["just a moment"],
                "max_wait_seconds": 2,
                "poll_seconds": 0.01,
            },
            "session": {
                "warmups": [
                    {
                        "url_pattern": r"https?://(?:www\.)?69shuba\.com/txt/(?P<book_id>\d+)/\d+",
                        "warmup_url": "https://www.69shuba.com/book/{book_id}/",
                    }
                ]
            },
            "index": {"wait_for_response_url_contains": ["clist"]},
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


@pytest.mark.asyncio
async def test_playwright_renderer_applies_profile_browser_settings() -> None:
    page = FakePage(title_values=["Just a moment", "Ready"])
    page.elements[".catalog-all"] = FakeElement()
    browser = FakeBrowser(page)
    chromium = FakeChromium(browser)
    playwright = FakePlaywright(chromium)

    async def factory() -> FakePlaywright:
        return playwright

    renderer = PlaywrightRenderer(playwright_factory=factory, sleeper=no_sleep)

    html = await renderer.render(
        "https://www.69shuba.com/txt/123/456",
        profile_with_browser(),
        purpose="index",
    )

    assert html == page.html
    assert chromium.launch_options == {
        "headless": True,
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    assert browser.context_options == {
        "user_agent": "Mozilla/5.0",
        "viewport": {"width": 1280, "height": 800},
    }
    assert page.init_scripts == ["delete Object.getPrototypeOf(navigator).webdriver;"]
    assert [call["url"] for call in page.goto_calls] == [
        "https://www.69shuba.com/book/123/",
        "https://www.69shuba.com/txt/123/456",
    ]
    assert page.goto_calls[-1]["wait_until"] == "domcontentloaded"
    assert page.goto_calls[-1]["timeout"] == 30000
    assert page.response_waits == ["expect_response timeout=30000"]
    assert page.elements[".catalog-all"].click_count == 1
    assert page.waited_selectors == [
        {"selector": ".clist .u-chapter li a", "timeout": 10000}
    ]


@pytest.mark.asyncio
async def test_playwright_renderer_runs_matching_warmup_once() -> None:
    page = FakePage()
    browser = FakeBrowser(page)
    chromium = FakeChromium(browser)
    playwright = FakePlaywright(chromium)

    async def factory() -> FakePlaywright:
        return playwright

    renderer = PlaywrightRenderer(playwright_factory=factory, sleeper=no_sleep)
    profile = profile_with_browser()

    await renderer.render("https://www.69shuba.com/txt/123/456", profile)
    await renderer.render("https://www.69shuba.com/txt/123/789", profile)

    assert [call["url"] for call in page.goto_calls] == [
        "https://www.69shuba.com/book/123/",
        "https://www.69shuba.com/txt/123/456",
        "https://www.69shuba.com/txt/123/789",
    ]


@pytest.mark.asyncio
async def test_playwright_renderer_rejects_unknown_strategy() -> None:
    profile = profile_with_browser()
    profile.browser.strategy = "missing_strategy"
    page = FakePage()
    browser = FakeBrowser(page)
    chromium = FakeChromium(browser)
    playwright = FakePlaywright(chromium)

    async def factory() -> FakePlaywright:
        return playwright

    renderer = PlaywrightRenderer(playwright_factory=factory, sleeper=no_sleep)

    with pytest.raises(ValueError, match="unknown crawl browser strategy"):
        await renderer.render("https://www.69shuba.com/txt/123/456", profile)
