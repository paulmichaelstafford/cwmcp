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

Copy the example config and fill in your credentials:

```bash
mkdir -p ~/.cwmcp
cp config.example.properties ~/.cwmcp/config.properties
```

Edit `~/.cwmcp/config.properties`:

```properties
cwbe_user=your-email@example.com
cwbe_password=your-password
content_path=/path/to/your/audio/content
```

- `cwbe_user` / `cwbe_password`: Your cwbe service account credentials
- `content_path`: Path to directory containing `onetime/` and `continuous/` book folders

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

| Tool | Description |
|------|-------------|
| `list_books` | List all books with publication IDs |
| `chapter_status` | Check what files exist locally for a chapter |
| `check_coverage` | Report alignment coverage for a translations.json |
| `align_text` | Test awesome-align on a single text pair |
| `build_translations` | Build translations.json using Azure Translate + awesome-align |
| `upload_chapter` | Upload a single lang/level combo |
| `upload_batch` | Upload all ready combos for a chapter |

## Content Directory Layout

The `content_path` should contain:

```
content_path/
├── onetime/
│   └── book-name/
│       ├── README.md          # Must contain: **Publication ID (cwbe):** <uuid>
│       └── chapter-NNNN-slug/
│           └── en/b1/
│               ├── chapter.md
│               ├── audio.mp3
│               ├── marks.json
│               ├── marks_in_milliseconds.json
│               └── translations.json
└── continuous/
    └── book-name/
        └── ...
```

## License

Apache 2.0
