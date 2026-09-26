from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / ".harness" / "source"

OBSOLETE_GENERATED_PATHS = [
    # Legacy unprefixed skill folders
    ROOT / ".agent" / "skills" / "crawl-book",
    ROOT / ".agent" / "skills" / "translate-book",
    ROOT / ".agent" / "skills" / "check-translation",
    ROOT / ".agent" / "skills" / "export-book",
    ROOT / ".claude" / "skills" / "crawl-book",
    ROOT / ".claude" / "skills" / "translate-book",
    ROOT / ".claude" / "skills" / "check-translation",
    ROOT / ".claude" / "skills" / "export-book",
    # Retired agent and workflow adapters
    ROOT / ".agent" / "agents" / "ag_coordinator.md",
    ROOT / ".claude" / "agents" / "cc_coordinator.md",
    ROOT / ".claude" / "agents" / "cc_metadata_translator.md",
    ROOT / ".claude" / "agents" / "cc_translator.md",
    ROOT / ".claude" / "agents" / "translator.md",
    ROOT / ".claude" / "agents" / "metadata_translator.md",
    ROOT / ".claude" / "agents" / "coordinator.md",
    ROOT / ".claude" / "workflows" / "translate-book.js",
    ROOT / ".opencode" / "agent" / "oc-metadata-translator.md",
    ROOT / ".opencode" / "agent" / "oc-translator.md",
    ROOT / ".codex" / "agents" / "codex_coordinator.md",
    ROOT / ".codex" / "agents" / "codex_metadata_translator.md",
    ROOT / ".codex" / "agents" / "codex_translator.md",
]


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
            f'name: "{name}"\n'
            f'description: "{description}"\n'
            "metadata:\n"
            f'  short-description: "{description}"\n'
            "---\n\n"
        )
    return f'---\nname: {name}\ndescription: "{description}"\n---\n\n'


def render_skill(manifest: dict, harness: str, skill: str) -> RenderedFile:
    body = read_text(SOURCE / "skills" / f"{skill}.md")
    body = body.replace("{SKILL_TITLE}", skill_title(harness, skill))
    content = (
        skill_frontmatter(harness, skill)
        + generated_header(manifest)
        + body.rstrip()
        + "\n"
    )
    path = {
        "ag": ROOT / ".agent" / "skills" / f"ag-{skill}" / "SKILL.md",
        "cc": ROOT / ".claude" / "skills" / f"cc-{skill}" / "SKILL.md",
        "oc": ROOT / ".opencode" / "skill" / f"oc-{skill}" / "SKILL.md",
        "codex": ROOT / ".codex" / "skills" / f"codex-{skill}" / "SKILL.md",
    }[harness]
    return RenderedFile(path=path, content=content)


def agent_frontmatter(harness: str, agent: str) -> str:
    agent_name = f"{harness}_{agent.replace('-', '_')}"
    tools = "Read, Write, Glob, Grep"
    return (
        "---\n"
        f"name: {agent_name}\n"
        f"description: Generated {agent} agent for {harness}.\n"
        f"tools: {tools}\n"
        "model: inherit\n"
        "---\n\n"
    )


def render_agent(manifest: dict, harness: str, agent: str) -> RenderedFile | None:
    if harness != "ag":
        return None
    body = read_text(SOURCE / "agents" / f"{agent}.md")
    agent_file = f"ag_{agent.replace('-', '_')}.md"
    path = ROOT / ".agent" / "agents" / agent_file
    content = (
        agent_frontmatter("ag", agent)
        + generated_header(manifest)
        + body.rstrip()
        + "\n"
    )
    return RenderedFile(path=path, content=content)


def render_guides(manifest: dict) -> list[RenderedFile]:
    shared = read_text(SOURCE / "guides" / "shared-main-agent.md").rstrip()
    panels = [
        read_text(SOURCE / "guides" / "panels" / f"{harness}.md").rstrip()
        for harness in manifest["harnesses"]
    ]
    profile_panels = [
        read_text(SOURCE / "guides" / "panels" / f"{profile}.md").rstrip()
        for profile in manifest.get("guide_profiles", [])
    ]
    agents = (
        generated_header(manifest)
        + shared
        + "\n\n## Harness Capability Matrix\n\n"
        + "\n\n".join(panels + profile_panels)
        + "\n"
    )
    claude_sections = [
        read_text(SOURCE / "guides" / "panels" / "cc.md").rstrip(),
        *profile_panels,
    ]
    claude = (
        generated_header(manifest)
        + shared
        + "\n\n## Claude Code Capability Panel\n\n"
        + "\n\n".join(claude_sections)
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
        agent_file = render_agent(manifest, "ag", agent)
        if agent_file is not None:
            rendered.append(agent_file)
    rendered.extend(render_guides(manifest))
    rendered.append(render_opencode_json(manifest))
    rendered.append(render_antigravity_hook(manifest))
    rendered.append(render_claude_hook(manifest))
    return rendered


def remove_legacy_outputs() -> None:
    for path in OBSOLETE_GENERATED_PATHS:
        if not path.resolve().is_relative_to(ROOT.resolve()):
            continue
        if path.is_dir():
            shutil.rmtree(path)
        elif path.is_file():
            path.unlink()

    workflows_dir = ROOT / ".claude" / "workflows"
    if workflows_dir.is_dir() and not any(workflows_dir.iterdir()):
        workflows_dir.rmdir()


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

    obsolete = []
    for path in OBSOLETE_GENERATED_PATHS:
        if path.exists():
            obsolete.append(f"obsolete: {path.relative_to(ROOT)}")

    if stale or obsolete:
        print("Generated adapters are out of date:")
        for entry in stale + obsolete:
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
