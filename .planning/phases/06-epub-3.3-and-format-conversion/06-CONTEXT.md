# Phase 6: EPUB 3.3 and Format Conversion - Context

**Gathered:** 2026-06-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Export QA-approved Vietnamese translations into a fully conformant canonical EPUB 3.3 ebook and derive other digital formats (AZW3, MOBI, PDF) through Calibre conversion tools. Enforce strict gated validations at each stage of compilation, ensuring that only verified, stable chapters are exported.

* **In Scope:**
  - Create the CLI export engine (`$export-book` skill and helper scripts).
  - Enforce `qa-approved` checkpoint validation before reading translations.
  - Compile a conformant EPUB 3.3 ebook directly from translations in memory using Python's standard `zipfile` library.
  - Implement strict compile-time validation of EPUB structure and ZIP invariants (e.g. mimetype as first uncompressed entry).
  - Bundle a clean, high-aesthetic CSS stylesheet optimized for Vietnamese e-reading, with support for custom stylesheets.
  - Integrate external EPUBCheck 5.3.0 command line verification to ensure complete w3c ebook conformance.
  - Integrate Calibre `ebook-convert` process wrappers to export AZW3, MOBI, and PDF formats.
  - Gracefully handle missing third-party tools (EPUBCheck and Calibre) with highly descriptive, actionable installation/configuration instructions.
* **Out of Scope:**
  - Automatic corrections of translation text during export (Phase 5 QA gate handles quality checks; export is non-mutating).
  - Direct translation of chapters (Phase 4).
  - Web UI or REST API export endpoints (v1 is operated strictly via project-local skills).

</domain>

<decisions>
## Implementation Decisions

### D-01: Gated QA Checkpoint Validation
- The export script will refuse to run if `checkpoints/qa-approved.yaml` does not exist or its evidence hashes for the translated chapters are stale or mismatch current files.
- Ensures only verified translation work is compiled into the final product.

### D-02: Atomic In-Memory EPUB 3.3 Compilation
- Construct the EPUB completely in-memory using `io.BytesIO` and Python's `zipfile` library.
- **ZIP Invariants Enforcement:**
  - The first entry written MUST be named `mimetype`, added with `zipfile.ZIP_STORED` (uncompressed), and contain exactly the string `application/epub+zip` (no spaces/newlines).
  - All subsequent entries (`META-INF/container.xml`, `EPUB/package.opf`, stylesheet, XHTML chapters) will be compressed using `zipfile.ZIP_DEFLATED`.
- Parse and validate the finished ZIP buffer structure in Python to guarantee container and manifest consistency before writing the file atomically to `exports/<slug>.epub`.

### D-03: EPUB 3.3 Layout & Standards Conformance
- **XHTML 5 Documents:** Produce clean XHTML 5 documents for the table of contents (`nav.xhtml`) and each chapter (`chapter_<id>.xhtml`). All documents must include correct XML namespaces, valid HTML5 structure, and character encoding set to `UTF-8`.
- **Package Document (`package.opf`):** Generate a valid OPF defining metadata (deterministic book identifier/UUID generated from book slug, title, author, language `vi`), a complete manifest of all bundled resources, and a reading spine in sequential order.

### D-04: Default Stylesheet and Customization
- Bundle a standard, highly polished, and modern CSS stylesheet (`EPUB/style.css`) by default.
- Typography is optimized for Vietnamese novel reading:
  - Margins: standard margins for pleasant padding on e-readers.
  - Line height: set to `1.6` for clean spacing.
  - Font fallback: serif / Georgia.
  - Headers: elegant, centered chapter title styling with margin separation.
- Support custom stylesheets by checking for a book-local custom stylesheet file in the style template folders or active style configurations.

### D-05: Subprocess EPUBCheck Verification
- Locate `epubcheck` in system `PATH` and fall back to the environment variable `DICH_TRUYEN_EPUBCHECK_PATH` (accepting a jar or binary path).
- Execute EPUBCheck as a subprocess without `shell=True` to prevent command injection.
- If EPUBCheck is missing, fail the export with a clean, detailed error guide explaining how to download it and configure the path.
- If EPUBCheck fails with validation errors, print the errors and abort the export before saving the final ebook.

### D-06: Calibre `ebook-convert` Derivative Format Runner
- Locate Calibre's `ebook-convert` utility in system `PATH`, Windows default installations (`Program Files/Calibre2/ebook-convert.exe`), or macOS/Linux standard locations.
- Support `DICH_TRUYEN_CALIBRE_PATH` env var override.
- Derivative generation is optional: if Calibre is missing, log a clear warning, skip AZW3/MOBI/PDF conversion, and successfully complete canonical EPUB generation.

### D-07: Separate `$export-book` Skill
- Add the `export-book` subcommand in `src/dich_truyen_agent/cli.py`.
- Wire up the `$export-book` skill under `.agent/skills/export-book/SKILL.md` to trigger the Python CLI subcommand.

</decisions>

<canonical_refs>
## Canonical References

- `.planning/PROJECT.md` - Overall system constraints and stack definitions.
- `.planning/REQUIREMENTS.md` - Export requirements `EXPT-01` through `EXPT-05` and skill requirement `SKIL-01`.
- `.planning/ROADMAP.md` - Roadmap details for Phase 6.
- `src/dich_truyen_agent/checkpoints.py` - Check gate and validation routines.
- `src/dich_truyen_agent/cli.py` - CLI commands parser and runner.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `check_gate()` in `src/dich_truyen_agent/checkpoints.py` for validating checkpoints.
- `workspace_paths()` in `src/dich_truyen_agent/paths.py` for locating folders.
- `load_yaml_model()` and `atomic_write_yaml()` in `src/dich_truyen_agent/storage.py` for model storage.

### Integration Points
- Add `src/dich_truyen_agent/export.py` containing the core EPUB compiler, EPUBCheck, and Calibre process wrappers.
- Update `src/dich_truyen_agent/cli.py` to register the `export-book` command.
- Update `.agent/skills/export-book/SKILL.md` to describe the finished skill usage.

</code_context>

<specifics>
## Specific Ideas

- **Deterministic UUIDs:** Use a namespace UUID (e.g. `uuid.uuid5(uuid.NAMESPACE_URL, book_metadata.source_url)`) to ensure that identical metadata always yields a stable, deterministic ebook package identifier across repeated builds.
- **Sandbox-Safe subprocesses:** Always pass list of strings to `subprocess.run` to guarantee Windows console and sandbox compatibility.

</specifics>

<deferred>
## Deferred Ideas

- None for Phase 6 (Phase 6 completes all remaining v1 roadmap features).

</deferred>

---

*Phase: 6-epub-3.3-and-format-conversion*
*Context gathered: 2026-06-01*
