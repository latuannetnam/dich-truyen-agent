---
phase: 01
slug: workspace-contracts-and-skill-skeletons
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-31
---

# Phase 01 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | `pyproject.toml` - Wave 0 adds pytest configuration and development dependencies |
| **Quick run command** | `uv run pytest tests/test_storage.py tests/test_workspace.py tests/test_checkpoints.py tests/test_styles.py -q` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run the narrow test file command listed in the plan task.
- **After every plan wave:** Run `uv run pytest`.
- **Before `$gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** 10 seconds.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | WORK-01, WORK-02 | T-01 | Reject path traversal and malformed YAML | unit | `uv run pytest tests/test_workspace.py -q` | No - W0 | pending |
| 01-01-02 | 01 | 1 | WORK-03 | T-02 | Preserve valid canonical files across interrupted writes | unit | `uv run pytest tests/test_storage.py -q` | No - W0 | pending |
| 01-01-03 | 01 | 1 | WORK-01, WORK-03 | T-03 | Refuse overwrite and stop on inconsistent completed state | unit | `uv run pytest tests/test_workspace.py -q` | No - W0 | pending |
| 01-02-01 | 02 | 2 | WORK-04 | T-04 | Reject missing or stale approvals after input mutation | unit | `uv run pytest tests/test_checkpoints.py -q` | No - W0 | pending |
| 01-02-02 | 02 | 2 | STYL-01, STYL-02 | T-05 | Validate safe YAML and snapshot selected style atomically | unit | `uv run pytest tests/test_styles.py -q` | No - W0 | pending |
| 01-02-03 | 02 | 2 | WORK-04 | - | Emit compact CLI metadata and documented unfinished skill failures | unit | `uv run pytest tests/test_cli.py -q` | No - W0 | pending |

---

## Wave 0 Requirements

- [ ] `pyproject.toml` - add Pydantic, PyYAML, pytest, and Ruff dependencies and configure `src/` packaging.
- [ ] `tests/conftest.py` - shared temporary-workspace fixtures.
- [ ] `tests/test_storage.py` - atomic write and orphan-temp tests.
- [ ] `tests/test_workspace.py` - initialization, layout, inspection, and resume tests.
- [ ] `tests/test_checkpoints.py` - checkpoint allow/block tests.
- [ ] `tests/test_styles.py` - bundled and custom style snapshot tests.
- [ ] `tests/test_cli.py` - compact result and skeleton failure tests.

---

## Manual-Only Verifications

All Phase 1 behaviors have automated verification. Skill Markdown should also be inspected for
readable command documentation during plan review.

---

## Validation Sign-Off

- [x] All tasks have automated verify commands or Wave 0 dependencies.
- [x] Sampling continuity: no 3 consecutive tasks without automated verify.
- [x] Wave 0 covers all missing references.
- [x] No watch-mode flags.
- [x] Feedback latency target is below 10 seconds.
- [x] `nyquist_compliant: true` is set in frontmatter.

**Approval:** approved 2026-05-31
