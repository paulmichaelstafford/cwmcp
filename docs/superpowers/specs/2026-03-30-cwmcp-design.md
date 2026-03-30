# cwmcp — CollapsingWave MCP Server

## Overview

A Python MCP server that exposes audiobook pipeline tools to Claude Code. It handles translation building, alignment checking, coverage validation, and chapter uploads for the CollapsingWave audiobook platform.

The server reads chapter content from a configurable local directory, credentials from a local config file, and calls the cwbe API for translations, alignment, and uploads.

## Problem

Every conversation about audiobook pipeline work requires:
- Re-reading CLAUDE.md and pipeline docs to remember how scripts work
- Exploring file structure to determine chapter status
- Constructing bash commands with correct flags and paths
- Parsing unstructured terminal output
- Repeating all of this next conversation

With dozens of chapters queued across multiple books, this overhead compounds significantly.

## Solution

An MCP server that exposes structured tools for each pipeline step. Claude Code calls these directly — no doc reading, no bash guessing, structured responses.

## Architecture

```
Claude Code <-- stdin/stdout --> cwmcp (Python MCP server)
                                  |-- reads ~/.cwmcp/config.properties
                                  |-- calls cwbe API (hardcoded: https://be.collapsingwave.com)
                                  |-- reads/writes chapter files from content_path
```

Single Python process using the `mcp` Python SDK. Communicates over stdin/stdout per MCP protocol.

### Credentials

Stored in `~/.cwmcp/config.properties` (never committed):

```properties
cwbe_user=your-email@example.com
cwbe_password=your-password
content_path=/path/to/your/audio/content
```

- `cwbe_user` and `cwbe_password`: required, cwbe service account credentials
- `content_path`: required, path to directory containing `onetime/` and `continuous/` book folders
- cwbe URL is hardcoded to `https://be.collapsingwave.com`

A `config.example.properties` ships in the repo as a template.

## Project Structure

```
cwmcp/
├── LICENSE                          # Apache 2.0
├── README.md                        # Setup + usage docs
├── CLAUDE.md                        # Instructions for Claude
├── config.example.properties        # Template config (no real creds)
├── pyproject.toml                   # Python project config
├── src/
│   ├── server.py                    # MCP server entry point, tool registration
│   ├── config.py                    # Reads ~/.cwmcp/config.properties
│   ├── tools/
│   │   ├── list_books.py            # List books + publication IDs
│   │   ├── chapter_status.py        # What exists locally vs server
│   │   ├── check_coverage.py        # Coverage report for translations.json
│   │   ├── align_text.py            # Standalone awesome-align call
│   │   ├── build_translations.py    # Auto builder with optional overrides
│   │   ├── upload_chapter.py        # Single chapter upload
│   │   └── upload_batch.py          # Batch upload all ready combos
│   └── lib/
│       ├── translations_auto.py     # Refactored from cwaudio build_translations_auto.py
│       ├── translations_helper.py   # Refactored from cwaudio translations_helper.py
│       ├── uploader.py              # Refactored from cwaudio upload_chapter.py
│       └── batch_uploader.py        # Refactored from cwaudio upload_batch.py
```

- `src/lib/` — refactored copies of cwaudio scripts. Credentials and paths passed as parameters instead of hardcoded.
- `src/tools/` — thin MCP tool wrappers that read config and call lib functions, returning structured JSON.

## Tools

### `list_books`

Lists all books found in content_path with their publication IDs.

- **Inputs:** none
- **Returns:** List of `{name, path, publication_id, type}` where type is "onetime" or "continuous"
- **How it works:** Scans `content_path/onetime/` and `content_path/continuous/` directories. Extracts publication IDs from each book's README.md.

### `chapter_status`

Reports what exists locally and what's uploaded to the server for a given chapter.

- **Inputs:** `book` (string), `chapter_number` (int)
- **Returns:** Per lang/level combo: which files exist locally (chapter.md, audio.mp3, marks.json, marks_in_milliseconds.json, translations.json), upload status on server, overall status label (`ready_to_upload`, `missing_translations`, `missing_audio`, `already_uploaded`, etc.)
- **How it works:**
  1. Finds the chapter directory by matching `chapter-{NNNN}-*` pattern
  2. For each of 18 lang/level combos, checks file existence
  3. Calls cwbe API to check which chapters are already uploaded for that publication
  4. Returns structured comparison of local vs server state

### `check_coverage`

Reports alignment coverage for an existing translations.json.

- **Inputs:** `translations_path` (string, path to translations.json)
- **Returns:** Per mark per target language: source coverage %, target coverage %, threshold, pass/fail
- **How it works:** Reads translations.json, computes coverage using the same logic as cwbe validation (alphanumeric character coverage). Reports which marks/languages are below threshold (70% European, 40% CJK).

### `align_text`

Calls the awesome-align endpoint for a specific source/target pair.

- **Inputs:** `source_lang` (string), `source_text` (string), `target_lang` (string), `target_text` (string)
- **Returns:** Token alignments, source coverage %, target coverage %, pass/fail
- **How it works:** Calls `POST /api/service/align` on cwbe with the given text pair. Computes coverage on the result. Useful for testing individual translations before committing.

### `build_translations`

Runs the auto translation builder for a chapter.

- **Inputs:** `book` (string), `chapter_number` (int), `level` (string, "b1" or "b2"), `overrides` (optional, JSON object with manual override data for failing marks)
- **Returns:** Success/failure, list of warnings (coverage failures), list of errors, output path
- **How it works:** Finds marks.json for the given chapter/level, calls Azure Translate for all target languages, calls awesome-align for alignments, applies manual overrides if provided, validates coverage, writes translations.json.

### `upload_chapter`

Uploads a single lang/level combo to cwbe.

- **Inputs:** `book` (string), `chapter_number` (int), `lang` (string), `level` (string)
- **Returns:** Job ID, status (COMPLETED/FAILED), error message if failed
- **How it works:** Reads audio.mp3, marks.json, marks_in_milliseconds.json, translations.json from the chapter directory. Validates translations locally. POSTs to cwbe, waits for job completion.

### `upload_batch`

Uploads all ready combos for a chapter.

- **Inputs:** `book` (string), `chapter_number` (int), `workers` (optional int, default 3)
- **Returns:** Per combo: success/failure/skipped, summary counts
- **How it works:** Scans all 18 lang/level combos, identifies which are ready (have all required files), uploads them with configurable concurrency. Max 3 workers to avoid overloading cwbe.

## Content Directory Layout

The MCP expects this structure under `content_path`:

```
content_path/
├── onetime/
│   ├── 1984/
│   │   ├── README.md              # Contains publication ID
│   │   ├── glossary.md            # Optional
│   │   └── chapter-0001-slug/
│   │       └── en/
│   │           └── b1/
│   │               ├── chapter.md
│   │               ├── audio.mp3
│   │               ├── marks.json
│   │               ├── marks_in_milliseconds.json
│   │               └── translations.json
│   └── ...
└── continuous/
    ├── everyday-life/
    └── ...
```

## Dependencies

- `mcp` — Python MCP SDK (stdin/stdout transport)
- `requests` — HTTP calls to cwbe API

No ElevenLabs SDK, no ML libraries. Lightweight.

## Registration

Users add to their Claude Code MCP settings:

```json
{
  "mcpServers": {
    "cwmcp": {
      "command": "python3",
      "args": ["/path/to/cwmcp/src/server.py"]
    }
  }
}
```

## Out of Scope

- Audio generation (requires ElevenLabs credentials + SDK)
- Chapter text writing (creative work, stays in conversation)
- Cover generation
- Chapter downloading
