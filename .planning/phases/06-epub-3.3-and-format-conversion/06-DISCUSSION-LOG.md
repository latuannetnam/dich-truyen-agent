# Phase 6: EPUB 3.3 and Format Conversion - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-01
**Phase:** 6-EPUB 3.3 and Format Conversion
**Areas discussed:** EPUB 3.3 packaging assembly, EPUBCheck integration, Calibre ebook-convert integration, CSS styling for Vietnamese novels

---

## EPUB 3.3 Packaging and Directory Layout

| Option | Description | Selected |
|--------|-------------|----------|
| **Option A** | Build in-memory first using `zipfile`, perform Python-level structure validation, then write atomically to `exports/book-title.epub` | ✓ |
| **Option B** | Assemble files in a temporary staging directory (e.g. `exports/.epub_staging/`) first, and then zip the folder | |
| **Option C** | Directly compile and write files to the `zipfile` on-the-fly without in-memory buffering or disk staging | |

**User's choice:** Option A.
**Notes:** Prevents corrupt or half-written files on disk, ensuring atomic writes and robust internal Python validation of zip invariants before committing the file to the final location.

---

## EPUBCheck 5.3.0 Integration

| Option | Description | Selected |
|--------|-------------|----------|
| **Option A** | Look for `epubcheck` in PATH, and fallback to `DICH_TRUYEN_EPUBCHECK_PATH` env var. If missing, fail export with detailed instructions to download and configure it. | ✓ |
| **Option B** | Only look for `DICH_TRUYEN_EPUBCHECK_PATH` environment variable. Fail immediately if it is unset. | |

**User's choice:** Option A.
**Notes:** Provides maximum user convenience by supporting global PATH binary/scripts while ensuring a clear path to fallback configuration and rigorous failure guidance as required.

---

## Calibre 'ebook-convert' Integration

| Option | Description | Selected |
|--------|-------------|----------|
| **Option A** | Look for `ebook-convert` in PATH and fallback paths (e.g. `C:\Program Files\Calibre2\` on Windows). If missing, skip AZW3/MOBI/PDF derivatives with a warning, but successfully export the canonical EPUB. | ✓ |
| **Option B** | Strictly enforce Calibre presence. If `ebook-convert` is missing, fail the entire export process. | |
| **Option C** | Accept a `--formats` flag. Only fail or warn if a requested derivative format (e.g. `mobi`) is explicitly selected but `ebook-convert` is missing. | |

**User's choice:** Option A.
**Notes:** Recognizes EPUB as the canonical, mandatory product of Phase 6. Since Calibre conversions are derivatives, missing Calibre warns the user but does not disrupt canonical EPUB delivery.

---

## CSS Styling for Vietnamese Novels

| Option | Description | Selected |
|--------|-------------|----------|
| **Option A** | Include a standard, beautiful, and clean CSS stylesheet (margins, line-height 1.6, nice serif fonts, elegant title styling) as a default template, and support custom book-level stylesheets. | ✓ |
| **Option B** | Generate a completely unstyled EPUB and rely entirely on the e-reader's default styling rules. | |

**User's choice:** Option A.
**Notes:** Delivers a premium, stunning aesthetic right out of the box with tailored spacing and line heights optimal for Vietnamese reading, while keeping custom extensions possible.

---

*Phase: 6-epub-3.3-and-format-conversion*
*Context gathered: 2026-06-01*
