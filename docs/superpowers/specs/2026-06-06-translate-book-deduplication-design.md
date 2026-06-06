# Translate-Book Subagent Deduplication & Isolation Design

## Overview
Deduplicate the translation prompt instructions in `translate-book/SKILL.md` by relying entirely on the native agent definitions, and resolve path collisions between `.agent` and `.claude` folder structures by explicitly renaming the Antigravity agent files.

## Goals
1. Remove the massive duplicated `[Subagent Prompt]` block in `translate-book/SKILL.md`.
2. Guarantee that `invoke_subagent` loads the agents from `.agent/agents/` and not `.claude/agents/` without relying on path resolution quirks.

## Proposed Changes

### 1. Rename Agent Files & Internal Frontmatter
- **Rename:** `.agent/agents/translator.md` -> `.agent/agents/ag_translator.md`
  - Update `name: translator` to `name: ag_translator` in its frontmatter.
- **Rename:** `.agent/agents/metadata_translator.md` -> `.agent/agents/ag_metadata_translator.md`
  - Update `name: metadata_translator` to `name: ag_metadata_translator` in its frontmatter.

### 2. Update `translate-book/SKILL.md`
- **Step 1.5 (Metadata Translation)**:
  - Update `TypeName` from `"metadata_translator"` to `"ag_metadata_translator"`.
  - Simplify the `Prompt` to remove JSON schema duplication.
    ```json
    {
      "Prompt": "Translate the metadata for the book. Title: '<title>', Author: '<author>'",
      "Role": "Chinese-to-Vietnamese Xianxia/Tu Chan Translator",
      "TypeName": "ag_metadata_translator"
    }
    ```
- **Step 5 (Chapter Translation)**:
  - Update `TypeName` from `"translator"` to `"ag_translator"`.
  - Remove the entire multi-line markdown template for `[Subagent Prompt]`.
  - Replace the `Prompt` in the JSON block with a clean injection of the dynamic variables, relying on the agent file for the static rules:
    ```json
    {
      "Prompt": "Please translate the assigned chapter.\n\n## Inputs\n- raw_path: [Absolute Path to raw_path]\n- style_path: [Absolute Path to style_path]\n- glossary_path: [Absolute Path to glossary_path]\n- prev_translation_path: [Absolute Path to prev_translation_path]\n- staged_txt: [Absolute Path to staging/chuong-{chapter_id:04d}-staged.txt]\n- staged_yaml: [Absolute Path to staging/chuong-{chapter_id:04d}-proposals.yaml]\n- chapter_id: [chapter_id]",
      "Role": "Chinese-to-Vietnamese Xianxia/Tu Chan Translator",
      "TypeName": "ag_translator"
    }
    ```

## Spec Self-Review
- [x] **Placeholder scan:** No unresolved "TODO"s.
- [x] **Internal consistency:** The architecture directly matches the approach approved by the user.
- [x] **Scope check:** Perfectly scoped to the two agent files and the one skill file.
- [x] **Ambiguity check:** The new prompt payload explicitly passes all required paths.
