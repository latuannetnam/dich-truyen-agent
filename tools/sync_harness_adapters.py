from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / ".harness" / "source"


@dataclass(frozen=True)
class RenderedFile:
    path: Path
    content: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(read_text(path))


def generated_header(manifest: dict) -> str:
    return manifest["generated_header"] + "\n\n"


def python_generated_header(manifest: dict) -> str:
    header = manifest["generated_header"]
    if header.startswith("<!--") and header.endswith("-->"):
        header = header[4:-3].strip()
    return f"# {header}\n\n"


def strip_existing_generated_header(content: str, manifest: dict) -> str:
    for header in (generated_header(manifest), python_generated_header(manifest)):
        if content.startswith(header):
            return content[len(header) :]
    return content


def skill_title(harness: str, skill: str) -> str:
    prefix = {"ag": "AG", "cc": "CC", "oc": "OC", "codex": "Codex"}[harness]
    words = " ".join(part.capitalize() for part in skill.split("-"))
    return f"{prefix}-{words}"


def skill_frontmatter(harness: str, skill: str) -> str:
    name = f"{harness}-{skill}"
    description = (
        f"Use when running the {skill} phase of the Chinese-to-Vietnamese "
        f"novel translation pipeline in the {harness} harness."
    )
    if harness == "ag":
        return (
            "---\n"
            f"name: \"{name}\"\n"
            f"description: \"{description}\"\n"
            "metadata:\n"
            f"  short-description: \"{description}\"\n"
            "---\n\n"
        )
    return "---\n" f"name: {name}\n" f"description: \"{description}\"\n" "---\n\n"


def translate_orchestration(harness: str) -> str:
    if harness == "oc":
        return """### Step 2: Run the Embedded Compact OpenCode Loop
The Main Agent fetches the next deterministic work item:
```bash
$env:PYTHONUTF8=1
uv run python main.py next-translation-work-item --workspace books/<book-slug> --json
```
* **If completed:** Report book completion with compact counts only.
* **If blocked:** Stop and report the gap to the user for repair.
* **If pending:** Continue with the next pending chapter inside this OpenCode skill loop.

### Step 3: Dispatch the Isolated OpenCode Worker
Use the OpenCode `task(` dispatch shown above with `subagent_type="general"` and `oc-translator` instructions, passing the absolute paths reported by `next-translation-work-item`, including `glossary_context_path`.

### Step 4: Lightweight Staging Verification
Run structural verification through the CLI:
```bash
$env:PYTHONUTF8=1
uv run python main.py verify-staged-chapter --workspace books/<book-slug> --chapter-id <chapter_id> --json
```
This does not replace glossary validation.

### Step 5: Atomically Promote and Continue
Promote the chapter:
```bash
$env:PYTHONUTF8=1
uv run python main.py promote-chapter --workspace books/<book-slug> --chapter-id <chapter_id> --json
```
If successful, loop back to Step 2 for the next pending chapter until the shared 5-chapter batch limit is reached.
If promotion is blocked by glossary consistency, retry the same chapter and include the `promote-chapter` reason in the translator prompt so the next attempt uses the existing glossary mapping and avoids rejected aliases.
* **Retries:** Retry failures up to 3 times with polite backoffs before halting.
* **Compact output:** Return only `{status, processed_count, chapter_start, chapter_end, next_chapter_id, failure_reason}`. Do not return cumulative chapter lists."""

    return """### Step 2: Fetch Progress and Dispatch Compact Coordinator
The Main Agent fetches the next deterministic work item:
```bash
$env:PYTHONUTF8=1
uv run python main.py next-translation-work-item --workspace books/<book-slug> --json
```
* **If completed:** Report book completion with compact counts only.
* **If blocked:** Stop and report the gap to the user for repair.
* **If pending:** The Main Agent spawns a **Coordinator Subagent** to handle the next 5 pending chapters using the harness-native dispatch block above.

> [!IMPORTANT]
> **Enforced Stateless Iteration:**
> 1. **Strict Batch Limit:** You must NEVER instruct a single Coordinator to translate the entire book. You must always specify the shared strict limit of 5 chapters in your prompt.
> 2. **Fresh Instances:** When the Coordinator completes its batch, you must spawn a completely NEW Coordinator instance. Do not send follow-up instructions to the previous subagent.
> 3. **Loop:** Repeat this cycle of spawning fresh Coordinators until `next-translation-work-item` returns `completed`.
> 4. **Compact Output:** Do not accumulate chapter arrays in the Main Agent. Re-query CLI state after each batch.

### Step 3: The Coordinator Micro-Loop
**The following steps (3 to 7) are executed purely by the Coordinator Subagent.**
Inside the Coordinator, fetch the exact next pending work item:
```bash
$env:PYTHONUTF8=1
uv run python main.py next-translation-work-item --workspace books/<book-slug> --json
```
Parse `data`. Stop on `completed`, `blocked`, or `error`.

### Step 4: Spawn the Translator Subagent (Coordinator)
The Coordinator spawns the Translator subagent using the harness-native mechanism in the dispatch block, passing the absolute paths reported by `next-translation-work-item`, including `glossary_context_path`.

### Step 5: Lightweight Staging Verification (Coordinator)
The Coordinator runs structural verification through the CLI:
```bash
$env:PYTHONUTF8=1
uv run python main.py verify-staged-chapter --workspace books/<book-slug> --chapter-id <chapter_id> --json
```
This does not replace glossary validation.

### Step 6: Atomically Promote and Loop (Coordinator)
The Coordinator promotes the chapter:
```bash
$env:PYTHONUTF8=1
uv run python main.py promote-chapter --workspace books/<book-slug> --chapter-id <chapter_id> --json
```
If successful, the Coordinator loops back to Step 3 until its assigned batch limit is reached.
If promotion is blocked by glossary consistency, retry the same chapter and include the `promote-chapter` reason in the translator prompt so the next attempt uses the existing glossary mapping and avoids rejected aliases.
* **Retries:** Coordinator retries failures up to 3 times with polite backoffs before halting.

### Step 7: Compact Coordinator Result
Return only `{status, processed_count, chapter_start, chapter_end, next_chapter_id, failure_reason}`. Do not return cumulative chapter lists or per-chapter logs."""


def render_skill(manifest: dict, harness: str, skill: str) -> RenderedFile:
    body = read_text(SOURCE / "skills" / f"{skill}.md")
    body = body.replace("{SKILL_TITLE}", skill_title(harness, skill))
    if skill == "translate-book":
        dispatch = read_text(SOURCE / "dispatch" / f"translate-{harness}.md").strip()
        body = body.replace("{TRANSLATE_DISPATCH}", dispatch)
        body = body.replace("{TRANSLATE_ORCHESTRATION}", translate_orchestration(harness))
    content = skill_frontmatter(harness, skill) + generated_header(manifest) + body.rstrip() + "\n"
    path = {
        "ag": ROOT / ".agent" / "skills" / f"ag-{skill}" / "SKILL.md",
        "cc": ROOT / ".claude" / "skills" / f"cc-{skill}" / "SKILL.md",
        "oc": ROOT / ".opencode" / "skill" / f"oc-{skill}" / "SKILL.md",
        "codex": ROOT / ".codex" / "skills" / f"codex-{skill}" / "SKILL.md",
    }[harness]
    return RenderedFile(path=path, content=content)


def agent_frontmatter(harness: str, agent: str) -> str:
    agent_name = f"{harness}_{agent.replace('-', '_')}"
    if harness == "oc":
        return (
            "---\n"
            f"description: \"Generated OpenCode {agent} agent.\"\n"
            "mode: subagent\n"
            "model: inherit\n"
            "hidden: true\n"
            "tools:\n"
            "  read: true\n"
            "  write: true\n"
            "  glob: true\n"
            "  grep: true\n"
            "  bash: false\n"
            "permission:\n"
            "  bash: deny\n"
            "---\n\n"
        )
    tools = "Bash, Read, InvokeSubagent" if agent == "coordinator" else "Read, Write, Glob, Grep"
    return (
        "---\n"
        f"name: {agent_name}\n"
        f"description: Generated {agent} agent for {harness}.\n"
        f"tools: {tools}\n"
        "model: inherit\n"
        "---\n\n"
    )


def render_agent(manifest: dict, harness: str, agent: str) -> RenderedFile | None:
    if agent == "coordinator" and harness == "oc":
        return None
    body = read_text(SOURCE / "agents" / f"{agent}.md")
    agent_file = f"{harness}_{agent.replace('-', '_')}.md"
    if harness == "oc":
        agent_file = f"oc-{agent}.md"
    path = {
        "ag": ROOT / ".agent" / "agents" / agent_file,
        "cc": ROOT / ".claude" / "agents" / agent_file,
        "oc": ROOT / ".opencode" / "agent" / agent_file,
        "codex": ROOT / ".codex" / "agents" / agent_file,
    }[harness]
    content = agent_frontmatter(harness, agent) + generated_header(manifest) + body.rstrip() + "\n"
    return RenderedFile(path=path, content=content)


def render_guides(manifest: dict) -> list[RenderedFile]:
    shared = read_text(SOURCE / "guides" / "shared-main-agent.md").rstrip()
    panels = [
        read_text(SOURCE / "guides" / "panels" / f"{harness}.md").rstrip()
        for harness in manifest["harnesses"]
    ]
    agents = (
        generated_header(manifest)
        + shared
        + "\n\n## Harness Capability Matrix\n\n"
        + "\n\n".join(panels)
        + "\n"
    )
    claude = (
        generated_header(manifest)
        + shared
        + "\n\n## Claude Code Capability Panel\n\n"
        + read_text(SOURCE / "guides" / "panels" / "cc.md").rstrip()
        + "\n"
    )
    return [
        RenderedFile(ROOT / "AGENTS.md", agents),
        RenderedFile(ROOT / "CLAUDE.md", claude),
    ]


def render_opencode_json(manifest: dict) -> RenderedFile:
    policy = read_json(SOURCE / "guardrails" / "external-llm-policy.json")
    bash_rules = {"*": "allow", "rm -rf /*": "deny"}
    for endpoint in policy["endpoints"]:
        bash_rules[f"*{endpoint}*"] = "deny"
    for env_var in policy["env_vars"]:
        bash_rules[f"*{env_var}*"] = "deny"
    for imp in ["import openai", "import anthropic", "from openai", "from anthropic"]:
        bash_rules[f"*{imp}*"] = "deny"

    skill_rules = {"*": "allow"}
    for name in manifest["skills"]:
        skill_rules[name] = "deny"
    for name in manifest.get("opencode_extra_denied_skills", []):
        skill_rules[name] = "deny"
    for prefix in ["ag", "cc", "codex"]:
        for name in manifest["skills"]:
            skill_rules[f"{prefix}-{name}"] = "deny"

    cfg = {
        "$schema": "https://opencode.ai/config.json",
        "plugin": ["superpowers@git+https://github.com/obra/superpowers.git"],
        "permission": {
            "bash": bash_rules,
            "skill": skill_rules,
            "edit": "allow",
            "read": "allow",
            "glob": "allow",
            "grep": "allow",
            "webfetch": "ask",
            "websearch": "ask",
        },
    }
    return RenderedFile(ROOT / "opencode.json", json.dumps(cfg, indent=2) + "\n")


def render_antigravity_hook(manifest: dict) -> RenderedFile:
    current = read_text(ROOT / ".agents" / "hooks" / "check_external_llm.py")
    body = strip_existing_generated_header(current, manifest)
    content = python_generated_header(manifest) + body.rstrip() + "\n"
    return RenderedFile(ROOT / ".agents" / "hooks" / "check_external_llm.py", content)


def render_claude_hook(manifest: dict) -> RenderedFile:
    current = read_text(ROOT / ".claude" / "hooks" / "check_external_llm.py")
    body = strip_existing_generated_header(current, manifest)
    content = python_generated_header(manifest) + body.rstrip() + "\n"
    return RenderedFile(ROOT / ".claude" / "hooks" / "check_external_llm.py", content)


def render_all() -> list[RenderedFile]:
    manifest = read_json(SOURCE / "manifest.json")
    rendered: list[RenderedFile] = []
    for harness in manifest["harnesses"]:
        for skill in manifest["skills"]:
            rendered.append(render_skill(manifest, harness, skill))
        for agent in manifest["agents"]:
            agent_file = render_agent(manifest, harness, agent)
            if agent_file is not None:
                rendered.append(agent_file)
    rendered.extend(render_guides(manifest))
    rendered.append(render_opencode_json(manifest))
    rendered.append(render_antigravity_hook(manifest))
    rendered.append(render_claude_hook(manifest))
    return rendered


def remove_legacy_outputs() -> None:
    for path in [
        ROOT / ".agent" / "skills" / "crawl-book",
        ROOT / ".agent" / "skills" / "translate-book",
        ROOT / ".agent" / "skills" / "check-translation",
        ROOT / ".agent" / "skills" / "export-book",
        ROOT / ".claude" / "skills" / "crawl-book",
        ROOT / ".claude" / "skills" / "translate-book",
        ROOT / ".claude" / "skills" / "check-translation",
        ROOT / ".claude" / "skills" / "export-book",
    ]:
        if path.exists():
            shutil.rmtree(path)

    for path in [
        ROOT / ".claude" / "agents" / "translator.md",
        ROOT / ".claude" / "agents" / "metadata_translator.md",
        ROOT / ".claude" / "agents" / "coordinator.md",
    ]:
        if path.exists():
            path.unlink()


def write_outputs(rendered: list[RenderedFile]) -> None:
    remove_legacy_outputs()
    for item in rendered:
        item.path.parent.mkdir(parents=True, exist_ok=True)
        item.path.write_text(item.content, encoding="utf-8", newline="\n")


def check_outputs(rendered: list[RenderedFile]) -> int:
    stale = []
    for item in rendered:
        if not item.path.is_file():
            stale.append(f"missing: {item.path.relative_to(ROOT)}")
            continue
        current = item.path.read_text(encoding="utf-8")
        if current != item.content:
            stale.append(f"stale: {item.path.relative_to(ROOT)}")
    if stale:
        print("Generated adapters are out of date:")
        for entry in stale:
            print(f"- {entry}")
        return 1
    print("all generated adapters are current")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    rendered = render_all()
    if args.check:
        return check_outputs(rendered)
    write_outputs(rendered)
    print(f"rendered {len(rendered)} generated adapters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
