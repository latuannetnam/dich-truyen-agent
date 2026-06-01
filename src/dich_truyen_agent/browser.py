from __future__ import annotations


class PlaywrightRenderer:
    """Lazy optional Playwright renderer adapter."""

    def __init__(self) -> None:
        pass

    async def render(self, url: str) -> str:
        """Render a URL using headless Playwright browser and return the HTML content."""
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise RuntimeError(
                "Playwright library is not installed. To use browser fallback, "
                "please install browser dependencies: uv run playwright install chromium"
            ) from e

        try:
            async with async_playwright() as p:
                try:
                    browser = await p.chromium.launch(headless=True)
                except Exception as e:
                    raise RuntimeError(
                        "Chromium browser binary is missing. Please run: "
                        "uv run playwright install chromium"
                    ) from e

                try:
                    page = await browser.new_page()
                    # Wait until network is idle or page is loaded
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                    html = await page.content()
                    return html
                finally:
                    await browser.close()
        except Exception as e:
            err_msg = str(e).lower()
            if "executable" in err_msg or "install" in err_msg or "chromium" in err_msg:
                raise RuntimeError(
                    "Playwright browser binary is missing. Please run: "
                    "uv run playwright install chromium"
                ) from e
            raise
