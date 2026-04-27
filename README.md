# cwmcp — CollapsingWave MCP Server

MCP server that exposes audiobook pipeline tools for the [CollapsingWave](https://collapsingwave.com) platform. Designed for use with Claude Code.

## Setup

### 1. Install

```bash
git clone <repo-url>
cd cwmcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Configure

Run the setup script to create your config:

```bash
./setup.sh
```

This prompts for your cwbe credentials and content path, then writes `~/.cwmcp/config.properties`.

Alternatively, copy and edit the example config manually:

```bash
mkdir -p ~/.cwmcp
cp config.example.properties ~/.cwmcp/config.properties
```

- `cwbe_user` / `cwbe_password`: cwbe service account credentials.
- `content_path`: Path to directory containing `onetime/` and `continuous/` book folders.
- `grafana_user` / `grafana_password` (optional): Grafana Viewer credentials, used only by `query_logs` to debug failed `/from-marks` jobs.

### 3. Register with Claude Code

Add to your Claude Code MCP settings:

```json
{
  "mcpServers": {
    "cwmcp": {
      "command": "/path/to/cwmcp/.venv/bin/python3",
      "args": ["/path/to/cwmcp/src/cwmcp/server.py"]
    }
  }
}
```

## Tools

The default chapter-creation path is `validate_marks` followed by `create_chapter_from_marks`. Everything else is read-only diagnostics or break-glass.

**Default path:**
- `validate_marks(language, level, marks)` — dry-run the Gemini pipeline (no TTS / no DB writes); returns all validation issues at once and warms cwbe's Gemini cache.
- `create_chapter_from_marks(publication_id, title, language, level, marks, source_audio_blob_name=None)` — full ingest: TTS → Gemini translate → awesome-align → cwseg tokens → persist. Polls the resulting Job until terminal.
- `chapter_release_sanity_check(publication_id, title_prefix)` — run after every chapter release; downloads all 18 variants matching the prefix (e.g. `"0005 - "`) and verifies structural integrity. Returns `ok: true` only when every variant passes.

**Read cwbe:** `list_publications`, `list_uploaded_chapters`, `get_publication_readme`, `download_chapters`.

**Publication CRUD:** `create_publication`, `update_publication_readme`, `update_publication_titles`, `update_publication_flags`, `delete_publication`.

**Chapter CRUD:** `update_chapter_metadata`, `delete_chapter`.

**Break-glass lego blocks** (one-call wrappers around individual cwbe service endpoints; use to assemble a chapter manually): `generate_audio`, `translate_texts`, `align`, `gloss_tokens`, `upload_chapter_from_zip`.

**Local content navigation:** `list_books`, `chapter_status`.

**Diagnostics:** `query_logs` (Grafana Loki), `gemini_cache_stats`, `clear_gemini_cache`.

For full descriptions and the exact response shapes, see `CLAUDE.md` and the cwbe Swagger UI at `https://be.collapsingwave.com/api/open/swagger-ui.html`.

## Content Directory Layout

The `content_path` should contain `onetime/` and/or `continuous/` book folders. Each book folder needs a `README.md` (or similar) whose first heading section contains `**Publication ID (cwbe):** <uuid>` so cwmcp can map the local folder to its cwbe publication. Per-chapter content lives under `chapter-NNNN-slug/<lang>/<level>/chapter.md`. cwbe owns audio, marks, translations and alignments — those don't need to exist locally for the default `/from-marks` path.

## License

Apache 2.0
