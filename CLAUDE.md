# CLAUDE.md — cwmcp

## What This Is

MCP server for the CollapsingWave audiobook pipeline. Exposes tools for checking chapter status, building translations, testing alignments, and uploading chapters.

## Running Tests

```bash
cd /path/to/cwmcp
PYTHONPATH=src python3 -m pytest tests/ -v
```

## Project Structure

- `src/cwmcp/server.py` — MCP entry point, all tool registrations
- `src/cwmcp/config.py` — Reads ~/.cwmcp/config.properties
- `src/cwmcp/tools/` — Tool implementations (thin wrappers)
- `src/cwmcp/lib/` — Core logic (translations, uploads, cwbe client)
- `tests/` — Unit tests

## Key Concepts

- 9 languages: EN, FR, ES, DE, IT, PT, ZH, JA, KO
- 2 levels: B1 (simple), B2 (intermediate)
- 18 combos per chapter (9 langs x 2 levels)
- Coverage thresholds: 70% European-European, 40% involving CJK
- cwbe URL is hardcoded: https://be.collapsingwave.com
