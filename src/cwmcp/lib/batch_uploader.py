# src/cwmcp/lib/batch_uploader.py
import os
import json
import concurrent.futures
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


def upload_batch(
    client: CwbeClient,
    chapter_base: str,
    publication_id: str,
    workers: int = 3,
) -> list[dict]:
    """Upload all ready lang/level combos for a chapter.
    Returns list of {lang, level, status, message}.
    """
    combos = [(lang, level) for lang in ALL_LANGS for level in ALL_LEVELS]
    ready = [(lang, level) for lang, level in combos if is_ready(chapter_base, lang, level)]

    if not ready:
        return [{"lang": "-", "level": "-", "status": "SKIPPED", "message": "Nothing ready to upload"}]

    results = []

    def do_upload(lang: str, level: str) -> dict:
        chapter_dir = os.path.join(chapter_base, lang, level)
        result = upload_chapter(client, chapter_dir, publication_id, lang.upper(), level.upper())
        return {"lang": lang.upper(), "level": level.upper(), **result}

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(do_upload, lang, level): (lang, level) for lang, level in ready}
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    return results
