"""Opt-in real Antigravity orchestrator smoke verification script.

This script tests the end-to-end orchestrator against a real local Antigravity
installation (`agy` CLI) using a disposable two-chapter workspace and local HTTP server.
No user books or external networks are touched.

Usage:
    python tests/smoke/run_agy_orchestrator.py [--model <slug>] [--keep]
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from dich_truyen_agent.orchestrator.models import OrchestratorConfig  # noqa: E402
from dich_truyen_agent.orchestrator.orchestrator import BookOrchestrator  # noqa: E402
from dich_truyen_agent.orchestrator.runners.agy import AgyRunner  # noqa: E402
from dich_truyen_agent.orchestrator.workspace_ops import WorkspaceOps  # noqa: E402
from dich_truyen_agent.workspace import initialize_workspace  # noqa: E402


class FixtureHttpHandler(BaseHTTPRequestHandler):
    pages: dict[str, tuple[int, dict[str, str], bytes]] = {}

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in self.pages:
            status, headers, content = self.pages[path]
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def log_message(self, format: str, *args) -> None:
        pass


def setup_fixture_server() -> tuple[HTTPServer, str]:
    server = HTTPServer(("127.0.0.1", 0), FixtureHttpHandler)
    host, port = server.server_address
    base_url = f"http://127.0.0.1:{port}"

    index_html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Smoke Test Novel</title></head>
<body>
<h1>Smoke Test Novel</h1>
<div class="chapters">
    <a href="{base_url}/ch1.html">第1章 仙人指路</a>
    <a href="{base_url}/ch2.html">第2章 炼气入体</a>
</div>
</body>
</html>
""".encode("utf-8")

    ch1_html = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>第1章 仙人指路</title></head>
<body>
<h1>第1章 仙人指路</h1>
<div class="content">
<p>大道初开，天地分阴阳。仙人指引凡人迈向长生大道。</p>
<p>少年站在青石台上，眺望远方的云雾山峰。</p>
</div>
</body>
</html>
""".encode("utf-8")

    ch2_html = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>第2章 炼气入体</title></head>
<body>
<h1>第2章 炼气入体</h1>
<div class="content">
<p>天地灵气汇聚丹田。少年屏气凝神，引导第一缕真气在体内运行。</p>
<p>气贯全身，经脉微热，标志着正式踏入修真门槛。</p>
</div>
</body>
</html>
""".encode("utf-8")

    FixtureHttpHandler.pages = {
        "/index.html": (200, {"Content-Type": "text/html; charset=utf-8"}, index_html),
        "/ch1.html": (200, {"Content-Type": "text/html; charset=utf-8"}, ch1_html),
        "/ch2.html": (200, {"Content-Type": "text/html; charset=utf-8"}, ch2_html),
    }

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, base_url


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run real Antigravity orchestrator smoke test"
    )
    parser.add_argument(
        "--model", type=str, default=None, help="Model slug to request from agy"
    )
    parser.add_argument(
        "--keep", action="store_true", help="Keep disposable workspace after test"
    )
    parser.add_argument(
        "--executable", type=str, default="agy", help="Path or name of agy CLI"
    )
    args = parser.parse_args()

    print("[smoke] Checking Antigravity CLI capability...")
    runner = AgyRunner(executable=args.executable)
    models = runner.get_available_models()

    if not models:
        print("[smoke] UNVERIFIED: No available models discovered from agy CLI.")
        print(
            "[smoke] Antigravity CLI is not installed or not authenticated on this system."
        )
        print("[smoke] Skipping opt-in real smoke test.")
        return 0

    print(
        f"[smoke] Discovered {len(models)} available models: {', '.join(models[:5])}..."
    )
    selected_model = args.model or models[0]
    print(f"[smoke] Using model: {selected_model}")

    # Set up local HTTP server
    server, base_url = setup_fixture_server()
    tmp_dir = Path(tempfile.mkdtemp(prefix="agy_smoke_"))
    print(f"[smoke] Created disposable workspace at: {tmp_dir}")

    try:
        # Initialize book
        init_res = initialize_workspace(
            workspace_root=tmp_dir,
            slug="smoke-book",
            title="Smoke Test Novel",
            source_url=f"{base_url}/index.html",
            author="Smoke Author",
            style_name="tien_hiep",
        )
        if init_res.status.value != "ok":
            print(f"[smoke] FAILED: workspace initialization failed: {init_res.reason}")
            return 1

        workspace_root = tmp_dir / "books" / "smoke-book"
        orchestrator = BookOrchestrator(runner=runner, ops=WorkspaceOps())

        print("[smoke] Running orchestrator: crawl -> export...")
        config = OrchestratorConfig(
            workspace_root=workspace_root,
            start_at="crawl",
            stop_after="export",
            global_model=selected_model,
            auto_approve=True,
            formats=["epub", "txt"],
        )
        outcome = orchestrator.start(config)

        print(
            f"[smoke] Orchestrator outcome: status={outcome.status}, exit_code={outcome.exit_code}"
        )
        if outcome.status != "completed":
            print(f"[smoke] FAILED: {outcome.error_message or outcome.blocker_reason}")
            return 1

        # Assertions
        summary_path = (
            workspace_root / "reports" / "runs" / outcome.run_id / "run_summary.json"
        )
        if not summary_path.is_file():
            print(f"[smoke] FAILED: missing run summary at {summary_path}")
            return 1

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["status"] == "completed"

        epub_path = workspace_root / "exports" / "smoke-book.epub"
        if not epub_path.is_file() or epub_path.stat().st_size == 0:
            print(f"[smoke] FAILED: expected EPUB export missing at {epub_path}")
            return 1

        print(
            "[smoke] PASSED: End-to-end real Antigravity orchestrator smoke succeeded!"
        )
        return 0
    finally:
        server.shutdown()
        server.server_close()
        if not args.keep:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        else:
            print(f"[smoke] Workspace retained at: {tmp_dir}")


if __name__ == "__main__":
    sys.exit(main())
