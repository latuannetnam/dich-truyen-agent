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
