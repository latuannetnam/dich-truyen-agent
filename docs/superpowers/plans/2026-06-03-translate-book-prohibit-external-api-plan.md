# Translate Book Prohibit External API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modify the `translate-book` skill to explicitly ban external LLM APIs and enforce native subagent usage.

**Architecture:** We are updating the `translate-book/SKILL.md` markdown file to add strict warnings and clarifications in the Overview, Step 5, and Common Pitfalls sections.

**Tech Stack:** Markdown

---

### Task 1: Update Translate Book Skill

**Files:**
- Modify: `.agent/skills/translate-book/SKILL.md`

- [ ] **Step 1: Add Global Warning to Overview**

Insert the following block immediately after the existing Context Protection `> [!IMPORTANT]` block (around line 18), right before the `---` separator:

```markdown
> [!WARNING]
> **Strict External API Prohibition:**
> You are strictly forbidden from using external LLM APIs (e.g., OpenRouter, OpenAI, Gemini) via Python scripts, curl, or any other external tool to perform the translation. You MUST only use the native Antigravity `invoke_subagent` capability as specified in this document.
```

- [ ] **Step 2: Update Step 5 Instructions**

Replace the sentence in Step 5 (around line 66) that reads:
`Spawn a specialized translation subagent natively using the `invoke_subagent` tool with this exact structure:`

With:
```markdown
Spawn a specialized translation subagent natively using the `invoke_subagent` tool. Do NOT attempt to run external python scripts or curl commands targeting third-party LLM APIs (OpenRouter, OpenAI, etc.). Use exactly this structure:
```

- [ ] **Step 3: Add Common Pitfall**

Add the following bullet point to the end of the `## Common Pitfalls` section (around line 195):

```markdown
* **Using External LLM APIs:** Attempting to use Python or shell scripts to send raw text to external APIs (OpenAI, OpenRouter, etc.) instead of spawning a subagent. This is strictly prohibited and bypasses the native orchestration framework. Always use `invoke_subagent`.
```

- [ ] **Step 4: Commit**

```bash
git add .agent/skills/translate-book/SKILL.md
git commit -m "docs: ban external API usage in translate-book skill"
```
