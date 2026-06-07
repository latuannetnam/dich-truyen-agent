# Feature Research

**Domain:** Antigravity-first agent-native Chinese-to-Vietnamese novel translation workflow
**Researched:** 2026-05-31
**Confidence:** HIGH

## Feature Landscape

The functional baseline comes from the old `dich-truyen-tien-hiep` repository and the
user's v1 scope decisions. The new product deliberately keeps the valuable book-processing
behaviors while removing UI/API scope and direct LLM-client translation.

### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Project-local Antigravity skills | Skills are the v1 user interface | MEDIUM | Separate crawl, translate, QA, and export entry points. |
| New-book workspace initialization | Every downstream step needs stable paths and schemas | MEDIUM | Do not inherit the old mutable monolithic schema. |
| Resumable per-chapter state | Novel translation runs are long and interruption is normal | MEDIUM | Persist after every crawl and translation promotion. |
| HTTP crawl with browser fallback | Static and JavaScript-rendered sites both occur | HIGH | Stop on CAPTCHA or login requirements. |
| Crawl validation and raw-review checkpoint | Bad selectors silently poison every later phase | HIGH | Produce chapter count, sampled titles, sampled content lengths, and warnings. |
| Reusable domain profile with per-book override | Extraction logic should be reusable but safely isolated | MEDIUM | Override only after domain-profile validation fails. |
| YAML styles with default `tien_hiep` | Literary tone and naming policy must be explicit | LOW | Validate schema before translation. |
| Initial glossary generation | Names, places, realms, and techniques need consistency from chapter 1 | MEDIUM | Build automatically from sampled raw chapters after crawl approval. |
| Strictly sequential chapter translation | Chapter `N` needs the completed Vietnamese context of chapter `N-1` | HIGH | One isolated worker per chapter; no adjacent concurrency in v1. |
| Retry, stop, and resume | Failed translation must not weaken later context | MEDIUM | Retry with configurable backoff, then stop at first exhausted chapter. |
| Deterministic QA report | User needs a quality checkpoint before export | MEDIUM | Report missing files, empty output, Chinese leftovers, glossary drift, and formatting problems. |
| EPUB 3.3 export and Calibre conversion | Ebook output is the final deliverable | MEDIUM | Canonical EPUB first, optional AZW3/MOBI/PDF conversion. |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Agent-assisted crawl repair | New domains can be supported without hard-coding every site in advance | HIGH | Agent edits a profile or per-book override, then helper validation decides whether it is accepted. |
| Context-isolated translation worker protocol | Long raw chapters do not flood the orchestrator context | HIGH | Worker reads paths, writes staged output, and returns compact structured metadata. |
| Progressive glossary merge after every chapter | Newly introduced names and terms affect the next chapter immediately | MEDIUM | Worker proposes; helper validates, deduplicates, and merges. |
| Audit-first filesystem contract | Every expensive action is inspectable and recoverable | MEDIUM | Keep staged output, reports, checkpoints, and atomic state updates. |
| Portable agent contract | Later Antigravity or Claude Code adapters can reuse the same helper layer | MEDIUM | Keep runtime-specific orchestration in skill adapters, not Python contracts. |

### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Adjacent-chapter translation concurrency | Faster throughput | Loses the previous translated chapter as a reliable continuity anchor | Strict sequential translation in v1 |
| Fully autonomous crawl-to-export | Fewer prompts | Bad crawl rules or poor translation can propagate before review | Raw-review and QA-review checkpoints |
| Automatic QA rewriting | Convenient cleanup | Literary edits can change meaning silently | Deterministic report and user-directed remediation |
| CAPTCHA bypass or login automation | Wider site coverage | Expands scope into brittle anti-bot handling and questionable automation | Stop with an actionable report |
| UI/API migration | Familiar old-app interaction | Delays validation of the agent-native core | Skills-only v1 |
| Legacy book migration | Reuse existing data | Couples the new design to old schema debt | New books only in v1 |

## Feature Dependencies

```text
[Workspace contracts]
    -> [Crawl helpers]
        -> [Crawl validation]
            -> [Raw-review checkpoint]
                -> [Initial glossary]
                    -> [Sequential translation]
                        -> [Progressive glossary merge]
                        -> [Deterministic QA report]
                            -> [QA-review checkpoint]
                                -> [EPUB 3.3 export]
                                    -> [Calibre conversion]

[Antigravity skills] -> orchestrate every step above
[Domain profiles] -> enhance [Crawl helpers]
[Per-book overrides] -> repair [Crawl validation] failures
```

### Dependency Notes

- **Translation requires crawl approval:** otherwise invalid raw extraction becomes expensive
  bad output.
- **Translation requires an initial glossary:** names and realms should be stable from the first
  translated chapter.
- **QA requires promoted translated files:** staged failed attempts must not be analyzed as
  completed chapters.
- **Export requires QA approval:** the generated ebook should not imply quality review happened
  when it did not.
- **Calibre conversion requires EPUB:** EPUB is the canonical artifact and conversion input.

## MVP Definition

### Launch With (v1)

- [ ] Four Antigravity skills: crawl, translate, QA, export.
- [ ] New workspace schema with atomic per-chapter state.
- [ ] HTTP crawler, Chromium fallback, domain profiles, and per-book overrides.
- [ ] Raw-review checkpoint and crawl validation report.
- [ ] Default `tien_hiep` YAML plus custom style validation.
- [ ] Automatic initial glossary and progressive per-chapter merge.
- [ ] Sequential context-isolated chapter workers with retry-stop-resume behavior.
- [ ] Deterministic QA report and user approval marker.
- [ ] EPUB 3.3 output, EPUBCheck integration, and Calibre conversion.

### Add After Validation (v1.x)

- [ ] More bundled style templates - add after custom-style contract proves stable.
- [ ] Operator commands for targeted retranslation - add when QA reports expose common repair
      workflows.
- [ ] Stronger crawl-profile library - add domains from real usage.
- [ ] Optional translation review worker - add only if deterministic QA misses material issues.

### Future Consideration (v2+)

- [ ] Codex adapter.
- [ ] Claude Code adapter.
- [ ] Legacy workspace migration.
- [ ] UI or API shell.
- [ ] Safe parallel translation modes based on segmentation or narrative anchors.

## Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Workspace and state contracts | HIGH | MEDIUM | P1 |
| Crawl and raw checkpoint | HIGH | HIGH | P1 |
| Sequential translation skill | HIGH | HIGH | P1 |
| Glossary lifecycle | HIGH | MEDIUM | P1 |
| QA report checkpoint | HIGH | MEDIUM | P1 |
| EPUB and Calibre export | HIGH | MEDIUM | P1 |
| Additional styles | MEDIUM | LOW | P2 |
| Additional agent adapters | MEDIUM | MEDIUM | P3 |
| UI/API | LOW for v1 | HIGH | P3 |

## Sources

- `../dich-truyen-tien-hiep/README.md` - old application baseline
- `../dich-truyen-tien-hiep/docs/ARCHITECTURE.md` - old pipeline patterns
- `../dich-truyen-tien-hiep/.agents/skills/translate-error-chapters/SKILL.md` - prior orchestrator-worker experiment
- `.planning/PROJECT.md` - user-approved v1 boundaries
- https://www.w3.org/TR/epub-33/ - EPUB 3.3 navigation and packaging expectations

---
*Feature research for: Antigravity-first agent-native novel translation workflow*
*Researched: 2026-05-31*
