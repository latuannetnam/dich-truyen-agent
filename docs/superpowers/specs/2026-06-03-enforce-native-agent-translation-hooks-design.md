# Design: Enforce Native Agent Translation via Hooks

## Objective
Provide programmatic enforcement that prevents the main agent (or subagents) from making external API calls (e.g. OpenRouter, OpenAI, Gemini, etc.) during translation by utilizing Antigravity hooks on `PreToolUse` for the `run_command` tool.

## Proposed Changes

### 1. Workspace Hooks Configuration
Create `.agents/hooks.json` to register a hook intercepting `run_command`.

#### [NEW] [hooks.json](file:///d:/latuan/Programming/dich-truyen-agent/.agents/hooks.json)
```json
{
  "PreToolUse": [
    {
      "matcher": "run_command",
      "hooks": [
        {
          "command": "python .agents/hooks/check_external_llm.py"
        }
      ]
    }
  ]
}
```

### 2. Hook Script
Create `.agents/hooks/check_external_llm.py` which executes during `PreToolUse` to analyze `run_command` arguments. It will:
- Check environment variables inside command lines for banned keys.
- Extract any target `.py` files referenced in the command.
- Inspect the source code of those `.py` files for banned SDK imports or API endpoint hostnames.
- Return `deny` if violations are found, blocking execution.

#### [NEW] [check_external_llm.py](file:///d:/latuan/Programming/dich-truyen-agent/.agents/hooks/check_external_llm.py)
```python
import sys
import json
import re
from pathlib import Path

BANNED_ENV_VARS = ["OPENAI_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY"]
BANNED_IMPORTS = ["openai", "anthropic", "google.generativeai", "openrouter"]
BANNED_ENDPOINTS = [
    "api.openai.com",
    "openrouter.ai",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    "api.deepseek.com"
]

def main():
    try:
        payload = json.loads(sys.stdin.read())
        tool_call = payload.get("toolCall", {})
        tool_name = tool_call.get("name")
        arguments = tool_call.get("arguments", {})
        
        if tool_name != "run_command":
            allow()
            return
            
        command_line = arguments.get("CommandLine", "")
        cwd = arguments.get("Cwd", "")
        
        # Check command line direct string matches
        for env in BANNED_ENV_VARS:
            if env in command_line:
                deny(f"Prohibited env variable '{env}' detected in command.")
                return
                
        for endpoint in BANNED_ENDPOINTS:
            if endpoint in command_line:
                deny(f"Prohibited external API endpoint '{endpoint}' detected in command.")
                return
                
        # Parse python file scripts
        py_files = re.findall(r'[\w\-./\\]+\.py\b', command_line)
        for py_file in py_files:
            file_path = Path(cwd) / py_file
            if file_path.exists() and file_path.is_file():
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                
                # Check for imports
                for imp in BANNED_IMPORTS:
                    pattern = r'(?:^|\s)(?:import|from)\s+' + re.escape(imp)
                    if re.search(pattern, content):
                        deny(f"Banned library import '{imp}' detected in {py_file}.")
                        return
                
                # Check for endpoints referenced inside file
                for endpoint in BANNED_ENDPOINTS:
                    if endpoint in content:
                        deny(f"Banned API endpoint '{endpoint}' referenced in code of {py_file}.")
                        return

        allow()
    except Exception as e:
        allow()

def allow():
    print(json.dumps({"decision": "allow"}))

def deny(reason):
    print(json.dumps({
        "decision": "deny",
        "reason": f"[Antigravity Guardrail] Command blocked: {reason} Please use native 'invoke_subagent' instead."
    }))

if __name__ == "__main__":
    main()
```

## Verification Plan

### Automated Verification
Run a test script that triggers a tool execution using a banned environment variable or importing a banned library, and verify that the command execution is denied.

### Manual Verification
Attempt to run a dummy python script importing `openai` via `run_command` in terminal, and confirm it is blocked with the error message: `[Antigravity Guardrail] Command blocked...`
