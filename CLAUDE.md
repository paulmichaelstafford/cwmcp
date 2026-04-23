# CLAUDE.md — cwmcp

**This file is the single source of truth.** Do not use memory files or save memories. All guidance, rules, and workflow instructions live here. If something is not in this file, it is not a rule.

## What This Is

MCP server for the CollapsingWave audiobook pipeline. The default path is one call to `create_chapter_from_marks` which triggers the full cwbe pipeline; the rest of the surface is publication/chapter CRUD, break-glass lego blocks for manual fix-ups, and diagnostics.

**This is a public repo.** Keep it clean — no one-off scripts, hardcoded secrets, throwaway files, or temp debugging code. If something is not reusable, it does not belong here.

Credentials (cwbe service account, optional Grafana viewer) are stored in `~/.cwmcp/config.properties` — see `config.example.properties` for the format.

## Diagnostics & Access — use these when things go wrong

Before giving up on a flaky `/from-marks` call, a bad translation, or a weird upload error, use the two diagnostic surfaces below. They cover ~everything.

### Swagger UI — browse every cwbe endpoint

- **URL:** `https://be.collapsingwave.com/api/open/swagger-ui.html`
- **Auth:** click "Authorize", use `cwbe_user` / `cwbe_password` from `~/.cwmcp/config.properties` (same service account). No JWT, no captcha.
- **The section that matters to cwmcp is `/api/service/*`.** Those are the endpoints cwmcp already wraps — `/chapters/from-marks`, `/jobs/{id}`, `/align`, `/tts/generate-chapter`, `/debug/gemini/gloss-tokens`, `/publications/{id}/chapters`, etc. Expand the `service-controller` group in Swagger to see every request/response schema live. If you're unsure what a field means or what a response looks like, it's faster to hit the endpoint in Swagger than to grep cwbe source.
- `/api/admin/*` and `/api/consumer/*` are visible but not relevant for authoring — they need JWT cookies, not basic auth, and cwmcp doesn't use them.
- **Typical use:** you hit an unfamiliar `400 Bad Request` from cwbe, open Swagger, click the relevant `/api/service/*` endpoint, read the request schema, compare to what cwmcp sent, fix.

### Grafana — cwbe / cwtts / cwseg / awesome-align logs

- **URL:** `https://grafana.collapsingwave.com`
- **Auth:** `grafana_user` / `grafana_password` from `~/.cwmcp/config.properties`. If blank, fall back to admin creds from cwbe's `CLAUDE.md` — or create a read-only Grafana Viewer service account token and drop it in `~/.cwmcp/config.properties`.
- **Datasources:** Loki (logs, `{container="cwbe"}` / `{container="cwtts"}` / `{container="cwseg"}` / `{container="awesome-align"}`), Prometheus (metrics).
- **Primary use for cwmcp:** debugging `/chapters/from-marks` — see the dedicated "Debugging `/chapters/from-marks` via Grafana Loki" section below for query patterns and log-line meanings. The `query_logs` MCP tool wraps this.
- **Also useful:** when a whole phase looks slow or wedged (e.g. awesome-align hung), check the pod's logs in Grafana to confirm the issue is on the cwbe side, not client-side.

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
- `src/cwmcp/tools/` — Tool implementations (one file per tool or per entity family)
- `src/cwmcp/lib/cwbe_client.py` — httpx-based client wrapping `/api/service/*` endpoints. The only lib file; no orchestration lives here.
- `tests/` — Unit tests

## Key Concepts

### Terminology

- **Mark** — a single sentence-level segment in the audio. Each mark has a UUID, text, and a start timestamp in milliseconds. In the app, each mark is one screen — the user presses the next button to advance to the next mark. Marks are the atomic unit of playback and alignment. A typical chapter has ~10 marks.
- **Chapter** — one story unit containing all marks. Each chapter has 18 variants (9 langs x 2 levels).

In marks.json, the `paragraph` field groups marks for audio pause duration (800ms between paragraph groups, 300ms within a group). This is purely an audio production detail — in the app every mark is its own screen regardless of paragraph grouping.

### Numbers

- 9 languages: EN, FR, ES, DE, IT, PT, ZH, JA, KO
- 2 levels: B1 (simple), B2 (intermediate)
- 18 combos per chapter (9 langs x 2 levels)
- Coverage thresholds: 70% European-European, 40% involving CJK
- cwbe URL is hardcoded: https://be.collapsingwave.com (Swagger + Grafana access documented in the Diagnostics & Access section at the top)

## Preferred Way to Create a Chapter — `/chapters/from-marks`

**This is the only path.** One cwbe call creates **one chapter variant** (one language, one level) from pre-split marks: cwbe generates audio via cwtts, translates the marks to the other 8 languages via Gemini Flash-Lite and attaches them to the chapter's marks for in-app reading, aligns EU targets via awesome-align (CJK targets get `cwseg` tokens + Gemini per-token glosses at ingest), and persists. To build all 9 language variants of a chapter, the orchestrator calls this endpoint **once per source language** — in parallel is fine (be gentle on hardware — **max 2 concurrent chapters**, see Concurrency Cap below).

**MCP tool:** `create_chapter_from_marks(publication_id, title, language, level, marks, source_audio_blob_name=None)` — wraps the endpoint and polls the resulting Job until terminal. Use this from the MCP; don't hand-craft the HTTP call.

**Endpoint (reference):** `POST https://be.collapsingwave.com/api/service/publications/{publicationId}/chapters/from-marks` (basic auth with service account). Full schema lives in Swagger (see Diagnostics & Access at the top). Body shape:

```json
{
  "title": "Chapter 3 — The Stone",
  "language": "DE",
  "level": "B2",
  "marks": ["Achilles war wütend auf Agamemnon.", "..."],
  "sourceAudioBlobName": "..."       // optional — skips source TTS on retry (scrape from a failed run's logs)
}
```

**Response:** a `Job` with `status=PROCESSING`. The MCP tool polls `GET /api/service/jobs/{jobId}` every 5s until `COMPLETED` or `FAILED`. On success, `storedDataId` (returned as `chapter_id` by the tool) holds the created chapter's UUID. To build the other 8 variants of the same story chapter, repeat the call with a different `language` and the corresponding `marks` in that language. If the same `(publication, language, level, title)` already exists, the call skips the work and returns that chapter's UUID — safe to retry.

**Retry after failure:** translations are not cached (Gemini is cheap enough to re-run). The Job `message` (and cwbe logs) contains `sourceAudioBlobName=...` for that specific call — pass it back as `source_audio_blob_name` to skip re-TTS on retry. The blob name is **per-call**: it belongs to one source language, so don't reuse it across different `language` calls.

### Concurrency Cap — one chapter at a time, no concurrent runs

**Run chapter ingests strictly sequentially — never more than one `/from-marks` call in flight.** The cwbe host has only 4 CPU threads and a single replica of each service (cwbe, cwtts, cwseg, awesome-align); running concurrent chapters starves the JobProcessor pool and risks re-introducing the thread-pool deadlock we hit during Art of War ch4 retries. Even concurrency=2 can cluster Gemini/cwtts calls enough to trigger transient 503s. Process 18 combos as 18 back-to-back sequential runs.

Because concurrency is 1, the MCP `create_chapter_from_marks` tool is the right shape for this: it already serializes within a single Claude session (even if you put two calls in the same assistant turn, the runtime runs them back-to-back, verified via cwbe HTTP arrival timestamps). For a full 18-combo batch, loop over the MCP tool — no async driver needed. If you're already shelling out for other reasons, a simple sequential Python loop against `/api/service/publications/{id}/chapters/from-marks` + poll `/api/service/jobs/{id}` is fine (basic auth with `cwbe_user`/`cwbe_password` from `~/.cwmcp/config.properties`). Do **not** use `asyncio.gather` + `Semaphore(N>1)` — that's the old concurrency=2 pattern and is no longer the policy.

### No local chapter files

Marks are authored upstream (e.g., in `cwaudio/**/build_translations_*.py` scripts, or a `chapter.md` that a caller splits into sentences). Once the marks list is ready, send it to `create_chapter_from_marks` — cwbe owns everything that follows (audio, translations, alignments, tokens, blob). No intermediate local files need to exist in cwmcp-land. The break-glass path is the exception: `upload_chapter_from_zip` takes 4 file paths, so you only materialise those files when you're manually patching a specific chapter.

### Languages & Levels
- 9 languages: EN, FR, ES, DE, IT, PT, ZH, JA, KO
- 2 levels: B1 (simple), B2 (intermediate)
- = 18 chapter variants per story chapter

## Design Principle — cwbe orchestrates, cwmcp triggers

**Don't rebuild pipeline logic inside cwmcp.** When something new needs to happen across all chapters (a new tokeniser, a new translation provider, a back-fill), add it as an endpoint in cwbe and have cwmcp call it. This keeps:

- **One place to retry** — cwbe already caches `sourceAudioBlobName`. cwmcp doesn't have to replicate blob-caching or mid-pipeline state.
- **One place to see logs** — everything runs inside the cwbe pod, so Loki shows the full pipeline per job. No cwmcp-side vs cwbe-side hunt.
- **One atomic unit** — success means the chapter is fully persisted, failure means retry the endpoint. Cwmcp never holds partial state between phases.
- **Thin client, fewer moving parts** — cwmcp stays a small set of wrappers around cwbe calls. No duplicated orchestration.

The break-glass **lego blocks** (`generate_audio`, `translate_texts`, `align`, `gloss_tokens`, `upload_chapter_from_zip`) are thin MCP wrappers around individual `/api/service/*` endpoints. Each one is one HTTP call + auth with no orchestration, so they stay cheap to maintain. Use them when you need to patch a single mark's translation / alignment and upload the exact bytes; don't use them to rebuild the whole pipeline locally.

## Claude-Side Authoring Rules (applied during mark writing)

The sections below describe how marks should be written. They are enforced by **Claude**, not by cwmcp or cwbe:

- **cwmcp** is a thin trigger — `create_chapter_from_marks` ships whatever strings it receives, no validation.
- **cwbe** runs the pipeline on whatever it receives; it only rejects structurally invalid input (blank marks, count mismatches).

The rules live here because sessions inside this repo are typically Claude sessions helping author or review marks. Claude reads these rules and applies them before calling the endpoint. Nothing in the codebase enforces them — if Claude ignores them, a bad chapter ships.

**Canonical home:** `cwaudio/CLAUDE.md` + each publication's readme. If those differ from what's here, they win.

## Writing Rules for Alignment-Friendly Text

Chapter text must be alignment-friendly **before** generating audio. Poorly structured text causes exponentially more alignment work.

- **Every sentence must be at least 5 words.** No fragments ("Gray.", "Silent.", "DELETE."). Merge fragments into full sentences.
- **Never emit a mark that is only closing punctuation.** In CJK (and sometimes FR/IT) prose the source text may put the closing quote on its own line for visual pacing — e.g. a multi-line quoted block followed by `」` / `』` / `»` / `"` alone. When writing marks (hand-authored `MARKS = [...]` tuples, or any chapter.md → marks conversion), **append the trailing quote to the previous mark's text** rather than emitting it as its own tuple. A lone-punctuation mark becomes a useless one-character card in the reader, gets 0 tokens, and is a waste of a sentence slot. Same rule applies to stray single-name tails ("Owen.") or one-word dialogue beats ("Good.", "Bien.") — if the "sentence" is under 5 words, merge it back into the neighboring mark.
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

- **Single `[narrator]` tag** — all text uses the `[narrator]` tag when marks come from a chapter.md. Direct quotes and dialogue are fine within narrator lines. No separate character voice tags.
- **cwtts is behind cwbe** — cwbe invokes cwtts internally as phase 0 of `/from-marks`. cwtts routes to the correct engine (Kokoro for EN, Voxtral for FR, Fish Audio for others), generates audio per mark, adds silence gaps, and returns the finished MP3 + mark timestamps with UUIDs. cwmcp never talks to cwtts directly.
- **No sound effects** — clean narrator audio only.

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

All TTS generation is handled by cwtts, which is invoked internally by cwbe during phase 0 of `/from-marks`. API keys (Mistral, Fish Audio) are configured on the cwtts pod. cwmcp only needs `cwbe_user` / `cwbe_password` (and optional `grafana_*` for diagnostics) in `~/.cwmcp/config.properties` — no cwtts creds.

## Available MCP Tools

Twenty tools, grouped by purpose.

**Create + trigger (the default path):**
- `create_chapter_from_marks` — POSTs `/chapters/from-marks`, polls the Job until terminal, returns `chapter_id` on success or `sourceAudioBlobName=...` in the `message` on failure for retry.

**Read cwbe:**
- `list_publications` — all publications with IDs, titles, types.
- `list_uploaded_chapters` — what's been uploaded for a publication.
- `get_publication_readme` — fetch a publication's style guide / voice config / glossary.
- `download_chapters` — bulk-download every chapter zip for a publication (backup / QA).

**Publication CRUD:**
- `create_publication` — new publication with cover jpeg (POST).
- `update_publication_readme` — replace the readme markdown (partial update).
- `update_publication_titles` — patch title and/or per-lang headers and descriptions (partial update, merged per-lang).
- `update_publication_flags` — patch `is_complete` / `archived` (partial update).
- `delete_publication` — destroy publication + every chapter + blob. Requires `confirm=True`.

**Chapter CRUD:**
- `update_chapter_metadata` — change title / language / level without re-uploading audio.
- `delete_chapter` — destroy one chapter variant + its blob. Requires `confirm=True`.

**Break-glass lego blocks** — one thin wrapper per cwbe service endpoint. Call them in sequence to assemble a chapter manually when `/from-marks` is wrong:
- `generate_audio(language, marks)` → base64 MP3 + mark timings from cwtts.
- `translate_texts(source_language, texts)` → Gemini sentence translations as `{lang: [texts]}`.
- `align(source_language, source_text, targets)` → awesome-align EU↔EU token alignments.
- `gloss_tokens(source_language, sentence_text, sentence_translations, tokens)` → Gemini per-token glosses for CJK.
- `upload_chapter_from_zip(publication_id, audio_path, marks_path, marks_in_ms_path, translations_path, title, language, level, chapter_id=None)` → POST/PUT `/chapters/from-audio` with the 4 file bytes.

**Local content navigation:**
- `list_books` — enumerate book dirs under `content_path` with their cwbe publication IDs.
- `chapter_status` — show which files exist for a local chapter's 18 combos (useful when authoring marks).

**Diagnostics:**
- `query_logs` — scrape Grafana Loki by job ID, substring, or raw LogQL. Primary use: pull `sourceAudioBlobName=...` from a failed `/from-marks` job log so you can retry.

## Debugging `/chapters/from-marks` via Grafana Loki

Every phase of a `/from-marks` run logs to Loki under `{container="cwbe"}`. When a job fails or hangs, query the logs directly — they're the source of truth. Credentials (`grafana_user`, `grafana_password`, `grafana_url`) live in `~/.cwmcp/config.properties`; if blank, fall back to the admin creds in the cwbe `CLAUDE.md` (or create a read-only Grafana Viewer service account token and use that instead).

**Query pattern (Loki via Grafana datasource proxy):**

```bash
source <(grep = ~/.cwmcp/config.properties | sed 's/ *= */=/g')
NOW=$(date +%s)000000000
BACK=$(($(date +%s) - 900))000000000   # last 15 min

curl -sS -u "$grafana_user:$grafana_password" \
  --data-urlencode 'query={container="cwbe"} |= "from-marks"' \
  --data-urlencode "start=$BACK" --data-urlencode "end=$NOW" \
  --data-urlencode "limit=200" --data-urlencode "direction=backward" \
  -G "$grafana_url/api/datasources/proxy/uid/loki/loki/api/v1/query_range"
```

**Log lines to grep for (most useful → least):**

| Grep | Meaning |
|---|---|
| `from-marks: audio blob=` | Phase 0 done. Blob name follows. Reusable on retry as `sourceAudioBlobName`. |
| `from-marks: translating N marks from <lang> via Gemini` | Phase 1 (Gemini sentence translation) started. Not cached — always re-runs on retry. |
| `from-marks: <lang>/<level> '<title>' already exists (id=...); skipping` | The chapter is already persisted — retry is a no-op, returns the existing UUID. |
| `from-marks failed for <lang>/<level> '<title>': …` | Call failed. Message includes `sourceAudioBlobName=…` — pass it back in the retry request to skip re-TTS. |
| `awesome-align failed for mark N (XX→EU)` | Alignment call errored — the mark falls back to empty alignments but the job continues. |
| `source mark produced no tokens` / `target produced no tokens` | cwseg returned an empty token list (usually degenerate input — punctuation/whitespace only). Fix the input. |

**Retry shortcut:** if a call fails, grep for the audio blob name in its log window:

```bash
... |= "from-marks" |~ "audio blob="
```

then call `create_chapter_from_marks` again with the same `marks` + `title` + `language` + `level`, plus `source_audio_blob_name` from the logs. If the chapter already exists from a prior run, the call short-circuits and returns its UUID.

## Verifying a Chapter (non-audio QA)

After a `/from-marks` call (or any ingest) succeeds, don't trust that `COMPLETED` means "good" — it only means "persisted". Audio QA is a separate listening pass. Use this checklist for the **non-audio** parts: text, translations, alignments, tokens, and consistency.

**Fetch the chapter bundle.** There's no JSON-detail endpoint; use the download URL:

```bash
source <(grep = ~/.cwbe/config.properties | sed 's/ *= */=/g')
URL=$(curl -sS -u "$service_user:$service_password" \
  "https://be.collapsingwave.com/api/service/publications/<pubId>/chapters/<chapId>/download-url" | tr -d '"')
curl -sSL "$URL" -o /tmp/chapter.zip && unzip -o /tmp/chapter.zip -d /tmp/chapter/
```

You'll get `audio.mp3`, `marks.json`, `marks_in_milliseconds.json`, `translations.json`. Inspect the three JSON files — that's everything non-audio.

**Or** for bulk: use the `download_chapters` MCP tool to grab every chapter in the publication at once.

### Checks

1. **Title + metadata**
   - Title follows `NNNN - <localized title>` pattern (e.g. `0004 - D.B. Cooper`, `0003 - Das Handbuch des Giftmischers`).
   - Language-specific title matches what the publication glossary prescribes — cross-check against `get_publication_readme`.
   - `language` and `level` on the chapter record match what you requested.

2. **Mark count + text**
   - Mark count matches the source marks you sent (14 in, 14 out — cwbe rejects mismatches, but double-check).
   - Every mark's `text` is non-empty and at least 5 words (alignment-friendliness rule). Short sentences are the #1 cause of bad alignment downstream.
   - Proper nouns and numbers preserved from the source (`Cooper`, `Boeing 727`, `1971`, `$200,000`).

3. **Language + level match** (covers both the chapter record and the translations block)
   - Chapter record's `language` matches what you requested and `level` is exactly `B1` or `B2` as requested. Mismatch = bug — reject.
   - For each source mark in `translations.json`, the `language` field equals the chapter's language (all 14 source marks agree).
   - For each mark, the set of target languages in `translationResults[].language` is **exactly** `{EN, FR, ES, DE, IT, PT, ZH, JA, KO} − chapter.language` — no duplicates, no missing, no extras.
   - Spot-check that the source `text` is actually in the claimed language (e.g. a DE chapter should have `ü/ß`, not ASCII-only English). Quick tell: if a "DE" mark looks English, you sent the wrong marks list.

4. **Audio language** — verify the `audio.mp3` is actually spoken in the claimed language (TTS routing bug, wrong voice clone, or caller sent wrong marks can all silently produce "German" audio that's actually English). Use Whisper's auto-detect on the first 30s — fast and local:

   ```bash
   # Omit --language to trigger auto-detection (openai-whisper's CLI has no
   # "auto" value — you just leave the flag off).
   whisper /tmp/chapter/audio.mp3 --model tiny \
     --task transcribe --output_format json --output_dir /tmp/whisper-check \
     --verbose False --fp16 False
   python3 -c "import json; print(json.load(open('/tmp/whisper-check/audio.json'))['language'])"
   ```

   Whisper prints a 2-letter ISO code (`en`, `de`, `fr`, `es`, `it`, `pt`, `zh`, `ja`, `ko`) — it must equal `chapter.language.lower()`. Mismatch = reject + investigate (check cwtts `ENGINE_ROUTES` and `FISH_AUDIO_VOICES`; grep cwtts logs for the `Generating mark` lines to see which engine+voice was actually used).

   For bulk verification across many chapters, the `tiny` model is enough — language ID doesn't need a big model and runs in ~1s per clip on CPU.

5. **Translations content (`translations.json`)** — one entry per source mark, each with a `translationResults` array of 8 entries (one per OTHER language).
   - **Non-empty text**: every target has a non-blank `text` field.
   - **Looks translated**: no raw English leaking into CJK variants (except proper nouns), no `\uXXXX` escapes or HTML entities, no placeholder strings.
   - **Glossary compliance**: key terms (character names, places, concepts) match the publication README's glossary across all chapters.

6. **Alignments / tokens** (inside each `translationResults` entry)
   - **EU → EU pairs** (e.g. EN→FR, DE→IT): `tokenAlignments` is a non-empty list of `{sourceStart, sourceEnd, targetStart, targetEnd}` per word pair. Isolated empty lists are tolerated (awesome-align can fail per-mark); a chapter where most EU targets are empty is suspicious — grep the logs for `awesome-align failed`.
   - **Any pair involving CJK** (EN→ZH, ZH→KO, etc.): `tokenAlignments` is `[]` on purpose. Instead, `tokens` is populated — a list of `{text: "..."}` entries representing the CJK segmentation. Check:
     - `tokens` list is non-empty.
     - Tokens are sensible units, not one big blob. For ZH, expect jieba-style word segmentation (multi-char words + single chars). For JA, expect fugashi tokens (mix of kanji compounds + kana). For KO, expect kiwipiepy tokens (eojeol-like spans).
     - Concatenating all `tokens[].text` in order should reconstruct the target text (modulo whitespace).

7. **Mark timings (`marks_in_milliseconds.json`)**
   - Every mark UUID from `marks.json` appears as a key.
   - Values are strictly monotonically increasing (mark N's start < mark N+1's start).
   - No wild outliers (e.g. a 2-second mark next to a 30-second one with the same word count suggests a TTS anomaly worth a listen).

8. **Cross-chapter consistency** (compare against other chapters in the same publication)
   - A recurring character/place is translated the same way chapter-to-chapter. If chapter 1's DE calls the protagonist "Winston" and chapter 5 calls him "Wilhelm", one is wrong — fix per the README glossary.
   - Title-numbering scheme (`NNNN -`) is uniform across all chapters in the publication.

### Red flags (reject + retry)

- Any `translationResults` missing a target language.
- CJK variant with empty `tokens`.
- English leaked into a CJK title or body mark (except proper nouns / trademarks).
- Translation text full of `\uXXXX` escapes, HTML entities, or a placeholder like `[en] fake`.
- Non-monotonic or inverted timings in `marks_in_milliseconds.json`.
- Coverage-warning logs for the run: grep `awesome-align failed for mark` in Loki; one or two per chapter is fine, most marks failing means the source text is bad (too short / punctuation-heavy).
