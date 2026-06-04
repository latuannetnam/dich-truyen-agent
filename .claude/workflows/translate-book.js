export const meta = {
  name: 'translate-book',
  description: 'Sequentially translate all pending chapters of a crawl-approved novel workspace (Chinese -> Vietnamese). Spawns the locked-down translator subagent for each chapter; promotes via CLI between chapters.',
  whenToUse: 'Long unattended translation runs (10+ chapters). For 1-5 chapters or troubleshooting, use the translate-book skill manually instead.',
  phases: [
    { title: 'Verify gate', detail: 'check-gate crawl-approved' },
    { title: 'Translate', detail: 'sequential per-chapter: progress -> context -> translator -> verify -> promote' },
  ],
}

// ----- Schemas -----

const PROGRESS_SCHEMA = {
  type: 'object',
  required: ['state'],
  properties: {
    state: { type: 'string', enum: ['pending', 'completed', 'blocked'] },
    chapter_id: { type: ['integer', 'null'] },
    slug: { type: ['string', 'null'] },
    original_title: { type: ['string', 'null'] },
    blocked_reason: { type: ['string', 'null'] },
    message: { type: ['string', 'null'] },
  },
}

const CONTEXT_SCHEMA = {
  type: 'object',
  required: ['raw_path', 'style_path', 'glossary_path', 'staged_txt', 'staged_yaml', 'is_fallback'],
  properties: {
    raw_path: { type: 'string' },
    style_path: { type: 'string' },
    glossary_path: { type: 'string' },
    prev_translation_path: { type: ['string', 'null'] },
    staged_txt: { type: 'string' },
    staged_yaml: { type: 'string' },
    is_fallback: { type: 'boolean' },
    fallback_reason: { type: ['string', 'null'] },
  },
}

const TRANSLATOR_SCHEMA = {
  type: 'object',
  required: ['status', 'chapter_id'],
  properties: {
    status: { type: 'string', enum: ['success', 'error'] },
    chapter_id: { type: 'integer' },
    title_vi: { type: ['string', 'null'] },
    character_count: { type: ['integer', 'null'] },
    proposals_count: { type: ['integer', 'null'] },
    error_message: { type: ['string', 'null'] },
  },
}

const VERIFY_SCHEMA = {
  type: 'object',
  required: ['ok'],
  properties: {
    ok: { type: 'boolean' },
    first_line: { type: ['string', 'null'] },
    reason: { type: ['string', 'null'] },
  },
}

const PROMOTE_SCHEMA = {
  type: 'object',
  required: ['ok'],
  properties: {
    ok: { type: 'boolean' },
    reason: { type: ['string', 'null'] },
  },
}

// ----- Workflow body -----

const workspace = (args && args.workspace) || 'books/<book-slug>'
const maxChapters = (args && args.max_chapters) || 0  // 0 = unlimited (loop until completed/blocked)
const maxRetries = 3

log(`Workspace: ${workspace}`)
log(`Max chapters this run: ${maxChapters === 0 ? 'unlimited' : maxChapters}`)

// Phase 1: Verify crawl gate
phase('Verify gate')
const gate = await agent(
  `Run this Bash command exactly once and return JSON:\n` +
  `  $env:PYTHONUTF8=1; uv run python main.py check-gate --workspace ${workspace} --type crawl-approved\n\n` +
  `Return ONLY this JSON:\n` +
  `{"ok": <true if exit 0 and stdout indicates valid gate, else false>, "reason": "<one sentence>"}\n` +
  `Do not run any other commands.`,
  { label: 'check-gate', schema: { type: 'object', required: ['ok'], properties: { ok: { type: 'boolean' }, reason: { type: ['string', 'null'] } } } }
)

if (!gate || !gate.ok) {
  log(`Gate check failed: ${gate ? gate.reason : 'null'}`)
  return { status: 'halted', reason: 'crawl-approved gate missing or invalid', detail: gate }
}

// Phase 2: Sequential translation loop
phase('Translate')

const promoted = []
let chaptersThisRun = 0

while (true) {
  if (maxChapters > 0 && chaptersThisRun >= maxChapters) {
    log(`Reached max_chapters=${maxChapters}, stopping.`)
    break
  }

  // Query next pending chapter
  const progress = await agent(
    `Run this Bash command and parse its stdout JSON to extract the next pending chapter:\n` +
    `  $env:PYTHONUTF8=1; uv run python main.py show-translation-progress --workspace ${workspace}\n\n` +
    `The command returns JSON in its 'reason' field with keys like state/chapter_id/slug/original_title. Return ONLY this JSON shape:\n` +
    `{"state": "pending"|"completed"|"blocked", "chapter_id": <int or null>, "slug": <string or null>, "original_title": <string or null>, "blocked_reason": <string or null>, "message": <string or null>}\n` +
    `Do not run any other commands.`,
    { label: `progress (${chaptersThisRun + 1})`, schema: PROGRESS_SCHEMA }
  )

  if (!progress) {
    log('progress query returned null — halting')
    return { status: 'halted', reason: 'show-translation-progress failed', promoted }
  }
  if (progress.state === 'completed') {
    log('All chapter translations completed.')
    break
  }
  if (progress.state === 'blocked') {
    log(`Blocked: ${progress.blocked_reason || progress.message}`)
    return { status: 'halted', reason: `progress blocked: ${progress.blocked_reason || progress.message}`, promoted }
  }

  const chapterId = progress.chapter_id
  log(`Chapter ${chapterId}: ${progress.original_title || progress.slug}`)

  // Prepare context
  const context = await agent(
    `Run this Bash command and parse stdout JSON to extract translation context for chapter ${chapterId}:\n` +
    `  $env:PYTHONUTF8=1; uv run python main.py prepare-translation-context --workspace ${workspace} --chapter-id ${chapterId}\n\n` +
    `Then resolve all paths to absolute (using PowerShell Resolve-Path or Python pathlib). Compute:\n` +
    `  staged_txt  = <absolute workspace>/staging/chuong-${String(chapterId).padStart(4, '0')}-staged.txt\n` +
    `  staged_yaml = <absolute workspace>/staging/chuong-${String(chapterId).padStart(4, '0')}-proposals.yaml\n\n` +
    `Return ONLY this JSON shape with absolute paths (use forward slashes or Windows backslashes; both are fine):\n` +
    `{"raw_path": "...", "style_path": "...", "glossary_path": "...", "prev_translation_path": "..."|null, "staged_txt": "...", "staged_yaml": "...", "is_fallback": <bool>, "fallback_reason": <string or null>}\n` +
    `Do not read the raw or staging files. Do not run any other commands.`,
    { label: `context ch${chapterId}`, schema: CONTEXT_SCHEMA }
  )

  if (!context) {
    log(`Context prep failed for chapter ${chapterId} — halting`)
    return { status: 'halted', reason: `prepare-translation-context failed for ch ${chapterId}`, promoted }
  }

  // Translate with retries
  let lastError = null
  let success = false

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    const prevSection = context.prev_translation_path
      ? `4. **Previous Chapter Context:** Read \`${context.prev_translation_path}\` for pronoun (xưng hô) continuity.`
      : `4. **Previous Chapter Context:** None — this is Chapter 1 or a fallback (reason: ${context.fallback_reason || 'n/a'}). Translate without predecessor context.`

    const translatorPrompt = `You are translating chapter ${chapterId} of a Chinese xianxia novel into Vietnamese.

## Inputs (absolute paths)
1. **Raw Chinese Text:** Read \`${context.raw_path}\`
2. **Style Guidelines:** Read \`${context.style_path}\` (archaic tone)
3. **Glossary:** Read \`${context.glossary_path}\` (glossary mappings override your own rendering)
${prevSection}

## Output paths (absolute)
- staged_txt:  \`${context.staged_txt}\`
- staged_yaml: \`${context.staged_yaml}\` (only write if there are new proposals)

## Rules (these are non-negotiable)
- Title: \`第[N]章\` -> \`Chương [N]\`; body in Sino-Vietnamese Title Case; single space joiner; no colon/hyphen/brackets.
- File line 1: \`# [title_vi]\`. Line 2 blank. Line 3+ body.
- Lexical Sandbox: scan and replace banned English helper words (but/and/or/the/while/before/after/of/to/in/on/at/for/with/here/now/okay) per the table in your system prompt.
- No Chinese characters in the body. No bilingual annotations in the body. Proposals go ONLY in staged_yaml.

## Return
Return ONLY the JSON block defined in your system prompt — either the success or the error shape. Nothing else.

Attempt ${attempt} of ${maxRetries}. chapter_id = ${chapterId}.`

    const result = await agent(translatorPrompt, {
      label: `translate ch${chapterId} (attempt ${attempt})`,
      agentType: 'translator',
      schema: TRANSLATOR_SCHEMA,
    })

    if (!result) {
      lastError = `attempt ${attempt}: translator returned null`
      log(lastError)
      continue
    }
    if (result.status !== 'success') {
      lastError = `attempt ${attempt}: ${result.error_message || 'translator returned error status'}`
      log(lastError)
      continue
    }

    // Verify staging file (lightweight, first 3 lines only)
    const verify = await agent(
      `Use the Read tool to read ONLY the first 3 lines of:\n  ${context.staged_txt}\n\n` +
      `Confirm:\n` +
      `  - Line 1 starts with \`# Chương ${chapterId}\` (the chapter number must match exactly)\n` +
      `  - Line 2 is blank\n` +
      `  - File is non-empty\n\n` +
      `Return ONLY: {"ok": <bool>, "first_line": "<line 1 content>", "reason": "<one sentence if not ok, else null>"}\n` +
      `Do not read more than 3 lines. Do not run Bash.`,
      { label: `verify ch${chapterId}`, schema: VERIFY_SCHEMA }
    )

    if (!verify || !verify.ok) {
      lastError = `attempt ${attempt}: staging verify failed (${verify ? verify.reason : 'null'}; first_line=${verify ? verify.first_line : 'n/a'})`
      log(lastError)
      continue
    }

    // Promote
    const promote = await agent(
      `Run this Bash command and report whether it succeeded:\n` +
      `  $env:PYTHONUTF8=1; uv run python main.py promote-chapter --workspace ${workspace} --chapter-id ${chapterId}\n\n` +
      `Return ONLY: {"ok": <true if exit 0 and stdout shows status ok, else false>, "reason": "<one sentence if not ok, else null>"}\n` +
      `Do not run any other commands.`,
      { label: `promote ch${chapterId}`, schema: PROMOTE_SCHEMA }
    )

    if (!promote || !promote.ok) {
      lastError = `attempt ${attempt}: promote-chapter failed (${promote ? promote.reason : 'null'})`
      log(lastError)
      continue
    }

    success = true
    promoted.push({
      chapter_id: chapterId,
      title_vi: result.title_vi,
      character_count: result.character_count,
      proposals_count: result.proposals_count,
      attempts: attempt,
    })
    log(`Promoted ch ${chapterId} (${result.character_count} chars, ${result.proposals_count} proposals) on attempt ${attempt}`)
    break
  }

  if (!success) {
    log(`Chapter ${chapterId} exhausted ${maxRetries} retries: ${lastError}`)
    return {
      status: 'halted',
      reason: `chapter ${chapterId} failed after ${maxRetries} retries`,
      last_error: lastError,
      promoted,
    }
  }

  chaptersThisRun++
}

return { status: 'ok', promoted_count: promoted.length, promoted }
