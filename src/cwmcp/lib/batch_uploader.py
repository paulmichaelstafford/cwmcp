# src/cwmcp/lib/batch_uploader.py
import asyncio
import json
import os
import re

from cwmcp.lib.cwbe_client import CwbeClient
from cwmcp.lib.uploader import upload_chapter

ALL_LANGS = ["en", "fr", "es", "de", "it", "pt", "zh", "ja", "ko"]
ALL_LEVELS = ["b1", "b2"]


def is_ready(chapter_base: str, lang: str, level: str) -> bool:
    """Check if a lang/level combo has all files needed for upload."""
    base = os.path.join(chapter_base, lang, level)
    required = ["audio.mp3", "marks.json", "marks_in_milliseconds.json", "translations.json", "chapter.md"]
    if not all(os.path.exists(os.path.join(base, f)) for f in required):
        return False
    marks_path = os.path.join(base, "marks.json")
    trans_path = os.path.join(base, "translations.json")
    with open(marks_path) as f:
        mc = len(json.load(f))
    with open(trans_path) as f:
        tc = len(json.load(f))
    return mc == tc


async def _build_existing_chapter_map(
    client: CwbeClient, publication_id: str, title_prefix: str,
) -> dict[tuple[str, str], str]:
    chapters = await client.get_all_chapters(publication_id)
    result: dict[tuple[str, str], str] = {}
    for ch in chapters:
        if ch.get("title", "").startswith(title_prefix):
            key = (ch["language"], ch["level"])
            if key not in result:
                result[key] = ch["id"]
    return result


async def upload_batch(
    client: CwbeClient,
    chapter_base: str,
    publication_id: str,
    workers: int = 3,
) -> list[dict]:
    """Upload all ready lang/level combos for a chapter. Limits concurrency to `workers`."""
    combos = [(lang, level) for lang in ALL_LANGS for level in ALL_LEVELS]
    ready = [(lang, level) for lang, level in combos if is_ready(chapter_base, lang, level)]

    if not ready:
        return [{"lang": "-", "level": "-", "status": "SKIPPED", "message": "Nothing ready to upload"}]

    chapter_num_match = re.search(r"(?:chapter|episode)-(\d+)", chapter_base)
    title_prefix = f"{int(chapter_num_match.group(1)):04d} - " if chapter_num_match else ""
    existing = await _build_existing_chapter_map(client, publication_id, title_prefix) if title_prefix else {}

    sem = asyncio.Semaphore(workers)

    async def do_upload(lang: str, level: str) -> dict:
        async with sem:
            chapter_dir = os.path.join(chapter_base, lang, level)
            chapter_id = existing.get((lang.upper(), level.upper()))
            result = await upload_chapter(
                client, chapter_dir, publication_id, lang.upper(), level.upper(), chapter_id=chapter_id,
            )
            return {"lang": lang.upper(), "level": level.upper(), **result}

    tasks = [do_upload(lang, level) for lang, level in ready]
    return await asyncio.gather(*tasks)
