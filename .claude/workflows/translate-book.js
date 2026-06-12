export const meta = {
  name: 'translate-book',
  description: 'Sequentially translate a compact batch of a crawl-approved novel workspace (Chinese -> Vietnamese). Spawns the locked-down translator subagent for each chapter; promotes via CLI between chapters.',
  whenToUse: 'Long-book translation runs. Defaults to a 5-chapter compact batch; rerun to resume from state.yaml until completed.',
  phases: [
    { title: 'Verify gate', detail: 'check-gate crawl-approved' },
    { title: 'Translate', detail: 'sequential per-chapter: work item -> translator -> verify -> promote' },
  ],
}

// ----- Schemas -----

const OPERATION_RESULT_SCHEMA = {
  type: 'object',
  required: ['status', 'reason', 'data'],
  properties: {
    status: { type: 'string', enum: ['ok', 'blocked', 'error'] },
    reason: { type: 'string' },
    progress: { type: ['object', 'null'] },
    data: { type: 'object' },
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

// ----- Workflow body -----

const workspace = (args && args.workspace) || 'books/<book-slug>'
const batchLimit = (args && args.max_chapters) || 5
const maxRetries = 3

let processedCount = 0
let chapterStart = null
let chapterEnd = null
let nextChapterId = null

const compactResult = (status, failureReason = null) => ({
  status,
  processed_count: processedCount,
  chapter_start: chapterStart,
  chapter_end: chapterEnd,
  next_chapter_id: nextChapterId,
  failure_reason: failureReason,
})

const runJsonCommand = async (label, command) => agent(
  `Run this Bash command exactly once and parse stdout as JSON:\n` +
  `  $env:PYTHONUTF8=1; ${command}\n\n` +
  `Return ONLY the parsed JSON object. Do not run any other commands.`,
  { label, schema: OPERATION_RESULT_SCHEMA }
)

log(`Workspace: ${workspace}`)
log(`Batch limit: ${batchLimit}`)

// Phase 1: Verify crawl gate
phase('Verify gate')
const gate = await runJsonCommand(
  'check-gate',
  `uv run python main.py check-gate --workspace ${workspace} --type crawl-approved --json`
)

if (!gate || gate.status !== 'ok') {
  return compactResult('blocked', gate ? gate.reason : 'crawl-approved gate check returned null')
}

// Phase 2: Sequential compact translation loop
phase('Translate')

while (processedCount < batchLimit) {
  const workItem = await runJsonCommand(
    `work-item ${processedCount + 1}`,
    `uv run python main.py next-translation-work-item --workspace ${workspace} --json`
  )

  if (!workItem) {
    return compactResult('error', 'next-translation-work-item returned null')
  }

  const item = workItem.data || {}
  nextChapterId = item.next_chapter_id || item.chapter_id || null

  if (item.state === 'completed') {
    nextChapterId = null
    return compactResult(processedCount === 0 ? 'completed' : 'ok')
  }
  if (item.state === 'blocked' || workItem.status === 'blocked') {
    return compactResult('blocked', item.failure_reason || workItem.reason)
  }
  if (item.state !== 'pending' || workItem.status !== 'ok') {
    return compactResult('error', item.failure_reason || workItem.reason)
  }

  const chapterId = item.chapter_id
  if (chapterStart === null) chapterStart = chapterId

  let lastError = null
  let success = false

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    const prevSection = item.prev_translation_path
      ? `4. **Previous Chapter Context:** Read \`${item.prev_translation_path}\` for pronoun (xưng hô) continuity.`
      : `4. **Previous Chapter Context:** None - this is Chapter 1 or a fallback (reason: ${item.fallback_reason || 'n/a'}). Translate without predecessor context.`

    const translatorPrompt = `You are translating chapter ${chapterId} of a Chinese xianxia novel into Vietnamese.

## Inputs (absolute paths)
1. **Raw Chinese Text:** Read \`${item.raw_path}\`
2. **Style Guidelines:** Read \`${item.style_path}\` (archaic tone)
3. **Glossary:** Read \`${item.glossary_path}\` (glossary mappings override your own rendering)
4. **Chapter Glossary Context:** Read \`${item.glossary_context_path}\`
${prevSection}

## Output paths (absolute)
- staged_txt:  \`${item.staged_txt}\`
- staged_yaml: \`${item.staged_yaml}\` (only write if there are new proposals)

## Rules (non-negotiable)
- File line 1: \`# [title_vi]\`. Line 2 blank. Line 3+ body.
- No Chinese characters in the body. No bilingual annotations in the body. Proposals go ONLY in staged_yaml.
- Use glossary_context_path exactly and never use rejected aliases from it.

## Return
Return ONLY the JSON block defined in your system prompt - either the success or the error shape. Nothing else.

Attempt ${attempt} of ${maxRetries}. chapter_id = ${chapterId}.`

    const translation = await agent(translatorPrompt, {
      label: `translate ch${chapterId} attempt ${attempt}`,
      agentType: 'translator',
      schema: TRANSLATOR_SCHEMA,
    })

    if (!translation || translation.status !== 'success') {
      lastError = translation ? translation.error_message || 'translator returned error' : 'translator returned null'
      continue
    }

    const verify = await runJsonCommand(
      `verify ch${chapterId}`,
      `uv run python main.py verify-staged-chapter --workspace ${workspace} --chapter-id ${chapterId} --json`
    )
    if (!verify || verify.status !== 'ok' || !verify.data || verify.data.ok !== true) {
      lastError = verify ? verify.reason : 'verify-staged-chapter returned null'
      continue
    }

    const promote = await runJsonCommand(
      `promote ch${chapterId}`,
      `uv run python main.py promote-chapter --workspace ${workspace} --chapter-id ${chapterId} --json`
    )
    if (!promote || promote.status !== 'ok') {
      lastError = promote ? promote.reason : 'promote-chapter returned null'
      continue
    }

    success = true
    processedCount += 1
    chapterEnd = chapterId
    break
  }

  if (!success) {
    return compactResult('error', `chapter ${chapterId} failed after ${maxRetries} attempts: ${lastError}`)
  }
}

const nextItem = await runJsonCommand(
  'next-work-item-after-batch',
  `uv run python main.py next-translation-work-item --workspace ${workspace} --json`
)
if (nextItem && nextItem.data) {
  nextChapterId = nextItem.data.next_chapter_id || nextItem.data.chapter_id || null
}

return compactResult('ok')
