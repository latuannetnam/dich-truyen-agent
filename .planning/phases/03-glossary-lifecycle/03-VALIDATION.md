---
phase: 3
slug: glossary-lifecycle
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-01
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/test_glossary.py` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_glossary.py`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | GLOS-01 | — | N/A | unit | `uv run pytest tests/test_glossary.py -k test_glossary_models` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 1 | GLOS-01 | — | N/A | unit | `uv run pytest tests/test_glossary.py -k test_initial_glossary_generation` | ❌ W0 | ⬜ pending |
| 03-02-01 | 02 | 2 | GLOS-02 / GLOS-04 | — | Atomic snapshots before merges | unit | `uv run pytest tests/test_glossary.py -k test_merge_proposals_and_snapshots` | ❌ W0 | ⬜ pending |
| 03-02-02 | 02 | 2 | GLOS-03 / GLOS-04 | — | Protect canonical locks (`is_canonical`) | unit | `uv run pytest tests/test_glossary.py -k test_conflict_reporting_and_locks` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_glossary.py` — stubs for GLOS-01, GLOS-02, GLOS-03, GLOS-04
- [ ] `tests/conftest.py` — check if any shared fixtures need to be extended for glossary files

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 10s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
