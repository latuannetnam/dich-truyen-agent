"""Verify opencode.json contains the external-LLM guardrail deny rules."""
import json
from pathlib import Path

import pytest

OPENCODE_JSON = Path(__file__).parent.parent / "opencode.json"

DENIED_ENDPOINTS = [
    "api.openai.com",
    "openrouter.ai",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    "api.deepseek.com",
]
DENIED_ENV_VARS = [
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "DEEPSEEK_API_KEY",
]
DENIED_IMPORTS = [
    "import openai",
    "import anthropic",
    "from openai",
    "from anthropic",
]
REQUIRED_SAFETY = "rm -rf /*"


@pytest.fixture(scope="module")
def cfg() -> dict:
    assert OPENCODE_JSON.is_file(), f"Missing {OPENCODE_JSON}"
    return json.loads(OPENCODE_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def bash_rules(cfg) -> dict:
    perm = cfg.get("permission", {})
    bash_rules = perm.get("bash", {})
    assert isinstance(bash_rules, dict), "permission.bash must be an object"
    return bash_rules


def test_opencode_json_exists():
    assert OPENCODE_JSON.is_file()


def test_opencode_json_has_schema(cfg):
    assert cfg.get("$schema") == "https://opencode.ai/config.json"


def test_permission_bash_block_exists(cfg):
    assert "permission" in cfg, "permission block missing"
    assert "bash" in cfg["permission"], "permission.bash block missing"


@pytest.mark.parametrize("endpoint", DENIED_ENDPOINTS)
def test_endpoints_denied(bash_rules, endpoint):
    matches = [p for p in bash_rules if endpoint in p]
    assert matches, f"No deny rule covers endpoint {endpoint!r}"
    assert all(bash_rules[m] == "deny" for m in matches), (
        f"Endpoint {endpoint!r} covered by non-deny rule"
    )


@pytest.mark.parametrize("env_var", DENIED_ENV_VARS)
def test_env_vars_denied(bash_rules, env_var):
    matches = [p for p in bash_rules if env_var in p]
    assert matches, f"No deny rule covers env var {env_var!r}"
    assert all(bash_rules[m] == "deny" for m in matches), (
        f"Env var {env_var!r} covered by non-deny rule"
    )


@pytest.mark.parametrize("imp", DENIED_IMPORTS)
def test_imports_denied(bash_rules, imp):
    matches = [p for p in bash_rules if imp in p]
    assert matches, f"No deny rule covers import {imp!r}"
    assert all(bash_rules[m] == "deny" for m in matches), (
        f"Import {imp!r} covered by non-deny rule"
    )


def test_rm_rf_root_safety(bash_rules):
    assert REQUIRED_SAFETY in bash_rules, f"{REQUIRED_SAFETY!r} safety rule missing"
    assert bash_rules[REQUIRED_SAFETY] == "deny"


def test_broad_allow_base_first(bash_rules):
    """The first rule should be the broad `*` allow; deny rules come after."""
    keys = list(bash_rules.keys())
    assert keys[0] == "*", (
        f"First bash rule must be `*` (broad allow), got: {keys[0]!r}. "
        "opencode evaluates the LAST matching rule, so broad rules must come FIRST."
    )
    assert bash_rules["*"] == "allow", "Base `*` rule must be 'allow'"


# Tool-level permission contract per spec Section 7.
# These are siblings of `bash` inside the `permission` object.
EXPECTED_TOOL_PERMS = {
    "edit": "allow",
    "read": "allow",
    "glob": "allow",
    "grep": "allow",
    "webfetch": "ask",
    "websearch": "ask",
}


@pytest.mark.parametrize("tool,expected", list(EXPECTED_TOOL_PERMS.items()))
def test_tool_level_permission(cfg, tool, expected):
    """Tool-level permissions must match spec Section 7 exactly.

    A silent regression here (e.g., webfetch flipped to "allow") would
    disable the user-prompt safety the spec mandates, and the bash-rule
    tests do not cover this.
    """
    perm = cfg["permission"]
    assert tool in perm, f"permission.{tool} is missing"
    actual = perm[tool]
    assert actual == expected, (
        f"permission.{tool} must be {expected!r} per spec Section 7, got {actual!r}"
    )
