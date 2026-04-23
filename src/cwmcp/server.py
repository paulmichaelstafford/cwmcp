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
from cwmcp.tools.chapter_status import get_chapter_status
from cwmcp.tools.chapters import delete_chapter as _delete_chapter
from cwmcp.tools.create_chapter import create_chapter_from_marks as _create_chapter_from_marks
from cwmcp.tools.download_chapters import download_publication_chapters
from cwmcp.tools.list_books import find_books as _find_books
from cwmcp.tools.publications import (
    create_publication as _create_publication,
    delete_publication as _delete_publication,
    update_publication_flags as _update_publication_flags,
    update_publication_readme as _update_publication_readme,
    update_publication_titles as _update_publication_titles,
)
from cwmcp.tools.query_logs import query_logs as _query_logs
from cwmcp.tools.upload_chapter_from_zip import upload_chapter_from_zip as _upload_chapter_from_zip


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
@_log_call("create_chapter_from_marks")
async def create_chapter_from_marks(
    publication_id: str,
    title: str,
    language: str,
    level: str,
    marks: list[str],
    source_audio_blob_name: str | None = None,
) -> str:
    """Create one chapter variant (single language+level) via cwbe's
    `/chapters/from-marks` pipeline: cwtts → Gemini translate → awesome-align
    → cwseg tokens → ingest. Polls the resulting Job until terminal. To build
    all 9 language variants of the same chapter, call this once per source
    language — **max 2 concurrent calls per the cwbe CPU budget**.

    Returns JSON with `status` ("COMPLETED" | "FAILED" | "CANCELLED" |
    "TIMEOUT"), `job_id`, `message`, and — on success — `chapter_id`. On
    failure the `message` includes `sourceAudioBlobName=...` scraped from
    cwbe logs; pass that back to retry without regenerating audio.

    If a chapter with the same (publication, language, level, title) already
    exists, cwbe returns that chapter's UUID immediately — safe to retry.

    Args:
        publication_id: Publication UUID on cwbe.
        title: Localized chapter title (e.g. "0005 - Les plans").
        language: Source language code (EN | FR | ES | DE | IT | PT | ZH | JA | KO).
        level: Difficulty (B1 | B2).
        marks: Pre-split sentence list in the source language. No blanks.
        source_audio_blob_name: Optional retry hint — skip phase 0 (TTS) by
            reusing a cached audio bundle from a previous failed run. Scrape
            from cwbe logs after a failure.
    """
    client = get_client()
    result = await _create_chapter_from_marks(
        client=client,
        publication_id=publication_id,
        title=title,
        language=language,
        level=level,
        marks=marks,
        source_audio_blob_name=source_audio_blob_name,
    )
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Break-glass lego blocks. Thin passthroughs to individual cwbe service
# endpoints. Use these to assemble a chapter manually when
# create_chapter_from_marks isn't right — e.g., patching a single mark's
# translation or alignment and uploading via upload_chapter_from_zip.
# ---------------------------------------------------------------------------


@mcp.tool()
@_log_call("generate_audio")
async def generate_audio(language: str, marks: list[str]) -> str:
    """Break-glass: call cwtts directly to generate audio for a single
    lang/level. Returns base64 MP3 + per-mark UUIDs + millisecond timings.
    Normal chapter creation should go through `create_chapter_from_marks`
    which invokes cwtts internally.

    Args:
        language: Source language code (EN | FR | ES | DE | IT | PT | ZH | JA | KO).
        marks: Pre-split sentence list in that language.
    """
    result = await get_client().generate_audio(language.upper(), marks)
    return json.dumps(result, indent=2)


@mcp.tool()
@_log_call("translate_texts")
async def translate_texts(source_language: str, texts: list[str]) -> str:
    """Break-glass: translate a list of texts from one source language to
    all 8 other langs via Gemini. Returns `{lang: [texts]}`. Parallel to
    phase 1 of `/from-marks`."""
    result = await get_client().translate_texts(source_language.upper(), texts)
    return json.dumps(result, indent=2)


@mcp.tool()
@_log_call("align")
async def align(source_language: str, source_text: str, targets: dict[str, str]) -> str:
    """Break-glass: call awesome-align for EU↔EU token-alignment between
    one source sentence and its per-target translations. `targets` is
    `{lang: translated_text}`. CJK targets are not aligned — cwseg handles
    those during ingest.

    Args:
        source_language: Source lang code (must be EU: EN/FR/ES/DE/IT/PT).
        source_text: Source sentence.
        targets: `{lang: text}` for each EU target you want aligned.
    """
    result = await get_client().align(source_language.upper(), source_text, {k.upper(): v for k, v in targets.items()})
    return json.dumps(result, indent=2)


@mcp.tool()
@_log_call("gloss_tokens")
async def gloss_tokens(
    source_language: str,
    sentence_text: str,
    sentence_translations: dict[str, str],
    tokens: list[str],
) -> str:
    """Break-glass: ask Gemini for per-token offline glosses, given one CJK
    sentence + its sentence-level translations + the cwseg token list.
    Returns a list of `{lang: gloss}` — one entry per input token in the
    same order. This is what cwbe runs during ingest to populate offline
    tap-for-translation for CJK chapters.

    Args:
        source_language: Source lang code (typically CJK: ZH / JA / KO).
        sentence_text: The CJK sentence containing the tokens.
        sentence_translations: Sentence-level translations, e.g.
            `{"EN": "...", "FR": "..."}` — richer context = better glosses.
        tokens: List of token strings (substrings of sentence_text).
    """
    result = await get_client().gloss_tokens(
        source_language.upper(),
        sentence_text,
        {k.upper(): v for k, v in sentence_translations.items()},
        tokens,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
@_log_call("upload_chapter_from_zip")
async def upload_chapter_from_zip(
    publication_id: str,
    audio_path: str,
    marks_path: str,
    marks_in_ms_path: str,
    translations_path: str,
    title: str,
    language: str,
    level: str,
    chapter_id: str | None = None,
) -> str:
    """Break-glass: POST (or PUT if `chapter_id` given) a manually-assembled
    chapter zip via `/chapters/from-audio`. Use this only when
    `create_chapter_from_marks` isn't right — e.g., you have hand-patched
    translations + alignments locally and need to push the exact bytes.

    Args:
        publication_id: Publication UUID.
        audio_path: Absolute path to `audio.mp3`.
        marks_path: Absolute path to `marks.json`.
        marks_in_ms_path: Absolute path to `marks_in_milliseconds.json`.
        translations_path: Absolute path to `translations.json`.
        title: Localized chapter title (e.g. "0005 - Les plans").
        language: Source lang code.
        level: B1 | B2.
        chapter_id: Optional — if given, PUTs (updates) instead of POSTs.
    """
    result = await _upload_chapter_from_zip(
        get_client(),
        publication_id=publication_id,
        audio_path=audio_path,
        marks_path=marks_path,
        marks_in_ms_path=marks_in_ms_path,
        translations_path=translations_path,
        title=title,
        language=language,
        level=level,
        chapter_id=chapter_id,
    )
    return json.dumps(result, indent=2)


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
    """Replace a publication's readme markdown. Partial update — all other
    fields (title, headers, descriptions, flags) are preserved."""
    result = await _update_publication_readme(get_client(), publication_id, readme)
    return json.dumps(result, indent=2)


@mcp.tool()
@_log_call("update_publication_titles")
async def update_publication_titles(
    publication_id: str,
    title: str | None = None,
    headers: dict[str, str] | None = None,
    descriptions: dict[str, str] | None = None,
) -> str:
    """Partial update of the publication title and/or per-language headers
    and descriptions. `headers` and `descriptions` are merged — pass only
    the languages you want to change; omitted langs keep their current
    value. Omit all three args for a no-op."""
    result = await _update_publication_titles(
        get_client(), publication_id, title=title, headers=headers, descriptions=descriptions,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
@_log_call("update_publication_flags")
async def update_publication_flags(
    publication_id: str,
    is_complete: bool | None = None,
    archived: bool | None = None,
) -> str:
    """Partial update of the publication isComplete / archived flags."""
    result = await _update_publication_flags(
        get_client(), publication_id, is_complete=is_complete, archived=archived,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
@_log_call("create_publication")
async def create_publication(
    title: str,
    publication_type: str,
    copyright_terms: list[str],
    headers: dict[str, str],
    descriptions: dict[str, str],
    readme: str,
    cover_path: str,
    archived: bool = False,
    is_complete: bool = False,
) -> str:
    """Create a new publication on cwbe. All 9 langs are required in both
    `headers` and `descriptions`. `cover_path` is an absolute local path to
    a JPEG cover image (required by cwbe).

    Args:
        title: Canonical title (e.g. "The Iliad").
        publication_type: "ONETIME_UPLOAD" | "CONTINUOUS_UPLOADS".
        copyright_terms: List of terms (e.g. ["PUBLICATION_PLUS_95",
            "LIFE_PLUS_70", "UNKNOWN", "LIFE_PLUS_100"]).
        headers: Per-lang display title, ALL 9 langs required.
        descriptions: Per-lang summary, ALL 9 langs required.
        readme: Authoring README markdown (style guide, glossary, etc.).
        cover_path: Absolute path to cover JPEG.
        archived: Default False.
        is_complete: Default False.
    """
    result = await _create_publication(
        get_client(),
        title=title,
        publication_type=publication_type,
        copyright_terms=copyright_terms,
        headers=headers,
        descriptions=descriptions,
        readme=readme,
        cover_path=cover_path,
        archived=archived,
        is_complete=is_complete,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
@_log_call("delete_publication")
async def delete_publication(publication_id: str, confirm: bool = False) -> str:
    """Delete a publication and EVERY chapter + blob it owns. Irreversible.
    Requires explicit `confirm=True`; any other value returns a refusal."""
    result = await _delete_publication(get_client(), publication_id, confirm=confirm)
    return json.dumps(result, indent=2)


@mcp.tool()
@_log_call("delete_chapter")
async def delete_chapter(
    publication_id: str, chapter_id: str, confirm: bool = False,
) -> str:
    """Delete a single chapter variant and its blob. Irreversible.
    Requires explicit `confirm=True`; any other value returns a refusal."""
    result = await _delete_chapter(
        get_client(), publication_id, chapter_id, confirm=confirm,
    )
    return json.dumps(result, indent=2)


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


@mcp.tool()
@_log_call("query_logs")
def query_logs(
    job_id: str | None = None,
    filter_text: str | None = None,
    logql: str | None = None,
    minutes_back: int = 30,
    limit: int = 500,
) -> str:
    """Query Grafana Loki for cwbe logs. Primary use: scrape
    `sourceAudioBlobName` and `translationsBlobName` from a failed
    `/chapters/from-marks` job for retry, or follow a job's progress
    across phases.

    Exactly one of `job_id`, `filter_text`, or `logql` should be given
    (in that precedence). If none, returns all recent cwbe lines (noisy).

    Args:
        job_id: Filter to lines containing this cwbe job UUID.
        filter_text: Filter to lines containing this literal substring
            (e.g. "from-marks", "blob=", "Google Translate raw response").
        logql: Raw LogQL string, used verbatim. Caller handles escaping.
        minutes_back: Time window in minutes (default 30).
        limit: Max lines returned (default 500, newest-first).

    Returns JSON `{"count": N, "entries": [{"timestamp": "<ns>", "line": "..."}]}`.
    Requires `grafana_user` and `grafana_password` in `~/.cwmcp/config.properties`.
    """
    config = get_config()
    entries = _query_logs(
        grafana_url=config.grafana_url,
        grafana_user=config.grafana_user,
        grafana_password=config.grafana_password,
        job_id=job_id,
        filter_text=filter_text,
        logql=logql,
        minutes_back=minutes_back,
        limit=limit,
    )
    return json.dumps({"count": len(entries), "entries": entries}, indent=2)


if __name__ == "__main__":
    _boost_default_executor()
    log.info("cwmcp starting")
    try:
        mcp.run(transport="stdio")
    finally:
        log.info("cwmcp shutting down")
