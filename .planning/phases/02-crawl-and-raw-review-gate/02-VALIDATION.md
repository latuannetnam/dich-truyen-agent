---
phase: 02
slug: crawl-and-raw-review-gate
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-31
---

# Phase 02 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x with pytest-asyncio 1.x |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest tests/test_crawl_profiles.py tests/test_crawler.py tests/test_crawl_batch.py tests/test_crawl_reports.py tests/test_cli.py -q` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~20 seconds offline |

## Sampling Rate

- **After every task commit:** Run the narrow test file command listed in the plan task.
- **After every plan wave:** Run `uv run pytest`.
- **Before `$gsd-verify-work`:** Run the full suite, Ruff, CLI help, and the live 10-chapter crawl.
- **Max offline feedback latency:** 20 seconds.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | CRAW-03, CRAW-04 | T-02-01 | Strict profile YAML and local override paths | unit | `uv run pytest tests/test_crawl_profiles.py -q` | Created first in task | pending |
| 02-01-02 | 01 | 1 | CRAW-01 | T-02-02 | Decode Chinese pages predictably | unit | `uv run pytest tests/test_crawler.py -q` | Created first in task | pending |
| 02-01-03 | 01 | 1 | CRAW-01, CRAW-09 | T-02-03 | Reject duplicate and clearly incomplete catalogs | unit | `uv run pytest tests/test_crawler.py -q` | Created first in task | pending |
| 02-02-01 | 02 | 2 | CRAW-06, CRAW-07 | T-02-04 | Stop at first exhausted chapter and resume safely | unit | `uv run pytest tests/test_crawl_batch.py -q` | Created first in task | pending |
| 02-02-02 | 02 | 2 | CRAW-02, CRAW-10 | T-02-05 | Browser fallback only for rendered-content failures; challenge pages block | unit | `uv run pytest tests/test_crawl_batch.py -q` | Created first in task | pending |
| 02-02-03 | 02 | 2 | CRAW-08 | T-02-06 | Persist compact results without bodies or verbose HTML | unit | `uv run pytest tests/test_crawl_batch.py tests/test_cli.py -q` | Created first in task | pending |
| 02-03-01 | 03 | 3 | CRAW-09, CRAW-11 | T-02-07 | Report blockers and preserve explicit partial approval scope | unit | `uv run pytest tests/test_crawl_reports.py tests/test_checkpoints.py -q` | Created first in task | pending |
| 02-03-02 | 03 | 3 | CRAW-05 | T-02-08 | Repair stays local unless explicitly promoted | unit | `uv run pytest tests/test_crawl_profiles.py tests/test_cli.py -q` | Created first in task | pending |
| 02-03-03 | 03 | 3 | CRAW-01..11 | T-02-09 | Skill documents explicit review and live verification | unit + manual | `uv run pytest tests/test_cli.py -q` | Existing file modified | pending |

## Same-Task TDD Test Creation

Wave 0 is not required. Each task creates or extends its listed tests before implementation and
runs the aligned narrow command before commit.

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live static crawl with conservative pacing | CRAW-01, CRAW-06, CRAW-08, CRAW-09, CRAW-11 | External network and live HTML drift | Run `uv run python main.py crawl-book --books-root books --slug jian-lai-phase2-check --source-url https://www.piaotia.com/html/8/8717/index.html --max-chapters 10`; confirm `10` raw files, partial scope, report path, compact result, and explicit approval flow. |
| Browser binary availability | CRAW-02 | Playwright Chromium is an optional local install | Run `uv run playwright install chromium` before an optional browser integration exercise; offline fake-renderer tests remain mandatory. |

## Validation Sign-Off

- [x] Every task has aligned automated verification or a documented manual external check.
- [x] Sampling continuity: no 3 consecutive tasks without automated verify.
- [x] Wave 0 is not required; fixtures and tests are created inside owning tasks.
- [x] No watch-mode flags.
- [x] Offline feedback latency target is below 20 seconds.
- [x] `nyquist_compliant: true` is set in frontmatter.

**Approval:** approved 2026-05-31

