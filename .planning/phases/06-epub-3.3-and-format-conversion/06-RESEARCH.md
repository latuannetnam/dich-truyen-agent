# Phase 6: EPUB 3.3 and Format Conversion - Research

**Researched:** 2026-06-01
**Domain:** EPUB 3.3 packaging, zipfile zipfile/mimetype invariants, EPUBCheck CLI verification, Calibre ebook-convert process runners, separate Antigravity skill triggers.
**Confidence:** HIGH

## Summary

Phase 6 delivers the final step in the Dich Truyen Agent workflow: converting approved Vietnamese translations into a perfectly conformant EPUB 3.3 ebook and deriving optional AZW3, MOBI, and PDF formats through Calibre `ebook-convert`. The export process enforces a rigid gated validation: it requires the presence of a valid `qa-approved` checkpoint, compile-time EPUB structure validation in Python, mandatory external EPUBCheck conformance testing, and robust process wrapper execution for Calibre.

---

## Recommended Architecture

### 1. In-Memory EPUB Assembly and ZIP Invariants (EXPT-02, EXPT-03)

To assemble a conformant EPUB 3.3 from scratch using python's `zipfile` standard library:
- **In-Memory Writing:** We will use `io.BytesIO` to compile the ZIP structure completely in memory first. This prevents half-written or corrupt files on disk.
- **Strict Invariant Validation:**
  - **Mimetype:** The first entry in the ZIP MUST be named `mimetype`, must contain exactly `application/epub+zip` (no trailing newlines or spaces), and MUST be added with `zipfile.ZIP_STORED` (uncompressed).
  - **Other Files:** All subsequent entries (e.g. `META-INF/container.xml`, OPF, XHTML chapters, stylesheets) will be added with `zipfile.ZIP_DEFLATED` (compressed).
- **Structure Verification:**
  - Verify that `META-INF/container.xml` exists.
  - Parse the container XML to locate the package OPF file.
  - Parse the package OPF to verify all files in the `<manifest>` are correctly packed in the ZIP.

### 2. EPUB 3.3 File Contracts & Layout
The generated EPUB will have the following internal file structure:
- `mimetype`: `application/epub+zip`
- `META-INF/container.xml`: Points to `EPUB/package.opf`
- `EPUB/package.opf`: Defines metadata (title, author, book slug, language `vi`, random but persisted/deterministic UUID, modified date), manifest (item list), and spine (reading order).
- `EPUB/nav.xhtml`: XHTML 5 navigation document (table of contents).
- `EPUB/style.css`: Clean, elegant CSS typography for Vietnamese translation reading.
- `EPUB/chapter_<id>.xhtml`: XHTML 5 document containing chapter heading and paragraphs.

### 3. EPUBCheck 5.3.0 Integration (EXPT-04)

EPUBCheck is a Java application. We will invoke it through a Python subprocess runner:
- **Detection Logic:**
  - Look for `epubcheck` command or executable in the system `PATH`.
  - Fall back to the `DICH_TRUYEN_EPUBCHECK_PATH` environment variable or setting. This can point to an executable, script, or directly to `epubcheck.jar` (in which case we invoke it as `java -jar <path_to_jar>`).
- **Missing Tool Handler:**
  - If EPUBCheck is not found, or `java` is missing when executing a jar, fail the export with an extremely clean, detailed instruction:
    * "EPUBCheck 5.3.0 or Java is missing. Please download EPUBCheck from https://github.com/w3c/epubcheck/releases and ensure Java is installed. Set your environment variable DICH_TRUYEN_EPUBCHECK_PATH to the downloaded epubcheck.jar or executable, and run again."
- **Execution:**
  - Run EPUBCheck in a sandbox-safe subprocess.
  - Parse exit code and output. If EPUBCheck returns non-zero, fail the build and print the errors.

### 4. Calibre `ebook-convert` Process Runner (EXPT-05)

- **Detection Logic:**
  - Look for `ebook-convert` or `ebook-convert.exe` in system `PATH`.
  - Check typical installation fallback paths:
    * Windows: `C:\Program Files\Calibre2\ebook-convert.exe` and `C:\Program Files (x86)\Calibre2\ebook-convert.exe`
    * macOS / Linux: `/Applications/calibre.app/Contents/MacOS/ebook-convert` or `/usr/bin/ebook-convert`.
  - Fall back to `DICH_TRUYEN_CALIBRE_PATH` env var.
- **Conversion Execution:**
  - For each selected format (AZW3, MOBI, PDF), run `ebook-convert <epub_path> <output_path>`.
  - If Calibre is missing, print a warning to the console, skipping derivatives but successfully saving the canonical EPUB.

### 5. CLI Integration & Gating (EXPT-01, SKIL-01)

- **Command:** `main.py export-book --workspace <path> [--formats epub,azw3,mobi,pdf]`
  - Runs `check_gate(workspace, CheckpointType.QA_APPROVED)` first. If blocked, fail with "QA approval checkpoint is missing. Run main.py approve-qa first."
  - Default `--formats` is `epub`.
  - Compiles the EPUB.
  - Runs EPUBCheck. If it passes, writes EPUB to `exports/<slug>.epub`.
  - Runs Calibre for any requested derivative formats.
  - Persists the execution metadata to `reports/results/export-book.yaml`.

---

## Validation Architecture

We will implement isolated unit and integration tests under `tests/test_export.py` to verify:

| Requirement | Automated Coverage |
|-------------|--------------------|
| **EXPT-01** | Verify export is completely blocked when `qa-approved` checkpoint is missing or stale. |
| **EXPT-02 / EXPT-03** | Verify standard EPUB 3.3 assembly and Python-side ZIP/mimetype invariant validations. |
| **EXPT-04** | Verify EPUBCheck wrapper: test correct executable / jar discovery, execution parsing, and the detailed error messages when the tool is missing. |
| **EXPT-05** | Verify Calibre conversion wrapper: test fallback search paths, mock execution of `ebook-convert`, and verification that missing Calibre produces warnings without failing canonical EPUB. |

---

## Security & STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-01 | Tampering | Checkpoint validation | Mitigate | Enforce exact evidence hash verification of all chapters under `translations/` to guarantee that exported content matches what passed QA. |
| T-06-02 | Command Injection | Subprocess process wrappers | Mitigate | Never use `shell=True` in `subprocess.Popen` or `subprocess.run`. Pass command arguments as parsed list tokens. |
| T-06-03 | Path Traversal | EPUB assembly path routing | Mitigate | Enforce that all filenames and path mappings in the OPF are strictly workspace-relative and stay inside the ZIP container. |

---

*Phase: 06-epub-3.3-and-format-conversion*
*Research complete: 2026-06-01*
