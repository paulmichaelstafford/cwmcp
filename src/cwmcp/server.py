# src/cwmcp/server.py
import asyncio
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from mcp.server.fastmcp import FastMCP

from cwmcp.config import load_config
from cwmcp.lib.cwbe_client import CwbeClient
from cwmcp.tools.list_books import find_books as _find_books
from cwmcp.tools.chapter_status import get_chapter_status
from cwmcp.tools.check_coverage import check_translations_coverage
from cwmcp.tools.align_text import align_text_pair
from cwmcp.tools.build_translations import build_chapter_translations
from cwmcp.tools.upload import upload_single, upload_chapter_batch
from cwmcp.tools.generate_audio import generate_single, generate_batch
from cwmcp.tools.download_chapters import download_publication_chapters


def _setup_logging() -> None:
    level = os.environ.get("CWMCP_LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    ))
    root = logging.getLogger("cwmcp")
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)
    root.propagate = False


_setup_logging()
log = logging.getLogger("cwmcp.server")


def _boost_default_executor() -> None:
    """Bump the asyncio default thread-pool for any residual blocking work
    (file I/O, tests). Network I/O is httpx-async so shouldn't hit this pool."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.set_default_executor(ThreadPoolExecutor(max_workers=32, thread_name_prefix="cwmcp"))


def _log_call(name: str):
    """Decorator: log tool entry + duration + outcome to stderr. Catches
    exceptions and returns a JSON error string so the stdio transport never
    sees an uncaught exception (which can race with MCP-client aborts and
    tear down the whole connection)."""
    def wrap(fn):
        import functools
        import inspect
        import time as _t

        def _error_json(exc: BaseException) -> str:
            return json.dumps({
                "status": "error",
                "error_type": type(exc).__name__,
                "message": str(exc),
            })

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def awrapper(*args, **kwargs):
                start = _t.time()
                log.info("call %s args=%s", name, {k: v for k, v in kwargs.items() if k != "overrides"})
                try:
                    result = await fn(*args, **kwargs)
                    log.info("done %s in %.1fs", name, _t.time() - start)
                    return result
                except asyncio.CancelledError:
                    log.warning("cancelled %s after %.1fs", name, _t.time() - start)
                    raise
                except Exception as e:
                    log.exception("error %s after %.1fs: %s", name, _t.time() - start, e)
                    return _error_json(e)
            return awrapper

        @functools.wraps(fn)
        def swrapper(*args, **kwargs):
            start = _t.time()
            log.info("call %s args=%s", name, kwargs)
            try:
                result = fn(*args, **kwargs)
                log.info("done %s in %.1fs", name, _t.time() - start)
                return result
            except Exception as e:
                log.exception("error %s after %.1fs: %s", name, _t.time() - start, e)
                return _error_json(e)
        return swrapper
    return wrap


mcp = FastMCP("cwmcp", instructions="CollapsingWave audiobook pipeline tools")

_config = None
_client: CwbeClient | None = None


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
@_log_call("list_books")
def list_books() -> str:
    """List all books in the content directory with their publication IDs."""
    config = get_config()
    books = _find_books(config.content_path)
    return json.dumps(books, indent=2)


@mcp.tool()
@_log_call("chapter_status")
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
@_log_call("check_coverage")
def check_coverage(translations_path: str) -> str:
    """Check alignment coverage for a translations.json file.
    Reports per-mark, per-language coverage with pass/fail status.

    Args:
        translations_path: Absolute path to translations.json
    """
    report = check_translations_coverage(translations_path)
    return json.dumps(report, indent=2)


@mcp.tool()
@_log_call("align_text")
async def align_text(source_lang: str, source_text: str, target_lang: str, target_text: str) -> str:
    """Call awesome-align on a source/target text pair.
    Returns alignments with coverage percentages and pass/fail status.

    Args:
        source_lang: Source language code (e.g. "EN")
        source_text: Source text
        target_lang: Target language code (e.g. "JA")
        target_text: Target translation text
    """
    client = get_client()
    result = await align_text_pair(client, source_lang, source_text, target_lang, target_text)
    return json.dumps(result, indent=2)


@mcp.tool()
@_log_call("build_translations")
async def build_translations(book: str, chapter_number: int, level: str, overrides: str | dict | None = None, target_lang: str | None = None, source_lang: str = "EN") -> str:
    """Build translations.json for a chapter using Azure Translate + awesome-align.
    Optionally accepts manual overrides for marks that fail coverage.

    Args:
        book: Book directory name (e.g. "everyday-life")
        chapter_number: Chapter number (e.g. 7)
        level: "b1" or "b2"
        overrides: Optional JSON string with manual overrides
        target_lang: Optional single target language (e.g. "DE")
        source_lang: Source language code (default "EN")
    """
    config = get_config()
    client = get_client()
    if overrides is None:
        override_data = None
    elif isinstance(overrides, str):
        override_data = json.loads(overrides)
    else:
        override_data = overrides
    result = await build_chapter_translations(
        client, config.content_path, book, chapter_number, level, override_data,
        target_lang=target_lang, source_lang=source_lang,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
@_log_call("upload_chapter")
async def upload_chapter(book: str, chapter_number: int, lang: str, level: str) -> str:
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
    result = await upload_single(client, config.content_path, book, chapter_number, lang, level)
    return json.dumps(result, indent=2)


@mcp.tool()
@_log_call("upload_batch")
async def upload_batch(book: str, chapter_number: int, workers: int = 3) -> str:
    """Upload all ready lang/level combos for a chapter.

    Args:
        book: Book directory name (e.g. "everyday-life")
        chapter_number: Chapter number (e.g. 7)
        workers: Max concurrent uploads (default 3, max 3)
    """
    config = get_config()
    client = get_client()
    workers = min(workers, 3)
    result = await upload_chapter_batch(client, config.content_path, book, chapter_number, workers)
    return json.dumps(result, indent=2)


@mcp.tool()
@_log_call("generate_audio")
async def generate_audio(book: str, chapter_number: int, lang: str, level: str) -> str:
    """Generate audio for a single lang/level combo.

    Args:
        book: Book directory name (e.g. "everyday-life")
        chapter_number: Chapter number (e.g. 7)
        lang: Language code (e.g. "EN", "FR", "JA")
        level: "B1" or "B2"
    """
    config = get_config()
    client = get_client()
    result = await generate_single(
        config.content_path, book, chapter_number, lang, level,
        cwbe_client=client,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
@_log_call("generate_audio_batch")
async def generate_audio_batch(book: str, chapter_number: int) -> str:
    """Generate audio for all lang/level combos that have chapter.md but no audio.mp3.

    Args:
        book: Book directory name (e.g. "everyday-life")
        chapter_number: Chapter number (e.g. 7)
    """
    config = get_config()
    client = get_client()
    results = await generate_batch(
        config.content_path, book, chapter_number,
        cwbe_client=client,
    )
    return json.dumps(results, indent=2)


@mcp.tool()
@_log_call("download_chapters")
async def download_chapters(publication_id: str, output_dir: str) -> str:
    """Download all chapters for a publication to a local directory.

    Args:
        publication_id: Publication UUID from cwbe
        output_dir: Local directory to save files to
    """
    client = get_client()
    result = await download_publication_chapters(client, publication_id, output_dir)
    return json.dumps(result, indent=2)


@mcp.tool()
@_log_call("list_publications")
async def list_publications() -> str:
    """List all publications from cwbe with their IDs, titles, and types."""
    client = get_client()
    pubs = await client.get_publications()
    summary = [
        {"id": p["id"], "title": p["title"], "type": p["publicationType"], "isComplete": p.get("isComplete", False)}
        for p in pubs
    ]
    return json.dumps(summary, indent=2)


@mcp.tool()
@_log_call("list_uploaded_chapters")
async def list_uploaded_chapters(publication_id: str) -> str:
    """List all chapters uploaded to cwbe for a publication.

    Args:
        publication_id: Publication UUID
    """
    client = get_client()
    chapters = await client.get_all_chapters(publication_id)
    summary = [
        {"id": c["id"], "title": c.get("title", ""), "language": c.get("language", ""), "level": c.get("level", "")}
        for c in chapters
    ]
    return json.dumps({"total": len(chapters), "chapters": summary}, indent=2)


@mcp.tool()
@_log_call("get_publication_readme")
async def get_publication_readme(publication_id: str) -> str:
    """Get the readme for a publication from cwbe.

    Args:
        publication_id: Publication UUID
    """
    client = get_client()
    pubs = await client.get_publications()
    pub = next((p for p in pubs if p["id"] == publication_id), None)
    if not pub:
        return json.dumps({"error": f"Publication {publication_id} not found"})
    return pub.get("readme", "")


@mcp.tool()
@_log_call("update_publication_readme")
async def update_publication_readme(publication_id: str, readme: str) -> str:
    """Update the readme for a publication on cwbe.

    Args:
        publication_id: Publication UUID
        readme: Full markdown content to replace the existing readme
    """
    client = get_client()
    result = await client.update_publication_readme(publication_id, readme)
    return json.dumps({"ok": True, "id": result.get("storedDataId", publication_id)})


@mcp.tool()
@_log_call("update_chapter_metadata")
async def update_chapter_metadata(publication_id: str, chapter_id: str, title: str,
                                   language: str, level: str) -> str:
    """Update chapter metadata (title, language, level) without re-uploading audio.

    Args:
        publication_id: Publication UUID
        chapter_id: Chapter UUID
        title: New chapter title
        language: Language code (e.g. "EN", "FR", "JA")
        level: "B1" or "B2"
    """
    client = get_client()
    result = await client.update_chapter_metadata(
        publication_id, chapter_id, title, language.upper(), level.upper(),
    )
    return json.dumps({"ok": True, "job_id": result.get("id", "")})


if __name__ == "__main__":
    _boost_default_executor()
    log.info("cwmcp starting")
    try:
        mcp.run(transport="stdio")
    finally:
        log.info("cwmcp shutting down")
