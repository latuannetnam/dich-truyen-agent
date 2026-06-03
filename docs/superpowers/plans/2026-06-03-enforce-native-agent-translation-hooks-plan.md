# Enforce Native Agent Translation via Hooks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create an Antigravity workspace hook to prevent external LLM API keys and SDK libraries from being used via commands.

**Architecture:** Create `.agents/hooks.json` to register a hook on `PreToolUse` for `run_command`. Implement a Python script `.agents/hooks/check_external_llm.py` that parses the command and targets, analyzes their code/environment variables, and returns an `allow` or `deny` decision JSON payload. Create a unit test `tests/test_hooks.py` to verify the script logic.

**Tech Stack:** Python, JSON

---

### Task 1: Create the Hook Script and Config

**Files:**
- Create: `.agents/hooks.json`
- Create: `.agents/hooks/check_external_llm.py`

- [ ] **Step 1: Create the Hook Config file**

Create the file `.agents/hooks.json` with the following content:
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

- [ ] **Step 2: Create the Guardrail Script**

Create the file `.agents/hooks/check_external_llm.py` with the following content:
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

- [ ] **Step 3: Commit Hook Files**

```bash
git add .agents/hooks.json .agents/hooks/check_external_llm.py
git commit -m "feat: add hooks config and check_external_llm script"
```

---

### Task 2: Implement Unit Tests and Verify

**Files:**
- Create: `tests/test_hooks.py`

- [ ] **Step 1: Create unit test file for the guardrail hook**

Create the file `tests/test_hooks.py` with the following content:
```python
import json
import subprocess
import sys
from pathlib import Path

HOOK_SCRIPT = str(Path(".agents/hooks/check_external_llm.py").absolute())

def run_hook(stdin_data):
    res = subprocess.run(
        [sys.executable, HOOK_SCRIPT],
        input=json.dumps(stdin_data),
        text=True,
        capture_output=True,
        check=True
    )
    return json.loads(res.stdout.strip())

def test_hook_allows_normal_command():
    payload = {
        "toolCall": {
            "name": "run_command",
            "arguments": {
                "CommandLine": "uv run python main.py check-gate --workspace books/test --type crawl-approved",
                "Cwd": "."
            }
        }
    }
    result = run_hook(payload)
    assert result["decision"] == "allow"

def test_hook_denies_banned_env_vars():
    payload = {
        "toolCall": {
            "name": "run_command",
            "arguments": {
                "CommandLine": "$env:OPENAI_API_KEY='123'; python test.py",
                "Cwd": "."
            }
        }
    }
    result = run_hook(payload)
    assert result["decision"] == "deny"
    assert "OPENAI_API_KEY" in result["reason"]

def test_hook_denies_banned_imports(tmp_path):
    # Create a temp python file that imports openai
    bad_script = tmp_path / "bad_script.py"
    bad_script.write_text("import openai\nprint('hello')")
    
    payload = {
        "toolCall": {
            "name": "run_command",
            "arguments": {
                "CommandLine": f"python {bad_script.name}",
                "Cwd": str(tmp_path)
            }
        }
    }
    result = run_hook(payload)
    assert result["decision"] == "deny"
    assert "Banned library import 'openai'" in result["reason"]
```

- [ ] **Step 2: Run pytest to verify the hook tests pass**

Run: `uv run pytest tests/test_hooks.py`
Expected output: 3 passed

- [ ] **Step 3: Commit test file**

```bash
git add tests/test_hooks.py
git commit -m "test: add unit tests for check_external_llm hook"
```
