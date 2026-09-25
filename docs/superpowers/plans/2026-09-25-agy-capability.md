# Antigravity CLI (agy) Target Installation Capability Record

- **Date:** 2026-09-25
- **Platform:** Windows 11 (win32, x86_64)
- **Target CLI Executable:** `C:\Users\latuan\AppData\Local\agy\bin\agy.exe`
- **Reported CLI Version:** `1.2.11`

---

## 1. Verified CLI Commands and Invocations

### Version and Help
- `agy --version` -> exits `0`, returns `1.2.11`.
- `agy --help` -> exits `0`, lists standard flags and subcommands.

### Headless Non-Interactive Prompt Form
- **Command Syntax:**
  `agy -p "<prompt>" --output-format json`
  or
  `agy --print "<prompt>" --output-format json`
- Supported output formats: `text`, `json`, `stream-json`.
- **Verified JSON Output Structure:**
  ```json
  {
    "conversation_id": "05216feb-2c07-4bba-88ea-06045b173e50",
    "status": "SUCCESS",
    "response": "PONG\n",
    "duration_seconds": 4.2214351,
    "num_turns": 1,
    "usage": {
      "input_tokens": 15653,
      "output_tokens": 421,
      "thinking_tokens": 419,
      "cache_read_tokens": 0,
      "total_tokens": 16074
    }
  }
  ```
- **Exit Codes:**
  - Exit code `0` on successful prompt completion (`status: "SUCCESS"`).
  - Exit code `1` on invalid arguments / unrecognized model (`status: "ERROR"` with descriptive `error` field in JSON and on stderr).

### Internal Timeouts vs. Wall-Clock Process Tree Supervision
- `--print-timeout <duration>` (e.g. `--print-timeout 5s`):
  - When `--print-timeout` expires internally during a turn, `agy` prints `[agy] print timeout after <duration> with turn in progress; returning partial output` and exits with **code 0** and partial output.
  - **Critical Invariant:** Relying on `agy`'s internal `--print-timeout` does not guarantee a failing/nonzero exit code or process tree termination. The orchestrator's Windows process supervisor (`run_process` with Job Object and external wall-clock timeout) is authoritative and required to terminate child processes and report `timed_out = True`.

### Permissions and File Restrictions
- Without `--dangerously-skip-permissions`:
  - When non-interactive tools modify workspace files, operations pause or timeout awaiting interactive authorization.
- With `--dangerously-skip-permissions`:
  - Tool permission prompts are bypassed.
  - As mandated by the spec, `--dangerously-skip-permissions` must **never** be used by default and must be an explicit operator opt-in flag (`--allow-harness-permission-bypass`), recorded in the run summary.

---

## 2. Models and Discovery

### Model Listing
- `agy models` exits `0`, listing available model slugs:
  - `gemini-3.8-flash-high`
  - `gemini-3.8-flash-medium`
  - `gemini-3.8-flash-low`
  - `gemini-3.7-flash-high`
  - `gemini-3.7-flash-medium`
  - `gemini-3.7-flash-low`
  - `gemini-3.6-flash-high`
  - `gemini-3.6-flash-medium`
  - `gemini-3.6-flash-low`
  - `gemini-3.1-pro-high`
  - `gemini-3.1-pro-low`
  - `claude-sonnet-4-6`
  - `claude-opus-4-6-thinking`
  - `gpt-oss-120b-medium`

### Model Selection (`--model <slug>`)
- Passing `--model <valid-slug>` sets the session model.
- Passing an unrecognized model (e.g. `--model nonexistent-model-slug`) immediately exits with **code 1**, emits an error on stderr, and returns a JSON payload with `status: "ERROR"`.
- Effective-model visibility: `agy` JSON output does not report the effective model slug used in the response; it reports token usage and timing only. An unreported effective model must be recorded as unknown in run summaries unless explicitly reported by CLI metadata.

---

## 3. Custom Agent Discovery and Capability Evaluation

- **Subcommand `agy agents`:**
  - Exits `0` with empty output on the target installation.
- **Flag `--agent <name>`:**
  - Flag is accepted by `agy` without error.
  - When `--agent ag_translator` or `--agent nonexistent_agent` is passed to a headless prompt, `agy 1.2.11` runs the default general coding assistant persona rather than loading custom instructions from `.agent/agents/ag_translator.md`.
- **Capability Gate Status for Native Agent Dispatch:**
  - Status: **Blocked / Unverified for direct CLI `--agent ag_translator` selection** in `agy 1.2.11`.
  - **Resolution / Fallback according to Spec & Plan:**
    Per Spec Section 3 and Plan Task 1:
    "A missing agy capability remains explicitly unverified, not a passing test. If unavailable, record the blocker and continue only deterministic/mock tasks."
    For deterministic tasks, mock runner, and headless prompt injection: `AgyRunner` will support headless prompt execution and pass `--model <slug>` and `--dangerously-skip-permissions` (when opted in). For agent personas, when direct `--agent` is unsupported by the binary, the agent instructions from `.harness/source/agents/translator.md` can be injected directly into the headless prompt context or operated via mock runner during tests.

---

## 4. LangGraph and SQLite Checkpointer Resolved Dependencies

- **Python Runtime:** 3.13.3 (Windows x86_64)
- **Resolved Package Versions:**
  - `langgraph`: `1.2.12`
  - `langgraph-checkpoint`: `4.2.0`
  - `langgraph-checkpoint-sqlite`: `3.1.1`
- **APIs Verified:**
  - `langgraph.graph.StateGraph`, `START`, `END`
  - `langgraph.types.interrupt`, `langgraph.types.Command(resume=...)`
  - `langgraph.checkpoint.sqlite.SqliteSaver`
  - Checkpointer deserializer: `JsonPlusSerializer` (safe JSON / orjson / msgpack deserialization, no arbitrary pickle execution).
