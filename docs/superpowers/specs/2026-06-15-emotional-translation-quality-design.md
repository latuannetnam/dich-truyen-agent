# Emotional, Human-Like Translation Quality — Design

- **Date:** 2026-06-15
- **Status:** Approved (design); pending implementation plan
- **Approach:** B — Genre-aware style profiles + universal emotional craft
- **Scope:** System-wide, future translations only

## Problem

Translation output reads as machine-like. From review of `books/mo-ri-zhang-lang`
(a modern apocalypse / zombie-survival novel, "Doomsday Cockroach"):

1. **Flat emotion** — characters' fear, panic, sarcasm, tenderness do not come
   through; prose reads like a report, not a felt scene.
2. **Monotone rhythm** — uniform sentence length and cadence; action scenes read
   as slowly as quiet ones.

Two root causes:

- The translator subagent prompt
  (`.harness/source/agents/translator.md`) optimizes only for
  "professional, elegant, archaic" correctness. It contains **no** guidance on
  emotional fidelity, prose rhythm, or character voice.
- The style system has a single template (`templates/styles/tien_hiep.yaml`) and
  `styles.py` hardcodes it as the default for every book. So a modern apocalypse
  novel is translated in archaic xianxia register — characters say
  `"tại hạ xin cáo từ"` and `"thiên linh cái"` mid zombie-chase. Tonal mismatch.

A secondary defect: the prompt's "Lexical Sandbox Rule" (Step 5) forces
diacritic-stripped ASCII replacements, producing lines such as
`"Ngoi... la... ngoi... phuong... nao...?"` — wrong for literary Vietnamese.

## Goals

- Make future translations emotionally faithful and naturally paced, across all
  books and genres.
- Apply the correct tonal register per book genre.
- Preserve the existing compact orchestration contract, translator isolation,
  sequential ordering, and glossary gates.

## Non-Goals (YAGNI)

- Re-translating already-completed books (future-only).
- A second "literary editor" refine pass (Approach C — rejected: doubles
  per-chapter cost/context and breaks the single-subagent-per-chapter contract).
- Automated emotion scoring / quality metrics.

## Core Idea — Two Layers

Separate **craft** from **register**:

- **Craft** (universal, every book): *how* to convey emotion and rhythm. Lives
  in the translator prompt so it applies to all genres.
- **Register** (per-genre, per-book): the tonal "dialect" — archaic xianxia vs.
  modern apocalypse. Lives in `style.yaml` and the genre templates.

The zombie book was both flat (missing craft) and wrong-toned (wrong register).
Each is fixed in its proper layer.

## Design

### 1. Translator prompt rewrite — `.harness/source/agents/translator.md`

Add a craft section and rework Steps 4–5:

- **Emotional fidelity:** translate the character's *felt experience* (fear,
  panic, sarcasm, tenderness); choose verbs/adjectives that carry the emotional
  charge instead of literal word-mapping.
- **Prose rhythm:** vary sentence length and cadence to match pacing — short,
  clipped sentences in action; longer flowing sentences in reflection/scenery.
  Explicitly avoid uniform cadence.
- **Natural dialogue voice:** render speech as a Vietnamese speaker actually
  would; give characters distinct voices; handle stutter / banter / bluster /
  hesitation with natural Vietnamese devices.
- **Show, don't report:** prefer concrete, embodied, sensory phrasing over flat
  narration.
- **Replace the "Lexical Sandbox Rule" (Step 5):** drop the ASCII replacement
  table. New rule: "No leaked English helper words; replace any with correct,
  fully-accented Vietnamese." Intentional slurred/broken speech becomes a
  deliberate authorial choice, not a diacritic-stripping byproduct.
- **Generalize register:** change "Maintain the archaic tone defined in
  style.yaml" to "Maintain the **register** and apply the craft fields
  (`emotion_guidelines`, `voice_guidelines`, `rhythm_guidelines`) defined in
  style.yaml."
- **Self-review (Step 9):** extend the checklist to confirm emotional/rhythm
  craft was applied and that all Vietnamese is fully accented.

**Unchanged:** single-chapter scope, JSON return schema, tool allowlist
(Read/Write/Glob/Grep), no external LLM calls, absolute paths, sequential `N-1`
continuity, no Chinese residue, glossary/rejected-alias rules.

### 2. Enriched style schema — `src/dich_truyen_agent/models.py` (`TranslationStyle`)

Add optional, backward-compatible fields (default empty so existing styles and
workspace snapshots still load):

- `register: str = ""` — e.g. `archaic-formal`, `modern-colloquial`.
- `emotion_guidelines: list[str] = []`
- `voice_guidelines: list[str] = []`
- `rhythm_guidelines: list[str] = []`

Existing fields (`name`, `description`, `guidelines`, `vocabulary`, `tone`,
`examples`) are retained unchanged.

### 3. Genre profile library — `templates/styles/`

Provide profiles, each carrying register + craft fields + genre vocabulary:

- `tien_hiep.yaml` — enrich existing with craft fields; keep archaic register.
- `mat_the.yaml` — modern apocalypse / survival register (what
  `mo-ri-zhang-lang` needs).
- `do_thi.yaml` — modern urban register.
- `general.yaml` — neutral fallback register.

### 4. init-book genre recommendation — `styles.py`, `cli.py`, harness init guide

- `load_selected_style` resolves `--style` as **either** a known profile name
  (`templates/styles/<name>.yaml`) **or** an explicit path. Backward compatible
  with the existing path-based `--style`.
- The default changes from hardcoded `tien_hiep` to `general`, so no book
  silently receives archaic styling.
- Init flow (agent-driven, all harnesses): the agent infers genre from the book
  title / source metadata, **recommends** a profile, the user confirms or
  overrides, then `init-book --style <genre>` runs. Documented in
  `.harness/source` so behavior is shared across harnesses.

### 5. Harness adapter regeneration

Because `.harness/source/**` changes (translator prompt + init guide), regenerate
and verify adapters:

```powershell
$env:PYTHONUTF8=1
uv run python tools/sync_harness_adapters.py
uv run python tools/sync_harness_adapters.py --check
```

## Testing

- **Unit:** `TranslationStyle` loads with and without the new fields (backward
  compat); each new template passes `validate-style`; `load_selected_style`
  resolves profile names, explicit paths, and the new `general` default.
- **Adapter sync:** `sync_harness_adapters.py --check` reports no drift.
- **Suite:** `uv run pytest -q` and `uv run ruff check tools tests src main.py`
  pass.
- **Acceptance (manual, not automated):** re-translate 1–2 `mo-ri-zhang-lang`
  chapters into a scratch workspace using the `mat_the` profile and compare
  before/after for emotion and rhythm.

## Risks

- Prompt changes are non-deterministic; translation quality is judged
  subjectively rather than by automated assertion.
- Changing the default style from `tien_hiep` to `general` alters implicit
  behavior for callers that relied on the old default. Mitigated by the
  agent-recommend-and-confirm init step and by documenting the change.

## Affected Files (anticipated)

- `.harness/source/agents/translator.md` — craft rewrite.
- `.harness/source/guides/**` — init genre-recommendation guidance.
- `src/dich_truyen_agent/models.py` — `TranslationStyle` fields.
- `src/dich_truyen_agent/styles.py` — profile-name resolution + default.
- `templates/styles/*.yaml` — enriched + new genre profiles.
- Generated adapters under `.claude/`, `.agent/`, `.opencode/`, `.codex/`
  (via sync tool, not hand-edited).
- `tests/**` — schema, template validity, style resolution.
