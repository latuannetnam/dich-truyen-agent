"""PreToolUse hook: block any Bash command that tries to call an external LLM API.

Mirrors `.agents/hooks/check_external_llm.py` (Antigravity), adapted for the Claude Code
hook payload format:
- payload["hook_event_name"] == "PreToolUse"
- payload["tool_name"] == "Bash" (also handles "Shell" defensively)
- payload["tool_input"]["command"] is the command string
- cwd is payload.get("cwd") or os.getcwd()

Output (stdout, JSON):
- Allow: {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}
- Deny:  {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                  "permissionDecision": "deny",
                                  "permissionDecisionReason": "..."}}

The hook fails OPEN: any unexpected exception allows the call, so a buggy hook
cannot wedge the agent. The guardrail is best-effort, not a security boundary.
"""
import sys
import os
import json
import re
from pathlib import Path

BANNED_ENV_VARS = [
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "DEEPSEEK_API_KEY",
]
BANNED_IMPORTS = [
    "openai",
    "anthropic",
    "google.generativeai",
    "openrouter",
]
BANNED_ENDPOINTS = [
    "api.openai.com",
    "openrouter.ai",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    "api.deepseek.com",
]

ALLOW = {
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
    }
}


def allow():
    print(json.dumps(ALLOW))


def deny(reason: str):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"[Translation Guardrail] Command blocked: {reason} "
                f"Use the native translator subagent (Agent tool with subagent_type=\"translator\") instead."
            ),
        }
    }))


def main():
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            allow()
            return

        payload = json.loads(raw)
        tool_name = payload.get("tool_name") or payload.get("toolName") or ""
        if tool_name not in ("Bash", "Shell"):
            allow()
            return

        tool_input = payload.get("tool_input") or payload.get("toolInput") or {}
        command_line = tool_input.get("command") or tool_input.get("CommandLine") or ""
        cwd = payload.get("cwd") or tool_input.get("Cwd") or os.getcwd()

        # 1) Direct string matches in the command line itself.
        for env in BANNED_ENV_VARS:
            if env in command_line:
                deny(f"Prohibited env variable '{env}' detected in command.")
                return

        for endpoint in BANNED_ENDPOINTS:
            if endpoint in command_line:
                deny(f"Prohibited external API endpoint '{endpoint}' detected in command.")
                return

        # 2) Scan any .py files referenced by the command.
        # Skip files inside .claude/hooks/ and .agents/hooks/ — those are guardrail
        # scripts which legitimately contain the banned constants and would otherwise
        # self-trigger when invoked for testing.
        py_files = re.findall(r"[\w\-./\\]+\.py\b", command_line)
        for py_file in py_files:
            normalized = py_file.replace("\\", "/").lower()
            if "/.claude/hooks/" in normalized or "/.agents/hooks/" in normalized \
                    or normalized.startswith(".claude/hooks/") \
                    or normalized.startswith(".agents/hooks/"):
                continue
            file_path = Path(cwd) / py_file
            try:
                if not (file_path.exists() and file_path.is_file()):
                    continue
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            for imp in BANNED_IMPORTS:
                pattern = r"(?:^|\s)(?:import|from)\s+" + re.escape(imp)
                if re.search(pattern, content):
                    deny(f"Banned library import '{imp}' detected in {py_file}.")
                    return

            for endpoint in BANNED_ENDPOINTS:
                if endpoint in content:
                    deny(f"Banned API endpoint '{endpoint}' referenced in code of {py_file}.")
                    return

        allow()
    except Exception:
        # Fail open: never block the user because the hook itself crashed.
        allow()


if __name__ == "__main__":
    main()
