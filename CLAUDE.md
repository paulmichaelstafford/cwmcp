# CLAUDE.md — cwmcp

**This file is the single source of truth.** Do not use memory files or save memories. All guidance, rules, and workflow instructions live here. If something is not in this file, it is not a rule.

## What This Is

MCP server for the CollapsingWave audiobook pipeline. Exposes tools for checking chapter status, generating audio, building translations, testing alignments, and uploading chapters.

**This is a public repo.** Keep it clean — no one-off scripts, hardcoded secrets, throwaway files, or temp debugging code. If something is not reusable, it does not belong here.

Credentials (cwbe service account, cwtts URL) are stored in `~/.cwmcp/config.properties` — see `config.example.properties` for the format.

## Working with Book Content

**All publication files (books, chapters, audio, translations) live under the `content_path` configured in `~/.cwmcp/config.properties`**, not in this repo. When asked to work on books, edit chapters, view content, or do anything involving publication files, always read `content_path` from the config and operate there. Do not ask — just do it.

## Running Tests

```bash
cd /path/to/cwmcp
PYTHONPATH=src python3 -m pytest tests/ -v
```

## Project Structure

- `src/cwmcp/server.py` — MCP entry point, all tool registrations
- `src/cwmcp/config.py` — Reads ~/.cwmcp/config.properties
- `src/cwmcp/tools/` — Tool implementations (thin wrappers)
- `src/cwmcp/lib/` — Core logic (translations, uploads, cwbe client, audio generation)
- `tests/` — Unit tests

## Key Concepts

- 9 languages: EN, FR, ES, DE, IT, PT, ZH, JA, KO
- 2 levels: B1 (simple), B2 (intermediate)
- 18 combos per chapter (9 langs x 2 levels)
- Coverage thresholds: 70% European-European, 40% involving CJK
- cwbe URL is hardcoded: https://be.collapsingwave.com
- Swagger UI is available at https://be.collapsingwave.com/api/open/swagger-ui.html to browse cwbe endpoints. Username and password are in `SecurityConfig.kt` in cwbe.

## Quick Start — New Chapter Pipeline

When asked to do "chapter N" for a book, this is the full workflow.

### Processing order

Process each lang/level combo **end-to-end** before starting the next one: audio → translations → upload. Do NOT batch all audio first then all translations — finish and upload each combo completely before moving on. Use up to 4 parallel agents, each processing one combo end-to-end.

### Step-by-step (per chapter)

0. **Get publication info** — use `list_publications` to find the publication ID, then `get_publication_readme` to read the style guide, voice config, topic backlog, and chapter structure rules. If the book has a glossary in its readme, use the localized proper noun forms. The upload tool reads the publication ID from a local `README.md` in the book directory (looks for `**Publication ID (cwbe):** <uuid>`). Create this file if missing, using the ID from `list_publications`.

1. **Check what's done** — use `list_uploaded_chapters` to see which chapters are already uploaded. Determine the next chapter number.

2. **Prepare abridged source** (first time only, skip if `text/abridged.txt` already exists)
   - Scan `text/original.txt` and plan how the full narrative maps to ~100 chapters at ~200 words each.
   - Write `text/abridged.txt` — a condensed version of the narrative that fits the 100-chapter budget. Compress descriptive passages, cut repetitive sections, merge minor scenes. Preserve all key plot beats, character arcs, and pivotal moments.
   - `original.txt` is never modified — it's the canonical reference. `abridged.txt` is the working source that chapters are written from.
   - When rewriting, follow the CJK-Friendly Writing rules (see below) — simple structure, concrete words, proper nouns, no idioms. This makes downstream alignment trivial.
   - For shorter books where the original already fits within 100 chapters at 200 words, `abridged.txt` may be close to the original with only minor restructuring.

3. **Write chapter.md** for each lang/level combo (18 total: 9 langs x 2 levels)
   - Path: `{content_path}/{onetime|continuous}/{book}/chapter-NNNN-slug/{lang}/{level}/chapter.md`
   - Front matter: `title: Chapter Title`
   - Body: `[narrator] Text here.` — all text uses the `[narrator]` tag. Direct quotes and dialogue within narrator lines are fine.
   - B1 = simple, B2 = intermediate
   - **Max 200 words per chapter** (both levels). Create more chapters if needed rather than exceeding the limit.
   - **Max 100 chapters per book.** Write chapters from `text/abridged.txt`, not from `original.txt`.

4. **Generate audio**
   - **EN only:** use `generate_audio` or `generate_audio_batch` MCP tools. These go through cwbe which runs Kokoro locally.
   - **All other languages:** call the TTS APIs directly. cwbe only handles EN.
     - **FR:** Mistral Voxtral API (`mistral_api_key` from config)
     - **ES, DE, IT, PT, ZH, JA, KO:** Fish Audio API (`fish_audio_api_key` from config)
     - See TTS Voice Config table for voice IDs.
   - Cache `audio.mp3` + `marks.json` + `marks_in_milliseconds.json` next to chapter.md in the same format as the MCP tool produces.
   - Skips if audio.mp3 already exists (safe to re-run).
   - Never delete audio.mp3, marks.json, or marks_in_milliseconds.json unless they have been successfully uploaded.
   - **After generating the first combo, check mark count.** If >15, rewrite chapter text before continuing.

5. **Build translations** — use `build_translations` MCP tool
   - Translates all marks to 8 target languages and aligns via awesome-align (cwbe `/api/service/align`)
   - European pairs pass automatically. **CJK pairs (ZH, JA, KO) return empty alignments** — Claude must build these itself (see CJK Alignment below).
   - After `build_translations` returns, check for any CJK target languages with empty `tokenAlignments`. For each, provide overrides and re-run `build_translations` with the `overrides` parameter.
   - Override format: `{"mark_idx": {"lang": {"text": "...", "tokenAlignments": [...]}}}`
   - **Must happen after step 4** because translations must match marks.json 1:1
   - **Every mark must have non-empty `tokenAlignments` for all 8 target languages** — cwbe rejects uploads with any empty alignments

6. **Upload** — use `upload_chapter` or `upload_batch` tools
   - Sends cached audio + marks + translations to cwbe
   - Max 3 concurrent uploads (cwbe is on limited hardware)

### File structure per chapter per lang per level
```
chapter.md                    # source text with speaker markup
audio.mp3                     # cached TTS output (deleted after successful upload)
marks.json                    # sentence boundaries with UUIDs
marks_in_milliseconds.json    # mark UUID -> millisecond offset
translations.json             # 8 target languages with word alignments
```

### Languages & Levels
- 9 languages: EN, FR, ES, DE, IT, PT, ZH, JA, KO
- 2 levels: B1 (simple), B2 (intermediate)
- = 18 chapter variants per story chapter

## Writing Rules for Alignment-Friendly Text

Chapter text must be alignment-friendly **before** generating audio. Poorly structured text causes exponentially more alignment work.

- **Every sentence must be at least 5 words.** No fragments ("Gray.", "Silent.", "DELETE."). Merge fragments into full sentences.
- **Aim for 10-15 marks per chapter.** Each `[narrator]` line may split into multiple marks at sentence boundaries. Short sentences = more marks = more alignment work. Chapter with 35 marks takes 3-4x longer than one with 12 marks.
- **Short sentences are hard to align.** A 3-word sentence like `"Of course."` needs every single word mapped to pass coverage — there is zero room for error. A 15-word sentence can tolerate gaps because missing a few words still clears the threshold. Short sentences are the #1 cause of alignment failures, especially for CJK where the 40% threshold is tight on small text. Combine short exchanges into longer lines: `"Of course, let me weigh it first," the clerk says, putting the package on the scale.` Direct quotes are fine — just keep each sentence substantial (8+ words).
- **Validate mark count after first audio.** After generating audio for the first combo (e.g. EN/B1), check marks.json. If mark count exceeds 15, stop and rewrite the chapter text before generating more audio.

### CJK-Friendly Writing (applies to abridged text and all chapter text)

These rules make CJK alignment fast and reliable. Follow them when writing `text/abridged.txt` and all chapter.md files:

- **Simple sentence structure.** SVO order, no nested clauses. CJK languages rearrange heavily — complex English structures produce translations where words scatter and are hard to pair.
- **Concrete nouns and verbs.** "sword", "goddess", "whispered" map 1:1 to CJK equivalents. Avoid abstract phrasing like "the satisfaction of having done so" — it becomes an unparseable blob in translation.
- **Use proper nouns liberally.** Every "Achilles"→"アキレス" is free alignment coverage. The more names in a sentence, the easier alignment gets.
- **Avoid idioms and phrasal verbs.** "hold back" must map as a unit to a CJK expression. "restrain" is cleaner — it maps 1:1 to a single verb.
- **Minimize function words.** "right where he stood" is 5 English words that map to 3 Japanese characters. Dense source text with small words (the, a, of, to, by) drags down source coverage because they have no CJK counterpart to pair with.
- **Write like a subtitle.** Direct, concrete, name-heavy prose aligns easily. Literary flourishes are the enemy of CJK alignment.

## Localization Rules

- **No Latin characters in CJK text.** Chinese (ZH), Japanese (JA), and Korean (KO) chapter text must use fully localized forms for all proper nouns, place names, and terminology. No English words in Latin script should appear in the narrative body text.
- **European languages must translate key terms.** Concepts like "Victory Mansions", "Big Brother", "telescreen", and "Victory Gin" must be translated into each target language — not left in English. Personal names (Winston, O'Brien, Goldstein) may remain in their original form as is conventional in published translations.
- **Consistency across chapters.** If a term is localized in one chapter, it must use the same localized form in all chapters. Use the glossary in the publication readme.

## Audio Production Style

- **Single `[narrator]` tag** — all text uses the `[narrator]` tag. Direct quotes and dialogue are fine within narrator lines. No separate character voice tags.
- **No sound effects** — do not use `[sfx:...]` tags. Clean narrator audio only.

## TTS Voice Config

| Language | Engine | Voice ID | Voice Name |
|----------|--------|----------|------------|
| EN | Kokoro (local) | af_heart | Heart (female, grade A) |
| FR | Voxtral (Mistral API) | e0580ce5-e63c-4cbe-88c8-a983b80c5f1f | Marie Curious |
| ES | Fish Audio | f53102becdf94a51af6d64010bc658f2 | Jesus Narrador |
| DE | Fish Audio | a42859a3e3674c58b73be590f62152eb | Markanter Erzähler |
| IT | Fish Audio | 4d45631184584ce1b2eda4e06ae14e5f | Narratore de Brainrot Italiano |
| PT | Fish Audio | 4d72497e3ceb4c75a7c5563900975afd | Narração Contos de Terror |
| ZH | Fish Audio | e0cbb35d7cc2420c87f2ea6ad623b61a | Mature Male Story |
| JA | Fish Audio | 0221478a85aa4703a410ccb405afb872 | Late Night Storyteller |
| KO | Fish Audio | 4194b66c6ec24dc3be72a0cbd2547b61 | Kore Storytelling |

EN uses Kokoro via cwbe (free, local). All other languages call external APIs directly — Mistral for FR, Fish Audio for the rest. cwbe does not handle non-EN TTS. API keys are in `~/.cwmcp/config.properties` (`mistral_api_key`, `fish_audio_api_key`).

## Translation & Alignment Rules

- The `build_translations` MCP tool handles translation and alignment. It translates each mark to 8 target languages and computes word-level alignments.
- **European-European pairs (EN, FR, ES, DE, IT, PT ↔ EN, FR, ES, DE, IT, PT):** Use awesome-align via cwbe `/api/service/align`. Gets 95-100% coverage — usually passes without manual work.
- **Any pair involving CJK (ZH, JA, KO):** cwbe returns **empty `tokenAlignments`** for these pairs. Claude must always build CJK alignments itself using the word-pair approach (see below).
- Format: `TokenAlignment { sourceStart, sourceEnd, targetStart, targetEnd }` — all **inclusive** character offsets (0-based).
- Target languages: EN, FR, ES, DE, IT, PT, ZH, JA, KO (8 targets per source, excluding source language).
- **Coverage thresholds** — cwbe validates that alphanumeric characters (`isLetterOrDigit()`) in both source and target text are covered by alignment ranges. Thresholds: **70% for European-European pairs**, **40% for any pair involving CJK**.
- **Max 3 concurrent requests** to cwbe/awesome-align. The server is on limited hardware.

## CJK Alignment (ZH, JA, KO)

cwbe does not produce alignments for CJK languages. Claude must build them directly using word pairs and the `align()` helper in `src/cwmcp/lib/translations_helper.py`.

### How it works

1. `build_translations` returns translations for all 8 target languages. European pairs have `tokenAlignments` populated. CJK pairs have **empty** `tokenAlignments`.
2. For each mark × CJK target language with empty alignments, Claude provides **word pairs** — a list of `(source_substring, target_substring)` tuples mapping phrases between the source text and the CJK translation.
3. The `align()` helper computes character offsets from these pairs automatically. No manual offset math needed.
4. Re-run `build_translations` with the `overrides` parameter containing the computed alignments.

### Word pair guidelines

- Map content words and phrases: nouns, verbs, adjectives, names, key expressions.
- Each pair must be a **literal substring** of the source and target texts (case-sensitive, exact match).
- Aim for ~40-60% coverage of alphanumeric characters on both sides. More pairs = higher coverage, but diminishing returns past 60%.
- Proper nouns are easy wins (e.g., `("Agamemnon", "アガメムノン")`).
- Map multi-word phrases when the target is a single unit (e.g., `("reached for", "手を伸ばし")`).
- Skip function words, particles, and grammatical markers that don't map cleanly.

### Phrase-level alignment for long marks (B2 text, CJK source)

**Single-word pairs fail on marks longer than ~120 characters**, especially with JA source. Japanese text is inflated by particles (は、が、を、の、に) and verb endings (ました、ていた) that can't be independently mapped. With 15 single-word pairs averaging 3 chars each, you max out at ~30% source coverage on a 160-char mark — below the 40% threshold.

**The fix: map long phrases that include surrounding particles and grammar.**

```python
# BAD — single words, covers 5 JA chars total:
("夫", "husband"), ("トロイア", "Troy")

# GOOD — phrase includes particles, covers 18 JA chars:
("夫がトロイアから帰還するのを待ち続け", "waited for her husband to return from Troy")
```

**Rules of thumb:**
- **B1 marks** (~100 chars): single-word pairs usually sufficient
- **B2 marks** (150-200 chars): use phrase-level pairs, especially for JA/ZH source
- **CJK source → European target** is harder than European → CJK because the 40% threshold bites harder on the verbose CJK side
- For JA source, aim for 5-10 long phrase pairs per mark (each covering 10-25 JA chars) rather than 15+ short pairs
- Include the particles/grammar in the JA phrase — `("妻ペーネロペーに求婚する権利を主張", "claimed the right to propose to his wife Penelope")` covers 17 chars vs `("妻", "wife")` covering 1

### Example

```python
from cwmcp.lib.translations_helper import align, check_coverage

source = "He reached for his sword and nearly struck Agamemnon down."
target = "彼は剣に手を伸ばし、アガメムノンを倒しそうになった。"

pairs = [
    ("He", "彼は"),
    ("sword", "剣"),
    ("reached for", "手を伸ばし"),
    ("Agamemnon", "アガメムノン"),
    ("struck", "倒し"),
]

alignments = align(source, target, pairs)
src_cov = check_coverage(source, alignments, side="source")
tgt_cov = check_coverage(target, alignments, side="target")
# src_cov=55%, tgt_cov=52% — passes 40% threshold
```

### Integration with build_translations

After `build_translations` returns with empty CJK alignments:
1. Read the translations.json to get each mark's source text and CJK translations
2. For each mark × CJK language, generate word pairs and compute alignments using `align()`
3. Package as overrides: `{mark_idx: {lang: {"text": translated_text, "tokenAlignments": [...]}}}`
4. Re-run `build_translations` with the `overrides` parameter to merge them in

## Available MCP Tools

- `list_publications` — list all publications with IDs and titles
- `list_uploaded_chapters` — see what's been uploaded for a publication
- `get_publication_readme` — fetch style guide, voice config, topic backlog
- `list_books` — list local book directories
- `chapter_status` — check local file status for a chapter's 18 combos
- `generate_audio` — generate TTS for a single lang/level combo
- `generate_audio_batch` — generate TTS for all combos missing audio
- `build_translations` — build translations.json using Azure + align
- `align_text` — test alignment on a single source/target pair
- `check_coverage` — check alignment coverage for a translations.json
- `upload_chapter` — upload a single lang/level combo
- `upload_batch` — upload all ready combos for a chapter
- `download_chapters` — download all chapters for a publication (backup)
