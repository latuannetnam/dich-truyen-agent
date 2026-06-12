from __future__ import annotations


class PlaywrightRenderer:
    """Stateful Playwright renderer adapter with Cloudflare bypass evasions."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._established_sessions = set()

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
            if not self._playwright:
                self._playwright = await async_playwright().start()
                try:
                    # Evasion: Disable automation control to bypass webdriver detection
                    self._browser = await self._playwright.chromium.launch(
                        headless=True,
                        args=["--disable-blink-features=AutomationControlled"]
                    )
                except Exception as e:
                    await self.close()
                    raise RuntimeError(
                        "Chromium browser binary is missing. Please run: "
                        "uv run playwright install chromium"
                    ) from e

                # Evasion: Spoof user-agent and viewport
                self._context = await self._browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 800}
                )
                self._page = await self._context.new_page()
                
                # Evasion: Delete webdriver property from navigator
                await self._page.add_init_script("delete Object.getPrototypeOf(navigator).webdriver;")
                
            # 69shuba session cookie bypass: visit the book's index page first if navigating to a chapter page
            import re
            import asyncio
            m = re.match(r'https?://(?:www\.)?69shuba\.com/txt/(\d+)/\d+', url)
            if m:
                book_id = m.group(1)
                index_url = f"https://www.69shuba.com/book/{book_id}/"
                if book_id not in self._established_sessions:
                    try:
                        print(f"[DEBUG] Establishing session cookies on index page: {index_url}")
                        await self._page.goto(index_url, wait_until="domcontentloaded", timeout=20000)
                        # Self-healing wait for Cloudflare challenge resolution
                        for _ in range(10):
                            title = await self._page.title()
                            if "just a moment" not in title.lower() and "attention required" not in title.lower():
                                break
                            await asyncio.sleep(1)
                        print(f"[DEBUG] Session title: {await self._page.title()}")
                        self._established_sessions.add(book_id)
                    except Exception as e:
                        print(f"[DEBUG] Session establishment failed: {e}")

            # Wait until DOM is loaded (domcontentloaded is faster and safer than networkidle on ad-heavy sites)
            is_ixdzs = any(domain in url for domain in ["ixdzs8.com", "ixdzs.hk", "ixdzs.tw"])
            is_index_page = is_ixdzs and not re.search(r'/p\d+\.html', url)
            
            if is_index_page:
                try:
                    print(f"[DEBUG] Navigating index page and waiting for clist response...")
                    async with self._page.expect_response(lambda response: "clist" in response.url, timeout=20000) as response_info:
                        await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    print(f"[DEBUG] clist response received!")
                except Exception as e:
                    print(f"[DEBUG] Failed to capture clist response: {e}")
                    try:
                        await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    except Exception:
                        pass
            else:
                await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Self-healing wait for Cloudflare or custom browser verification challenges
            print(f"[DEBUG] Playwright navigation complete. Initial title: {await self._page.title()}")
            for i in range(15):
                title = await self._page.title()
                title_lower = title.lower()
                is_challenge = (
                    "just a moment" in title_lower
                    or "attention required" in title_lower
                    or "正在验证" in title_lower
                    or "安全验证" in title_lower
                    or "验证浏览器" in title_lower
                )
                if not is_challenge:
                    print(f"[DEBUG] Playwright page resolved after {i}s. Title: {title}")
                    break
                print(f"[DEBUG] Playwright page challenge active. Waiting {i+1}s... Title: {title}")
                await asyncio.sleep(1)

            # If the page has a catalog button, click it to expand the catalog list
            try:
                catalog_btn = await self._page.query_selector(".catalog-all")
                if catalog_btn:
                    print("[DEBUG] Found .catalog-all element, clicking to expand catalog.")
                    await catalog_btn.click()
                    # Wait for the catalog to populate
                    await self._page.wait_for_selector(".clist .u-chapter li a", timeout=10000)
                    print("[DEBUG] Catalog expanded and populated successfully.")
            except Exception as e:
                print(f"[DEBUG] Catalog expansion failed or timed out: {e}")

            html = await self._page.content()
            return html
        except Exception:
            await self.close()
            raise

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


