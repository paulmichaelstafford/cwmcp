# src/cwmcp/server.py
import json
from mcp.server.fastmcp import FastMCP

from cwmcp.config import load_config
from cwmcp.lib.cwbe_client import CwbeClient
from cwmcp.tools.list_books import find_books as _find_books
from cwmcp.tools.chapter_status import get_chapter_status
from cwmcp.tools.check_coverage import check_translations_coverage
from cwmcp.tools.align_text import align_text_pair
from cwmcp.tools.build_translations import build_chapter_translations
from cwmcp.tools.upload import upload_single, upload_chapter_batch

mcp = FastMCP("cwmcp", instructions="CollapsingWave audiobook pipeline tools")

_config = None
_client = None


def get_config():
    global _config
    if _config is None:
        _config = load_config()
    return _config


def get_client() -> CwbeClient:
    global _client
    if _client is None:
        config = get_config()
        _client = CwbeClient(config.cwbe_user, config.cwbe_password)
    return _client


@mcp.tool()
def list_books() -> str:
    """List all books in the content directory with their publication IDs."""
    config = get_config()
    books = _find_books(config.content_path)
    return json.dumps(books, indent=2)


@mcp.tool()
def chapter_status(book: str, chapter_number: int) -> str:
    """Get the status of all lang/level combos for a chapter.
    Reports which files exist locally (chapter.md, audio, marks, translations).

    Args:
        book: Book directory name (e.g. "1984", "everyday-life")
        chapter_number: Chapter number (e.g. 7)
    """
    config = get_config()
    books = _find_books(config.content_path)
    book_info = next((b for b in books if b["name"] == book), None)
    if not book_info:
        return json.dumps({"error": f"Book '{book}' not found"})
    status = get_chapter_status(book_info["path"], chapter_number)
    return json.dumps(status, indent=2)


@mcp.tool()
def check_coverage(translations_path: str) -> str:
    """Check alignment coverage for a translations.json file.
    Reports per-mark, per-language coverage with pass/fail status.

    Args:
        translations_path: Absolute path to translations.json
    """
    report = check_translations_coverage(translations_path)
    return json.dumps(report, indent=2)


@mcp.tool()
def align_text(source_lang: str, source_text: str, target_lang: str, target_text: str) -> str:
    """Call awesome-align on a source/target text pair.
    Returns alignments with coverage percentages and pass/fail status.
    Useful for testing individual translations before committing.

    Args:
        source_lang: Source language code (e.g. "EN")
        source_text: Source text
        target_lang: Target language code (e.g. "JA")
        target_text: Target translation text
    """
    client = get_client()
    result = align_text_pair(client, source_lang, source_text, target_lang, target_text)
    return json.dumps(result, indent=2)


@mcp.tool()
def build_translations(book: str, chapter_number: int, level: str, overrides: str | None = None) -> str:
    """Build translations.json for a chapter using Azure Translate + awesome-align.
    Optionally accepts manual overrides for marks that fail coverage.

    Args:
        book: Book directory name (e.g. "everyday-life")
        chapter_number: Chapter number (e.g. 7)
        level: "b1" or "b2"
        overrides: Optional JSON string with manual overrides: {"mark_idx": {"lang": {"text": "...", "tokenAlignments": [...]}}}
    """
    config = get_config()
    client = get_client()
    override_data = json.loads(overrides) if overrides else None
    result = build_chapter_translations(
        client, config.content_path, book, chapter_number, level, override_data,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
def upload_chapter(book: str, chapter_number: int, lang: str, level: str) -> str:
    """Upload a single lang/level combo to cwbe.
    Requires audio.mp3, marks.json, marks_in_milliseconds.json, and translations.json.

    Args:
        book: Book directory name (e.g. "everyday-life")
        chapter_number: Chapter number (e.g. 7)
        lang: Language code (e.g. "EN", "FR", "JA")
        level: "B1" or "B2"
    """
    config = get_config()
    client = get_client()
    result = upload_single(client, config.content_path, book, chapter_number, lang, level)
    return json.dumps(result, indent=2)


@mcp.tool()
def upload_batch(book: str, chapter_number: int, workers: int = 3) -> str:
    """Upload all ready lang/level combos for a chapter.
    Scans all 18 combos, uploads those with all required files.

    Args:
        book: Book directory name (e.g. "everyday-life")
        chapter_number: Chapter number (e.g. 7)
        workers: Max concurrent uploads (default 3, max 3)
    """
    config = get_config()
    client = get_client()
    workers = min(workers, 3)
    result = upload_chapter_batch(client, config.content_path, book, chapter_number, workers)
    return json.dumps(result, indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")
