# Spec: Profile-Driven Browser Strategies For Crawling

* **Date**: 2026-06-12
* **Status**: Draft
* **Author**: Codex

## Goal
Refactor the crawling browser fallback so dynamic anti-bot handling is driven by
the active crawl profile first, with a small Python strategy registry as an
escape hatch for behavior that is too procedural for YAML.

## Context
`src/dich_truyen_agent/browser.py` currently mixes three responsibilities:
generic Playwright lifecycle management, anti-bot browser evasions, and
site-specific behavior for domains such as `www.69shuba.com` and ixdzs-style
catalog pages. The rest of the crawler is already profile-driven: selectors,
encoding, and validation live in `crawl-profile.yaml`. Browser behavior should
follow the same workspace-local override and shared-template flow.

## Proposed Design

### 1. Extend The Crawl Profile Schema
Add an optional `browser` section to `CrawlProfile`.

The default value keeps current static-first behavior unchanged:

```yaml
browser:
  enabled: false
  strategy: null
  launch_args: []
  user_agent: null
  viewport:
    width: 1280
    height: 800
  init_scripts: []
  challenge:
    title_markers: []
    max_wait_seconds: 0
    poll_seconds: 1.0
  session:
    url_patterns: []
    warmup_urls: []
  navigation:
    wait_until: domcontentloaded
    timeout_milliseconds: 30000
  index:
    wait_for_response_url_contains: []
  actions: []
```

The profile remains declarative. Supported action types are intentionally small:
`click`, `wait_for_selector`, and `wait_for_response_url_contains`. Each action
has explicit timeouts and selectors or URL fragments. Python callbacks are not
embedded in YAML.

### 2. Keep A Named Strategy Registry
Add a small registry module for procedural browser behavior:

```python
class BrowserStrategy(Protocol):
    async def before_goto(self, page, url: str, profile: CrawlProfile) -> None: ...
    async def after_goto(self, page, url: str, profile: CrawlProfile) -> None: ...
```

Profiles can opt into a strategy with `browser.strategy: "strategy_name"`.
Unknown strategy names fail validation clearly when rendering starts. The first
implementation can include only a no-op strategy plus any site behavior that
cannot be expressed cleanly through profile fields.

### 3. Make `PlaywrightRenderer` Generic
Change the renderer API to accept the active crawl profile:

```python
async def render(self, url: str, profile: CrawlProfile, *, purpose: str = "chapter") -> str:
```

The renderer owns generic browser mechanics only:

* start and close Playwright resources;
* create browser context from profile browser settings;
* install configured init scripts;
* establish configured warmup sessions;
* navigate with configured wait policy;
* wait for challenge titles to clear;
* run configured post-navigation actions;
* call optional strategy hooks.

`browser.py` should not contain literal domain names, domain URL regexes,
catalog selectors, or hardcoded API response names.

### 4. Integrate With `crawl_batch`
`crawl_batch.py` continues to try static HTTP first. Browser fallback is used
when static fetch fails with anti-bot status, anti-bot HTML markers, or extractor
signals that rendered content is needed.

When browser fallback is used, pass `profile_source.profile` into
`renderer.render(...)`. Existing test injection through `renderer_instance`
continues to work; fake renderers can accept `*args, **kwargs` or the new
signature.

### 5. Move Existing Site Behavior Into Profiles
Move the current 69shuba behavior from code into
`templates/crawl_profiles/www.69shuba.com.yaml`:

* Chromium automation-control launch flag;
* browser-like user agent;
* webdriver-removal init script;
* challenge title markers and wait window;
* session warmup URL derived from named regex capture groups;
* catalog expansion action if needed.

If ixdzs support remains needed, express the `clist` response wait through
`index.wait_for_response_url_contains` when possible. Use a named strategy only
if the behavior needs more than URL-response waiting and configured actions.

### 6. Update Harness Source Documentation
Update `.harness/source/skills/crawl-book.md` so generated harness skills tell
agents to edit `crawl-profile.yaml` browser settings or select a named strategy.
The docs should stop instructing agents to hardcode new evasions in
`browser.py`.

## Error Handling
Invalid profile browser settings should fail profile loading through Pydantic
validation when possible. Runtime failures should include the profile domain,
URL, and failing browser step, without dumping page HTML into the main agent
context.

If a challenge remains active after the configured wait, rendering should return
the page HTML and let existing anti-bot detection block the crawl with the
chapter or index URL context. If browser setup fails because Playwright or
Chromium is missing, keep the current actionable installation messages.

## Testing Plan
Add focused unit tests for:

* `CrawlProfile` accepts default `browser` settings and rejects invalid action
  types, navigation wait policies, and unsafe warmup placeholders;
* `PlaywrightRenderer` applies configured launch args, context settings, init
  scripts, session warmups, challenge waits, response waits, and actions using
  fake Playwright/page objects;
* `crawl_batch` passes the active profile into browser rendering for index and
  chapter fallback;
* the 69shuba template validates with the new browser section;
* generated harness adapters stay in sync after updating `.harness/source`.

## Non-Goals
This change does not attempt to defeat every anti-bot system automatically,
persist browser cookies across separate crawl runs, add external scraping
services, or read raw chapter contents into the main agent context.

