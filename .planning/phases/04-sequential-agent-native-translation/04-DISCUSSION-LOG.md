# Phase 4: Sequential Agent-Native Translation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-01
**Phase:** 4-Sequential Agent-Native Translation
**Areas discussed:** Translation Worker Execution Model, Staging, Validation, and Atomic Promotion Flow, Skill-Driven Loop Orchestration, Continuity Context Depth & Continuity

---

## Translation Worker Execution Model

| Option | Description | Selected |
|--------|-------------|----------|
| Option A | CLI-driven API Translation Helper (standard python API client library) | |
| Option B | Subagent Tool Invocation (Spawns context-isolated subagent for each chapter) | ✓ |
| Option C | Hybrid (Orchestration in Python, Translation by Agent) | |

**User's choice:** Option B: Subagent Tool Invocation.
**Notes:** Spawns a subagent per chapter passing the paths of the context files rather than embedding them directly in the orchestrator's context.

---

## Staging, Validation, and Atomic Promotion Flow

| Option | Description | Selected |
|--------|-------------|----------|
| Option A | Clean Staged Files + CLI Promotion (Validate, merge glossary, atomically copy, and update state) | ✓ |
| Option B | Direct Writes (Worker directly writes to translations and updates state) | |

**User's choice:** Option A: Clean Staged Files + CLI Promotion.
**Notes:** Extremely robust against crashes and aligns with Phase 1's requirement of atomic, resume-friendly workspace file operations.

---

## Skill-Driven Loop Orchestration

| Option | Description | Selected |
|--------|-------------|----------|
| Option A | Autonomous Python Orchestration (The entire sequential loop is run in Python) | |
| Option B | Skill-Driven Loop (The loop is written in the `$translate-book` skill markdown itself) | ✓ |

**User's choice:** Option B: Skill-Driven Loop.
**Notes:** Perfectly fits Antigravity's native skill model, allowing the agent to read state and invoke the CLI commands in a sequential markdown-driven loop.

---

## Continuity Context Depth & Continuity

| Option | Description | Selected |
|--------|-------------|----------|
| Option A | Strict Predecessor Context with Fallback (Pass Chapter N-1; fallback if N-1 doesn't exist) | ✓ |
| Option B | Sliding Window Context (Pass Chapter N-3 to N-1) | |
| Option C | Predecessor Context + Rolling Summary | |

**User's choice:** Option A: Strict Predecessor Context with Fallback.
**Notes:** If Chapter N-1 translation is not present or empty (e.g. for Chapter 1, or after resets), the orchestrator falls back to passing no predecessor context with a note to the subagent to avoid blocking the workflow.

---

## Deferred Ideas

- Target re-translation of specific chapters (deferred to Phase 5 / QA or v2).
- Automatic character description extraction from chapter text (deferred to v2).

---

*Phase: 4-sequential-agent-native-translation*
*Context gathered: 2026-06-01*
