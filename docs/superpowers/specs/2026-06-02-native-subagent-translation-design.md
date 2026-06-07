# Design Spec: Native Antigravity Subagent Translation

Improve the `.agent/skills/translate-book/SKILL.md` file to strictly use the native Antigravity subagent invocation tool (`invoke_subagent`), integrating precise prompting, absolute path resolution guidelines, a structured lexical sandbox rule, and lightweight verification checks to prevent context pollution in the Main Agent.

---

## 1. Context & Motivation

In the previous versions of the translation skill, translation was either handled by external scripts calling API endpoints or was underspecified. This led to issues where relative paths failed, modern English words leaked into classical Xianxia/Tu Chan prose, or the Main Agent's context window was overloaded by reading raw/translated files directly.

By strictly using the native Antigravity subagent invocation tool (`invoke_subagent`), the Main Agent acts as a lightweight coordinator, keeping its own session clean and allowing it to orchestrate the translation of hundreds of chapters in a single session.

---

## 2. Proposed Changes

### [Component] `.agent/skills/translate-book/SKILL.md`

We will rewrite [SKILL.md](../../../.agent/skills/translate-book/SKILL.md) to define:
* A structured sequential orchestration loop.
* Clear instructions for constructing absolute file paths before dispatching subagents.
* The exact native `invoke_subagent` tool call signature.
* A robust, self-contained subagent prompt template.
* The **Lexical Sandbox Rule** lookup table to translate modern English helper words to Vietnamese.
* Lightweight verification check using `view_file` to inspect only the first few lines of staged outputs.
* Safe promotion and error handling (retries, polite backoffs, and resumption gates).

---

## 3. Subagent Execution Protocol

### Tool Call Signature
The Main Agent will invoke the subagent natively using:
```json
invoke_subagent({
  "Subagents": [
    {
      "Prompt": "[Filled Prompt Template]",
      "Role": "Chinese-to-Vietnamese Xianxia/Tu Chan Translator",
      "TypeName": "translator"
    }
  ]
})
```

### Lexical Sandbox Table
To keep the translation literary and clean, the subagent must scan its draft translation for the following banned English words:

| Banned English Word | Vietnamese Equivalent | Notes |
| :--- | :--- | :--- |
| `but` | nhưng | |
| `and` | và | |
| `or` | hoặc | |
| `while` | trong khi | |
| `before` | trước khi | |
| `after` | sau khi | |
| `of` | của | |
| `to` | đến / cho | depends on context |
| `in` | trong | |
| `on` | trên | |
| `at` | tại | |
| `for` | cho / vì | depends on context |
| `with` | với | |
| `the` | *(omit article)* | Vietnamese has no articles |
| `here` | đây | |
| `now` | bây giờ | |
| `okay` | được / OK | |

---

## 4. Main Agent Orchestration Protocol

The Main Agent must follow these steps:
1. **Verify Checkpoint Gate:** Check `crawl-approved` gate status.
2. **Query Progress:** Fetch next pending chapter `chapter_id`, `slug`, and `original_title`.
3. **Fetch Context Paths:** Call `prepare-translation-context` to retrieve workspace relative/absolute paths.
4. **Resolve Absolute Paths:** Resolve all paths (`raw_path`, `style_path`, `glossary_path`, `prev_translation_path`) to absolute paths.
5. **Call `invoke_subagent`:** Execute the native subagent invocation.
6. **Staging Preview:** Use `view_file` with `EndLine: 3` to verify the staging file `# Chương [N] [Title]` header. Do **NOT** load the whole file.
7. **Promote Chapter:** Call `promote-chapter` to commit and clean staging.
8. **Loop or Handle Error:** Retry up to 3 times on failure; halt on exhaustion.

---

## 5. Verification Plan

* **Lint and Parsing:** Run a markdown parser/linter if available, or visually check that the file conforms to standard markdown format.
* **Orchestration Test Run:** Walk through the steps manually on a mock chapter to verify the CLI helper outputs.
* **Test Suite Verification:** Run `pytest` to make sure all existing python tests for translation context preparation and promotion still pass successfully.
