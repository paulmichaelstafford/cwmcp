# CLAUDE.md — cwmcp

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

Process each lang/level combo **end-to-end** before starting the next one: audio → translations → alignments → upload. Do NOT batch all audio first then all translations — finish and upload each combo completely before moving on.

### Step-by-step (per chapter)

0. **Get publication info** — use `list_publications` to find the publication ID, then `get_publication_readme` to read the style guide, voice config, topic backlog, and chapter structure rules. If the book has a glossary in its readme, use the localized proper noun forms.

1. **Check what's done** — use `list_uploaded_chapters` to see which chapters are already uploaded. Determine the next chapter number.

2. **Write chapter.md** for each lang/level combo (18 total: 9 langs x 2 levels)
   - Path: `{content_path}/{onetime|continuous}/{book}/chapter-NNNN-slug/{lang}/{level}/chapter.md`
   - Front matter: `title: Chapter Title`
   - Body: `[narrator] Text here.` — all text is narrated (no character voices)
   - B1 = simple, B2 = intermediate
   - **Max 200 words per chapter** (both levels). Create more chapters if needed rather than exceeding the limit.

3. **Generate audio** — use `generate_audio` or `generate_audio_batch` tools
   - Calls cwtts service (Kokoro for EN, Voxtral/Mistral API for FR, Fish Audio API for ES/DE/IT/PT/ZH/JA/KO)
   - Caches `audio.mp3` + `marks.json` + `marks_in_milliseconds.json` next to chapter.md
   - Skips if audio.mp3 already exists (safe to re-run)
   - EN is free (Kokoro, local). Other languages use cloud APIs (cheap — cents per chapter).
   - Never delete audio.mp3, marks.json, or marks_in_milliseconds.json unless they have been successfully uploaded.

4. **Build translations** from cached marks
   - **Dispatch one agent per lang/level combo** — all 16 non-EN variants can run in parallel
   - Each agent writes a manual translation script (e.g. `scripts/build_el7_fr_b1.py`) and runs it
   - Uses `build_chapter_translations.py` with `build_and_save()` for European alignment via cwbe + manual CJK word pairs
   - For failing marks, provide manual overrides with alignment data
   - **Must happen after step 3** because translations must match marks.json 1:1
   - **Every mark must have non-empty `tokenAlignments` for all 8 target languages** — cwbe rejects uploads with any empty alignments. The local coverage check may pass but cwbe will reject.

5. **Upload** — use `upload_chapter` or `upload_batch` tools
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
- **Longer sentences help CJK**: the 40% coverage threshold is easier to hit with more characters per mark. A 3-word sentence needs every word mapped; a 15-word sentence can tolerate some gaps.

## Localization Rules

- **No Latin characters in CJK text.** Chinese (ZH), Japanese (JA), and Korean (KO) chapter text must use fully localized forms for all proper nouns, place names, and terminology. No English words in Latin script should appear in the narrative body text.
- **European languages must translate key terms.** Concepts like "Victory Mansions", "Big Brother", "telescreen", and "Victory Gin" must be translated into each target language — not left in English. Personal names (Winston, O'Brien, Goldstein) may remain in their original form as is conventional in published translations.
- **Consistency across chapters.** If a term is localized in one chapter, it must use the same localized form in all chapters. Use the glossary in the publication readme.

## Audio Production Style

- **Narrator only** — all text uses a single narrator voice. No character voices.
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

Voice IDs are configured in `cwbe/docker/cwtts/app/config.py`. EN is free (Kokoro, local). Other languages use cloud APIs (Mistral for FR, Fish Audio for the rest).

## Translation & Alignment Rules

- **Two-track alignment strategy:**
  - **European (EN, FR, ES, DE, IT, PT):** Use awesome-align via cwbe's `/api/service/align` endpoint. It gets 95-100% coverage for European pairs — no need for Claude to generate alignments. Translate the text, then call `align_text` to get alignments automatically.
  - **CJK (ZH, JA, KO):** Use manual Claude-generated translations + word-pair alignments. Awesome-align fails CJK (~26-39% coverage). Claude provides phrase-level alignments with ~93% target coverage.
- **Translation quality:** Claude provides all translations (European and CJK) for correct domain terminology, proper nouns, and consistent literary register. Only the alignment step differs.
- Format: `TokenAlignment { sourceStart, sourceEnd, targetStart, targetEnd }` — all inclusive character offsets.
- Target languages: EN, FR, ES, DE, IT, PT, ZH, JA, KO (8 targets per source, excluding source language).
- **Alignment coverage required** — cwbe validates that alphanumeric characters (`isLetterOrDigit()`) in both source and target text are covered by alignment ranges. Thresholds: **70% for European-European pairs**, **40% for any pair involving CJK**.
- **Max 3 concurrent requests** to cwbe/awesome-align. The server is on limited hardware — don't bombard it.

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
