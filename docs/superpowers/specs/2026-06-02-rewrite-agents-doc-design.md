# Design Spec: Rewrite AGENTS.md for Agent-Native Translation Orchestration

**Date:** 2026-06-02
**Topic:** Rewrite AGENTS.md
**Status:** Approved by User

## 1. Goal & Context

The goal is to streamline and rewrite [AGENTS.md](../../../AGENTS.md) to serve as a high-level orchestration guide for the Antigravity agent-native novel translation pipeline (Crawl -> Translate -> QA -> Export).

We will remove all unrelated developer stack details, GSD command instructions, troubleshooting guides, and empty conventions placeholders. The target of this document is the Antigravity Main Agent coordinating the workflow.

## 2. Selected Approach

**Approach: Pipeline Stage Walkthrough with Delegated Skills**
Instead of repeating the details of each step or just listing a CLI reference:
- Define the high-level workspace lifecycle (using a Mermaid diagram).
- Register the available Antigravity skills and link directly to their respective `SKILL.md` files as the single source of truth.
- Keep only the critical global orchestration guardrails (token/context protection, order requirements, failure/retry limits, and Windows-specific encoding/sandbox CLI configurations).

## 3. Proposed File Changes

### [MODIFY] [AGENTS.md](../../../AGENTS.md)

Replace the entire content of [AGENTS.md](../../../AGENTS.md) with the new orchestration guide structure:
1. **System Mission & Orchestration Flow**
2. **Pipeline Skills & Entry Points**
3. **Global Orchestration Guardrails**

---

## 4. Verification Plan

### Manual Verification
- Review the rewritten [AGENTS.md](../../../AGENTS.md) file to verify that:
  - All GSD-specific workflows and empty sections are removed.
  - The Mermaid diagram is syntactically correct.
  - All file links to `SKILL.md` files are correct and clickable.
  - The file is concise and highly readable.
