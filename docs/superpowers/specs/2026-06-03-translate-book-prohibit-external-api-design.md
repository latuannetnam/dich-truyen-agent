# Design: Prohibit External LLM APIs in translate-book Skill

## Objective
Enforce the strict use of native agent capabilities (`invoke_subagent`) for translation and explicitly ban the use of external LLM APIs (like OpenRouter, OpenAI, Gemini) via Python scripts or curl in the `translate-book` skill.

## Proposed Changes

### 1. Overview Section
Add a strict warning block immediately alongside the context protection block to ban external API usage globally.

```markdown
> [!WARNING]
> **Strict External API Prohibition:**
> You are strictly forbidden from using external LLM APIs (e.g., OpenRouter, OpenAI, Gemini) via Python scripts, curl, or any other external tool to perform the translation. You MUST only use the native Antigravity `invoke_subagent` capability as specified in this document.
```

### 2. Step 5: Spawn the Isolation Subagent Natively
Update the intro paragraph for Step 5 to reinforce the rule at the point of action.

```markdown
Spawn a specialized translation subagent natively using the `invoke_subagent` tool. Do NOT attempt to run external python scripts or curl commands targeting third-party LLM APIs (OpenRouter, OpenAI, etc.). Use exactly this structure:
```

### 3. Common Pitfalls
Add a new bullet point to address this specific anti-pattern.

```markdown
* **Using External LLM APIs:** Attempting to use Python or shell scripts to send raw text to external APIs (OpenAI, OpenRouter, etc.) instead of spawning a subagent. This is strictly prohibited and bypasses the native orchestration framework. Always use `invoke_subagent`.
```

## Review
- [x] Placeholder scan: No placeholders.
- [x] Internal consistency: All updates align with the same core constraint.
- [x] Scope check: Tightly scoped to the `translate-book` skill document.
- [x] Ambiguity check: Clear and direct language.
