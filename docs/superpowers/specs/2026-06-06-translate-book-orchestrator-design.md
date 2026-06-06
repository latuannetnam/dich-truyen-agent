# Translate Book Middle-Tier Orchestrator Design

## Goal
Optimize the `translate-book` skill to handle large books (>100 chapters) by preventing the Main Agent from exhausting its context window during the chapter-by-chapter sequential loop.

## Architecture: Middle-Tier Orchestrator Pattern
To achieve infinite scalability and optimal context preservation, we introduce a nested subagent hierarchy.

### 1. Main Agent (The Dispatcher)
The Main Agent shifts from a micro-manager to a high-level dispatcher.
* **Responsibilities:**
  * Verify the `crawl-approved` gate.
  * Check and translate book metadata (`book.yaml`).
  * Run a macro-loop: query overall translation progress. If chapters remain, spawn a **Coordinator Subagent** to translate the next batch of chapters (e.g., 20 at a time).
  * Wait for the Coordinator to complete, then query progress again. 
* **Context Benefit:** The Main Agent only consumes one tool call per 20 chapters. The Coordinator's history is wiped automatically upon return, preserving the Main Agent's context infinitely.

### 2. Coordinator Subagent (`ag_coordinator`)
A new middle-tier subagent type responsible for executing the translation loop for a specific chunk of chapters.
* **Responsibilities:**
  * Loop up to X times (batch size).
  * Run `show-translation-progress` and `prepare-translation-context` CLI commands.
  * Invoke the **Translator Subagent** via `invoke_subagent` for a single chapter.
  * Run `view_file` on the first 3 lines of the staging output for sanity checking.
  * Run the `promote-chapter` CLI command.
  * If a hard error occurs or the batch size is reached, return control to the Main Agent.

### 3. Translator Subagent (`ag_translator`)
Remains strictly identical to its current implementation.
* **Responsibilities:**
  * Take absolute paths for raw files and context files for a single chapter.
  * Translate the content.
  * Exit.
* **Benefit:** Ensures that translation quality is not compromised by trying to stuff multiple chapters into a single LLM prompt.

## Error Handling & Retries
* The Coordinator will handle the 3 transient retries for the Translator subagent.
* If a chapter permanently fails, the Coordinator will halt and return an error to the Main Agent, which will then halt the workflow and report the gap to the user.

## Boundaries and Data Flow
* **Main Agent <-> Coordinator:** Main Agent passes the goal (e.g., "translate 20 chapters starting from current progress") and the Coordinator returns a success/failure status.
* **Coordinator <-> Translator:** Coordinator passes the exact absolute file paths for one chapter. Translator returns a success status once the staging files are written.

## Updates to Existing Files
* `AGENTS.md`: Update the global orchestration guide to reflect the Middle-Tier Orchestrator pattern and nested subagent delegation.
* `.agent/skills/translate-book/SKILL.md`: Update instructions to describe the macro-loop (Main Agent) and micro-loop (Coordinator).
* `.claude/skills/translate-book/SKILL.md`: (If applicable, apply parallel updates).
