# Phase 2: Crawl and Raw Review Gate - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-05-31
**Phase:** 2-crawl-and-raw-review-gate
**Areas discussed:** Crawl configuration and verification, Profile ownership and repair,
Catalog completeness rules, Retries and browser fallback, Raw review and approval flow

---

## Crawl Configuration and Verification

### Maximum chapter count

**User's choice:** Add configurable `max_chapters`; default `0` means unlimited. Use
`max_chapters=10` for live Phase 2 verification against
`https://www.piaotia.com/html/8/8717/index.html`.

### Crawl pacing

| Option | Description | Selected |
|--------|-------------|----------|
| Configurable fixed delay | Sleep after each successful chapter fetch; allow overrides | Yes |
| Configurable randomized delay | Sleep within a configured range | |
| Fixed built-in delay | Hardcode pacing with no override | |

**User's choice:** Configurable fixed delay with a default of `3` seconds.

---

## Profile Ownership and Repair

### Repaired-profile destination

| Option | Description | Selected |
|--------|-------------|----------|
| Book-local override first | Keep repairs local until a later promotion action | |
| Shared domain profile immediately | Update shared rules as soon as repair validates | |
| Prompt each time | Ask whether validated repair remains local or updates shared rules | Yes |

### Existing local override reuse

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse automatically | Apply the validated override and report it as active | Yes |
| Ask before reuse | Confirm on every run | |
| Ignore unless explicitly requested | Default back to shared domain rules | |

### Failed shared-profile validation

| Option | Description | Selected |
|--------|-------------|----------|
| Stop and request agent repair | Preserve diagnostics and propose validated local repair | Yes |
| Try generic fallback selectors first | Attempt heuristics silently | |
| Switch directly to Playwright | Substitute browser transport for profile repair | |

### Promotion timing

| Option | Description | Selected |
|--------|-------------|----------|
| Offer promotion immediately | Ask once after successful repair validation | Yes |
| Keep local without prompting | Require a separate later command | |
| Always promote after validation | Replace shared rules automatically | |

---

## Catalog Completeness Rules

### Limited crawl behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Discover full catalog, download first N | Validate full structure while limiting body downloads | Yes |
| Stop discovery after N chapters | Limit both catalog parsing and downloads | |
| Separate discovery and download limits | Add independent configuration knobs | |

### Duplicate entries

| Option | Description | Selected |
|--------|-------------|----------|
| Stop before downloads | Block duplicates and avoid guessing canonical entries | Yes |
| Deduplicate exact URLs automatically | Collapse identical links only | |
| Keep first occurrence with warning | Continue while discarding later entries | |

### Gaps and unusual ordering

| Option | Description | Selected |
|--------|-------------|----------|
| Stop on clear gaps; warn on uncertain ordering | Block parsed numeric gaps and warn on ambiguity | Yes |
| Stop on any irregularity | Block irregular titles too | |
| Warn and continue | Never block catalog irregularities | |

### Pagination and list sections

| Option | Description | Selected |
|--------|-------------|----------|
| Follow configured rules and validate all pages | Use deterministic profile rules | Yes |
| Auto-follow likely pagination links | Use heuristic next-page discovery | |
| Use supplied URL only | Require repair for split indexes | |

---

## Retries and Browser Fallback

### Playwright fallback

| Option | Description | Selected |
|--------|-------------|----------|
| After missing rendered content | Fall back when received HTML validates as empty or incomplete | Yes |
| After any HTTP failure | Use browser transport for transport-level errors too | |
| Only when profile requests browser mode | Never infer fallback | |

### Recoverable HTTP retries

| Option | Description | Selected |
|--------|-------------|----------|
| Three attempts with exponential backoff | Configurable delay between attempts | Yes |
| Three attempts with fixed delay | Keep retry spacing constant | |
| One retry only | Fail quickly | |

### Persistent chapter failure

| Option | Description | Selected |
|--------|-------------|----------|
| Stop immediately and preserve progress | Resume later from the failed chapter | Yes |
| Continue later chapters | Download around gaps | |
| Skip permanently with warning | Complete despite missing raw content | |

### CAPTCHA or authentication page

| Option | Description | Selected |
|--------|-------------|----------|
| Stop without retrying | Preserve URL and diagnostics for intervention | Yes |
| Retry HTTP before stopping | Treat signal as possibly transient | |
| Open Playwright for manual login | Support interactive authentication | |

---

## Raw Review and Approval Flow

### Crawl report contents

| Option | Description | Selected |
|--------|-------------|----------|
| Structured summary plus representative samples | Include findings, lengths, and beginning/middle/end excerpts | Yes |
| Summary statistics only | Require manual raw-file inspection for content | |
| Excerpt for every chapter | Include a body sample per crawled chapter | |

### Approval blockers

| Option | Description | Selected |
|--------|-------------|----------|
| Block structural and extraction failures | Warn on suspicious content requiring judgment | Yes |
| Block every anomaly | Treat warnings as hard failures | |
| Block only missing or empty chapters | Allow other structural issues | |

### Limited-crawl approval

| Option | Description | Selected |
|--------|-------------|----------|
| Allow approval scoped to partial crawl | Mark partial and block downstream full-book use | Yes |
| Never allow limited approval | Restrict checkpoints to unlimited crawls | |
| Treat subset as complete book | Allow downstream use without distinction | |

### Approval command

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit approval through `$crawl-book` | Confirm after displaying report summary | Yes |
| Run low-level helper manually | Require direct CLI invocation | |
| Create automatically | Write checkpoint when no blockers exist | |

---

## the agent's Discretion

None.

## Deferred Ideas

None.
