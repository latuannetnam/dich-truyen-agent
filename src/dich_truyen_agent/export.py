from __future__ import annotations

import html
import io
import os
import shutil
import subprocess
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from dich_truyen_agent.checkpoints import check_gate
from dich_truyen_agent.models import (
    BookMetadata,
    ChapterCatalog,
    CheckpointType,
    OperationResult,
    OperationStatus,
    ProgressSummary,
)
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.storage import load_yaml_model


def compile_epub_in_memory(
    workspace_root: Path,
    book_metadata: BookMetadata,
    catalog: ChapterCatalog,
) -> bytes:
    """Compile the EPUB 3.3 ebook completely in memory to verify zip and mimetype invariants."""
    buffer = io.BytesIO()

    # 1. Generate deterministic UUID based on source URL
    pub_id = str(uuid.uuid5(uuid.NAMESPACE_URL, book_metadata.source_url))
    modified_time = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    author = book_metadata.author or "Unknown"

    # 2. Build standard templates
    style_content = """body {
    font-family: Georgia, serif;
    margin: 5%;
    line-height: 1.6;
    font-size: 1em;
}
h1, h2, h3 {
    text-align: center;
    font-family: sans-serif;
    margin-top: 1.5em;
    margin-bottom: 0.5em;
}
p {
    text-indent: 1.5em;
    margin-bottom: 0.5em;
    text-align: justify;
}
"""

    container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

    # 3. Read chapter files and parse titles & paragraphs
    chapters_xhtml: dict[int, str] = {}
    nav_items: list[str] = []
    manifest_items: list[str] = []
    spine_items: list[str] = []

    for entry in catalog.chapters:
        ch_id = entry.chapter_id
        trans_file = workspace_root / "translations" / entry.translation_filename

        # Read text, falling back to original title if missing
        if trans_file.is_file():
            text = trans_file.read_text(encoding="utf-8")
        else:
            text = ""

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if lines:
            ch_title = lines[0]
            paragraphs_list = lines[1:]
        else:
            ch_title = entry.original_title
            paragraphs_list = []

        escaped_title = html.escape(ch_title)
        paragraphs_html = "\n".join(
            f"    <p>{html.escape(p)}</p>" for p in paragraphs_list
        )

        ch_xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="vi" xml:lang="vi">
<head>
  <title>{escaped_title}</title>
  <meta charset="utf-8"/>
  <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
  <section epub:type="chapter" id="chapter-{ch_id}">
    <h1>{escaped_title}</h1>
{paragraphs_html}
  </section>
</body>
</html>
"""
        chapters_xhtml[ch_id] = ch_xhtml

        # Add to OPF spine & manifest
        filename = f"chapter_{ch_id:04d}.xhtml"
        manifest_items.append(
            f'    <item id="chapter_{ch_id:04d}" href="{filename}" media-type="application/xhtml+xml"/>'
        )
        spine_items.append(f'    <itemref idref="chapter_{ch_id:04d}"/>')
        nav_items.append(f'        <li><a href="{filename}">{escaped_title}</a></li>')

    # 4. Build Navigation document
    nav_xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="vi" xml:lang="vi">
<head>
  <title>Mục lục</title>
  <meta charset="utf-8"/>
  <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
  <nav epub:type="toc" id="toc">
    <h1>Mục lục</h1>
    <ol>
{"\n".join(nav_items)}
    </ol>
  </nav>
</body>
</html>
"""

    # 5. Build OPF package document
    manifest_str = "\n".join(manifest_items)
    spine_str = "\n".join(spine_items)

    package_opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="pub-id" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">urn:uuid:{pub_id}</dc:identifier>
    <dc:title>{html.escape(book_metadata.title)}</dc:title>
    <dc:language>vi</dc:language>
    <dc:creator>{html.escape(author)}</dc:creator>
    <meta property="dcterms:modified">{modified_time}</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="style" href="style.css" media-type="text/css"/>
{manifest_str}
  </manifest>
  <spine>
    <itemref idref="nav"/>
{spine_str}
  </spine>
</package>
"""

    # 6. Write ZIP archive with strict EPUB invariants
    with zipfile.ZipFile(buffer, "w") as zf:
        # First entry MUST be mimetype, stored (uncompressed)
        zf.writestr(
            "mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED
        )

        # Subsequent entries are compressed
        zf.writestr(
            "META-INF/container.xml", container_xml, compress_type=zipfile.ZIP_DEFLATED
        )
        zf.writestr("EPUB/style.css", style_content, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("EPUB/package.opf", package_opf, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("EPUB/nav.xhtml", nav_xhtml, compress_type=zipfile.ZIP_DEFLATED)

        for ch_id, ch_xhtml in chapters_xhtml.items():
            zf.writestr(
                f"EPUB/chapter_{ch_id:04d}.xhtml",
                ch_xhtml,
                compress_type=zipfile.ZIP_DEFLATED,
            )

    return buffer.getvalue()


def verify_epub_invariants(epub_bytes: bytes) -> None:
    """Perform internal checks to verify ZIP and EPUB mimetype constraints."""
    with zipfile.ZipFile(io.BytesIO(epub_bytes)) as zf:
        infolist = zf.infolist()
        if not infolist:
            raise ValueError("empty EPUB archive")

        # First entry must be mimetype
        first = infolist[0]
        if first.filename != "mimetype":
            raise ValueError(
                f"EPUB violation: first zip entry must be 'mimetype', got {first.filename!r}"
            )

        if first.compress_type != zipfile.ZIP_STORED:
            raise ValueError(
                "EPUB violation: 'mimetype' entry must be stored (uncompressed)"
            )

        mimetype_content = zf.read("mimetype").decode("utf-8")
        if mimetype_content != "application/epub+zip":
            raise ValueError(
                f"EPUB violation: 'mimetype' must contain 'application/epub+zip', got {mimetype_content!r}"
            )

        # Check container file exists
        if "META-INF/container.xml" not in zf.namelist():
            raise ValueError("EPUB violation: missing 'META-INF/container.xml'")


def find_epubcheck() -> tuple[Path | str | None, bool]:
    """Find EPUBCheck tool in system PATH or environment variable.
    Returns (path_or_command, is_jar)."""
    env_path = os.environ.get("DICH_TRUYEN_EPUBCHECK_PATH")
    if env_path:
        candidate = Path(env_path)
        if candidate.is_file():
            if env_path.endswith(".jar"):
                return candidate, True
            return candidate, False
        elif candidate.is_dir():
            jar_candidate = candidate / "epubcheck.jar"
            if jar_candidate.is_file():
                return jar_candidate, True

    # Search system PATH for epubcheck command
    which_epubcheck = shutil.which("epubcheck")
    if which_epubcheck:
        return which_epubcheck, False

    return None, False


def run_epubcheck(epub_path: Path) -> OperationResult:
    """Run EPUBCheck CLI on the generated EPUB file."""
    tool_path, is_jar = find_epubcheck()
    if not tool_path:
        return OperationResult(
            status=OperationStatus.BLOCKED,
            reason=(
                "EPUBCheck is missing or not configured. To compile and validate conformant EPUB 3.3 ebooks, "
                "please download EPUBCheck 5.3.0 from https://github.com/w3c/epubcheck/releases and ensure Java is installed. "
                "Set your environment variable DICH_TRUYEN_EPUBCHECK_PATH to the epubcheck.jar file or folder, and run again."
            ),
        )

    if is_jar:
        # Verify Java is in PATH
        java_path = shutil.which("java")
        if not java_path:
            return OperationResult(
                status=OperationStatus.BLOCKED,
                reason="Java is required to run epubcheck.jar, but was not found in system PATH.",
            )
        cmd = ["java", "-jar", str(tool_path), str(epub_path)]
    else:
        cmd = [str(tool_path), str(epub_path)]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            return OperationResult(
                status=OperationStatus.ERROR,
                reason=f"EPUBCheck validation failed (exit code {res.returncode}):\n{res.stderr or res.stdout}",
            )
    except Exception as e:
        return OperationResult(
            status=OperationStatus.ERROR, reason=f"EPUBCheck execution failed: {e}"
        )

    return OperationResult(
        status=OperationStatus.OK, reason="EPUBCheck validation passed successfully"
    )


def find_calibre() -> Path | str | None:
    """Locate Calibre's ebook-convert tool."""
    env_path = os.environ.get("DICH_TRUYEN_CALIBRE_PATH")
    if env_path:
        candidate = Path(env_path)
        if candidate.is_file():
            return candidate
        # If directory was specified, try finding the executable inside it
        exe_name = "ebook-convert.exe" if os.name == "nt" else "ebook-convert"
        if (candidate / exe_name).is_file():
            return candidate / exe_name

    # Standard installation paths on Windows
    if os.name == "nt":
        windows_defaults = [
            Path(r"C:\Program Files\Calibre2\ebook-convert.exe"),
            Path(r"C:\Program Files (x86)\Calibre2\ebook-convert.exe"),
        ]
        for path in windows_defaults:
            if path.is_file():
                return path

    # Search system PATH
    which_calibre = shutil.which("ebook-convert")
    if which_calibre:
        return which_calibre

    return None


def run_calibre_convert(epub_path: Path, output_format: str) -> OperationResult:
    """Run Calibre ebook-convert to generate derivative formats (azw3, mobi, pdf)."""
    calibre_bin = find_calibre()
    output_format = output_format.lower().strip()
    dest_path = epub_path.with_suffix(f".{output_format}")

    if not calibre_bin:
        # Since Calibre is optional, warn the user instead of failing the run
        return OperationResult(
            status=OperationStatus.BLOCKED,
            reason=(
                "Calibre 'ebook-convert' is missing. Skip derivative format conversions. "
                "To resolve, download Calibre and ensure ebook-convert is in your PATH, "
                "or set DICH_TRUYEN_CALIBRE_PATH."
            ),
        )

    cmd = [str(calibre_bin), str(epub_path), str(dest_path)]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            return OperationResult(
                status=OperationStatus.ERROR,
                reason=f"Calibre conversion failed (exit code {res.returncode}):\n{res.stderr or res.stdout}",
            )
    except Exception as e:
        return OperationResult(
            status=OperationStatus.ERROR, reason=f"Calibre execution failed: {e}"
        )

    return OperationResult(
        status=OperationStatus.OK,
        reason=f"Derivative {output_format.upper()} format generated successfully",
        report_paths=[str(dest_path)],
    )


def export_book(workspace_root: Path, formats: list[str]) -> OperationResult:
    """Verify QA checkpoints, compile EPUB atomically, run EPUBCheck, and convert to Calibre derivatives."""
    try:
        workspace_root = workspace_root.resolve()
        paths = workspace_paths(workspace_root.parent, workspace_root.name)

        # 1. Enforce QA Checkpoint exists and is current (EXPT-01)
        gate_res = check_gate(workspace_root, CheckpointType.QA_APPROVED)
        if gate_res.status is not OperationStatus.OK:
            return OperationResult(
                status=OperationStatus.BLOCKED,
                reason=f"Export blocked: missing or stale QA approval checkpoint. Run check-translation / approve-qa first. Detail: {gate_res.reason}",
                approval_path=gate_res.approval_path,
            )

        # 2. Load Book Metadata and Chapters Catalog
        book_metadata = load_yaml_model(paths.book, BookMetadata)
        catalog = load_yaml_model(paths.chapters, ChapterCatalog)

        # 3. Build in-memory EPUB
        epub_bytes = compile_epub_in_memory(workspace_root, book_metadata, catalog)

        # 4. Verify ZIP & EPUB mimetype invariants
        verify_epub_invariants(epub_bytes)

        # 5. Write EPUB file atomically to a temp file, then rename
        paths.exports.mkdir(parents=True, exist_ok=True)
        epub_path = paths.exports / f"{book_metadata.book_slug}.epub"

        # We write to a temporary file in the same directory for atomic replace
        temp_epub = epub_path.with_name(f".{epub_path.name}.{uuid.uuid4().hex}.tmp.epub")
        temp_epub.write_bytes(epub_bytes)

        # 6. Run EPUBCheck on the generated temporary EPUB first (so we don't save a corrupt EPUB)
        epubcheck_res = run_epubcheck(temp_epub)
        if epubcheck_res.status is OperationStatus.ERROR:
            # Delete temporary file
            try:
                temp_epub.unlink()
            except OSError:
                pass
            return epubcheck_res

        # If EPUBCheck was blocked (tool missing), we stop and fail with actionable guidance
        if epubcheck_res.status is OperationStatus.BLOCKED:
            try:
                temp_epub.unlink()
            except OSError:
                pass
            return epubcheck_res

        # Promote temporary file to canonical EPUB path
        os.replace(temp_epub, epub_path)

        saved_reports = [str(epub_path.relative_to(workspace_root).as_posix())]
        warnings = []

        # 7. Compile Calibre derivatives if requested
        for fmt in formats:
            fmt_clean = fmt.lower().strip()
            if fmt_clean == "epub":
                continue
            if fmt_clean in ("azw3", "mobi", "pdf"):
                conv_res = run_calibre_convert(epub_path, fmt_clean)
                if conv_res.status is OperationStatus.OK:
                    if conv_res.report_paths:
                        saved_reports.append(
                            str(
                                Path(conv_res.report_paths[0])
                                .relative_to(workspace_root)
                                .as_posix()
                            )
                        )
                elif conv_res.status is OperationStatus.BLOCKED:
                    warnings.append(conv_res.reason)
                else:
                    # Conversion errored out
                    return conv_res
            else:
                warnings.append(f"Skipped unsupported format: {fmt}")

        reason = "Ebook export completed successfully."
        if warnings:
            reason += " Warnings:\n" + "\n".join(warnings)

        return OperationResult(
            status=OperationStatus.OK,
            reason=reason,
            report_paths=saved_reports,
            progress=ProgressSummary(
                completed=len(catalog.chapters), total=len(catalog.chapters)
            ),
        )

    except Exception as e:
        return OperationResult(
            status=OperationStatus.ERROR, reason=f"Failed to export book: {e}"
        )
