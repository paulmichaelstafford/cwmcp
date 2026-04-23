# src/cwmcp/tools/upload_chapter_from_zip.py
"""Break-glass: upload a manually-assembled chapter zip via /from-audio.
Use this only when `create_chapter_from_marks` isn't right — e.g., you've
hand-patched a single mark's translation or alignment locally and need to
push it as-is. Files are supplied by absolute path, no book-tree lookup."""
import json
import logging
import os

from cwmcp.lib.cwbe_client import CwbeClient

log = logging.getLogger("cwmcp.upload_zip")


async def upload_chapter_from_zip(
    client: CwbeClient,
    publication_id: str,
    audio_path: str,
    marks_path: str,
    marks_in_ms_path: str,
    translations_path: str,
    title: str,
    language: str,
    level: str,
    chapter_id: str | None = None,
) -> dict:
    """POST /from-audio (or PUT if chapter_id given). Files read synchronously
    from the provided absolute paths. The call returns a Job — poll it via
    `query_logs` or the cwbe Swagger if you need to track completion."""
    for path in (audio_path, marks_path, marks_in_ms_path, translations_path):
        if not os.path.exists(path):
            return {"status": "FAILED", "message": f"missing file: {path}"}

    with open(audio_path, "rb") as f:
        audio_bytes = f.read()
    with open(marks_path) as f:
        marks = json.load(f)
    with open(marks_in_ms_path) as f:
        marks_in_ms = json.load(f)
    with open(translations_path) as f:
        translations = json.load(f)

    if len(marks) != len(translations):
        return {
            "status": "FAILED",
            "message": f"marks count ({len(marks)}) != translations count ({len(translations)})",
        }

    job = await client.upload_chapter_from_zip(
        publication_id=publication_id,
        audio_bytes=audio_bytes,
        marks=marks,
        marks_in_ms=marks_in_ms,
        title=title,
        language=language.upper(),
        level=level.upper(),
        chapter_id=chapter_id,
        translations=translations,
    )
    return {
        "status": "OK",
        "job_id": job.get("id", ""),
        "method": "PUT" if chapter_id else "POST",
        "message": job.get("message", ""),
    }
