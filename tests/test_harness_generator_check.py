"""Verify generated harness adapters stay in sync with canonical sources."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SYNC = ROOT / "tools" / "sync_harness_adapters.py"


def test_sync_script_exists():
    assert SYNC.is_file(), f"Missing {SYNC}"


def test_sync_check_mode_reports_clean_tree():
    result = subprocess.run(
        [sys.executable, str(SYNC), "--check"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert "all generated adapters are current" in result.stdout
