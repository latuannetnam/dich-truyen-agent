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

from dich_truyen_agent.models import BookMetadata, ChapterCatalog  # noqa: E402
from dich_truyen_agent.orchestrator.models import OrchestratorConfig  # noqa: E402
from dich_truyen_agent.orchestrator.orchestrator import BookOrchestrator  # noqa: E402
from dich_truyen_agent.orchestrator.runners.agy import AgyRunner  # noqa: E402
from dich_truyen_agent.orchestrator.workspace_ops import WorkspaceOps  # noqa: E402
from dich_truyen_agent.paths import workspace_paths  # noqa: E402
from dich_truyen_agent.styles import load_selected_style  # noqa: E402
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


def run_unified_prefix_smoke(args: argparse.Namespace) -> int:
    print("[smoke] Preflighting unified prefix smoke dependencies...")

    # 1. agy CLI
    runner = AgyRunner(executable=args.executable)
    models = runner.get_available_models()
    if not models:
        print("[smoke] UNVERIFIED: No available models discovered from agy CLI.")
        print(
            "[smoke] Antigravity CLI is not installed or not authenticated on this system."
        )
        return 0
    selected_model = args.model or models[0]
    print(f"[smoke] agy CLI OK. Using model: {selected_model}")

    # 2. EPUBCheck
    from dich_truyen_agent.export import find_calibre, find_epubcheck

    epubcheck = find_epubcheck()
    if not epubcheck:
        print(
            "[smoke] UNVERIFIED: EPUBCheck not found. Set DICH_TRUYEN_EPUBCHECK_PATH."
        )
        return 0
    print(f"[smoke] EPUBCheck OK: {epubcheck}")

    # 3. Calibre
    calibre = find_calibre()
    if not calibre:
        print(
            "[smoke] UNVERIFIED: Calibre ebook-convert not found. Set DICH_TRUYEN_CALIBRE_PATH."
        )
        return 0
    print(f"[smoke] Calibre OK: {calibre}")

    # 4. Crawl profile
    from dich_truyen_agent.crawl_profiles import (
        _source_host,
        load_active_crawl_profile,
    )

    try:
        dummy_ws = ROOT / "books" / "_probe"
        load_active_crawl_profile(ROOT, dummy_ws, args.source_url)
        print(
            f"[smoke] Crawl profile OK for source domain: {_source_host(args.source_url)}"
        )
    except Exception as e:
        print(f"[smoke] UNVERIFIED: Crawl profile check failed: {e}")
        return 0

    # 5. Source reachability
    import urllib.request

    try:
        req = urllib.request.Request(
            args.source_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status >= 400:
                print(f"[smoke] UNVERIFIED: Source URL returned HTTP {resp.status}")
                return 0
        print("[smoke] Source URL reachable.")
    except Exception as e:
        print(f"[smoke] UNVERIFIED: Source URL unreachable ({e})")
        return 0

    # 6. Generate unique slug (never remove an existing book workspace)
    import uuid

    unique_slug = args.slug or f"smoke-prefix-{uuid.uuid4().hex[:8]}"
    books_root = ROOT / "books"
    ws_paths = workspace_paths(books_root, unique_slug)
    if ws_paths.root.exists():
        print(
            f"[smoke] Error: workspace {ws_paths.root} already exists. Aborting to avoid overwrite."
        )
        return 1

    print(f"[smoke] Target unique slug: {unique_slug}")
    print(f"[smoke] Target workspace: {ws_paths.root}")

    # 7. Invoke unified command
    import subprocess

    cmd = [
        sys.executable,
        str(ROOT / "main.py"),
        "orchestrate",
        "--url",
        args.source_url,
        "--slug",
        unique_slug,
        "--style",
        args.style,
        "--limit",
        str(args.limit),
        "--formats",
        args.formats,
        "--yes",
        "--agy-model",
        selected_model,
    ]
    print(f"[smoke] Invoking command: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)

    print(f"[smoke] Command exit code: {proc.returncode}")
    if proc.stdout:
        print(f"[smoke] Output:\n{proc.stdout}")
    if proc.stderr:
        print(f"[smoke] Stderr:\n{proc.stderr}")

    # 8. Check exit code
    if proc.returncode == 2:
        print(
            "[smoke] Exit code 2 (paused): Gate approval paused safely for human review."
        )
        if ws_paths.crawl_report.is_file():
            print(f"[smoke] Crawl report: {ws_paths.crawl_report}")
        qa_rep = ws_paths.reports / "qa-report.yaml"
        if qa_rep.is_file():
            print(f"[smoke] QA report: {qa_rep}")
        print(f"[smoke] Workspace retained at: {ws_paths.root}")
        return 0

    if proc.returncode != 0:
        print(f"[smoke] FAILED: Orchestrator failed with exit code {proc.returncode}")
        return 1

    # 9. Verify completion invariants
    print("[smoke] Inspecting completed workspace outputs...")
    from dich_truyen_agent.checkpoints import check_gate
    from dich_truyen_agent.models import (
        BookState,
        ChapterCatalog,
        CheckpointType,
        StageStatus,
    )
    from dich_truyen_agent.scope import load_source_scope
    from dich_truyen_agent.storage import load_yaml_model

    assert ws_paths.source_scope.is_file(), "reports/source-scope.yaml missing"
    scope_rec = load_source_scope(ws_paths.source_scope)
    assert scope_rec.selected_count == args.limit, (
        f"selected_count={scope_rec.selected_count} != {args.limit}"
    )
    print(
        f"[smoke] Source scope OK: {scope_rec.mode.value} {scope_rec.selected_count} of {scope_rec.source_count}"
    )

    catalog = load_yaml_model(ws_paths.chapters, ChapterCatalog)
    assert len(catalog.chapters) == args.limit, (
        f"catalog chapters={len(catalog.chapters)} != {args.limit}"
    )
    print(f"[smoke] Chapter catalog OK: {len(catalog.chapters)} chapters")

    state = load_yaml_model(ws_paths.state, BookState)
    assert len(state.chapters) == args.limit
    for ch in state.chapters:
        assert ch.translation.status == StageStatus.COMPLETED
        trans_file = (
            ws_paths.translations
            / f"{ch.chapter_id:04d}-chuong-{ch.chapter_id:04d}.txt"
        )
        assert trans_file.is_file() and trans_file.stat().st_size > 0
    print(
        f"[smoke] State and translations OK: {len(state.chapters)} completed chapters"
    )

    crawl_gate = check_gate(ws_paths.root, CheckpointType.CRAWL_APPROVED)
    assert crawl_gate.status.value == "ok", (
        f"crawl gate not approved: {crawl_gate.reason}"
    )

    qa_gate = check_gate(ws_paths.root, CheckpointType.QA_APPROVED)
    assert qa_gate.status.value == "ok", f"qa gate not approved: {qa_gate.reason}"
    print("[smoke] Crawl and QA gates OK: approved")

    epub_file = ws_paths.exports / f"{unique_slug}.epub"
    pdf_file = ws_paths.exports / f"{unique_slug}.pdf"
    assert epub_file.is_file() and epub_file.stat().st_size > 0
    assert pdf_file.is_file() and pdf_file.stat().st_size > 0
    print(
        f"[smoke] Exports OK: {epub_file.name} ({epub_file.stat().st_size} bytes), {pdf_file.name} ({pdf_file.stat().st_size} bytes)"
    )

    print(f"[smoke] PASSED: Unified prefix smoke succeeded for slug: {unique_slug}")
    if args.cleanup:
        shutil.rmtree(ws_paths.root, ignore_errors=True)
        print(f"[smoke] Cleaned up workspace: {ws_paths.root}")
    else:
        print(f"[smoke] Preserved workspace for diagnosis: {ws_paths.root}")
    return 0


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
    parser.add_argument(
        "--unified-prefix-smoke",
        action="store_true",
        help="Run live unified prefix smoke against Piaotian URL",
    )
    parser.add_argument(
        "--source-url",
        type=str,
        default="https://www.piaotia.com/html/14/14959/index.html",
        help="Source novel URL for unified prefix smoke",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Scope limit for unified prefix smoke (default: 3)",
    )
    parser.add_argument(
        "--style",
        type=str,
        default="tien_hiep",
        help="Style profile for unified prefix smoke (default: tien_hiep)",
    )
    parser.add_argument(
        "--formats",
        type=str,
        default="epub,pdf",
        help="Export formats for unified prefix smoke (default: epub,pdf)",
    )
    parser.add_argument(
        "--slug",
        type=str,
        default=None,
        help="Explicit slug for unified prefix smoke",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Clean up workspace after successful unified prefix smoke",
    )
    args = parser.parse_args()

    if args.unified_prefix_smoke:
        return run_unified_prefix_smoke(args)

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
        style = load_selected_style(ROOT, Path("tien_hiep"))
        metadata = BookMetadata(
            book_slug="smoke-book",
            title="Smoke Test Novel",
            source_url=f"{base_url}/index.html",
            author="Smoke Author",
        )
        init_res = initialize_workspace(
            books_root=tmp_dir,
            metadata=metadata,
            catalog=ChapterCatalog(),
            style=style,
        )
        if init_res.status.value != "ok":
            print(f"[smoke] FAILED: workspace initialization failed: {init_res.reason}")
            return 1

        workspace_root = workspace_paths(tmp_dir, "smoke-book").root
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
