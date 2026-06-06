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


def render_skill(manifest: dict, harness: str, skill: str) -> RenderedFile:
    body = read_text(SOURCE / "skills" / f"{skill}.md")
    body = body.replace("{SKILL_TITLE}", skill_title(harness, skill))
    if skill == "translate-book":
        dispatch = read_text(SOURCE / "dispatch" / f"translate-{harness}.md").strip()
        body = body.replace("{TRANSLATE_DISPATCH}", dispatch)
    content = generated_header(manifest) + skill_frontmatter(harness, skill) + body.rstrip() + "\n"
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
    content = generated_header(manifest) + agent_frontmatter(harness, agent) + body.rstrip() + "\n"
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
    for name in ["crawl-book", "translate-book", "check-translation", "export-book"]:
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
