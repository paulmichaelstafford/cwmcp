# src/cwmcp/tools/create_chapter.py
"""Thin wrapper around cwbe /chapters/from-marks. Cwbe orchestrates the full
pipeline (TTS → Gemini translate → awesome-align → cwseg tokens → ingest);
this tool kicks it off and polls the resulting Job until COMPLETED or FAILED.
"""
import asyncio
import logging

from cwmcp.lib.cwbe_client import CwbeClient

log = logging.getLogger("cwmcp.create_chapter")

TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED"}


async def create_chapter_from_marks(
    client: CwbeClient,
    publication_id: str,
    title: str,
    language: str,
    level: str,
    marks: list[str],
    source_audio_blob_name: str | None = None,
    poll_interval_s: float = 5.0,
    max_wait_s: float = 900.0,
) -> dict:
    """Kick off /from-marks and poll until the Job is terminal.

    Returns a dict with:
      - status: "COMPLETED" | "FAILED" | "CANCELLED" | "TIMEOUT"
      - chapter_id: str (present when status == COMPLETED)
      - job_id: str
      - message: str (cwbe-supplied; contains sourceAudioBlobName=... on
        failure so the caller can retry without regenerating audio)
    """
    if not marks:
        raise ValueError("marks list cannot be empty")
    if any(not m.strip() for m in marks):
        raise ValueError("mark text cannot be blank")

    job = await client.create_chapter_from_marks(
        publication_id=publication_id,
        title=title,
        language=language.upper(),
        level=level.upper(),
        marks=marks,
        source_audio_blob_name=source_audio_blob_name,
    )
    job_id = job.get("id", "")
    log.info(
        "from-marks kicked %s/%s '%s' job=%s", language, level, title, job_id,
    )

    deadline = asyncio.get_event_loop().time() + max_wait_s
    while True:
        status = (job.get("status") or "").upper()
        if status in TERMINAL_STATES:
            break
        if asyncio.get_event_loop().time() >= deadline:
            return {
                "status": "TIMEOUT",
                "job_id": job_id,
                "message": f"job still {status} after {max_wait_s:.0f}s",
            }
        await asyncio.sleep(poll_interval_s)
        job = await client.get_job(job_id)

    result: dict = {
        "status": status,
        "job_id": job_id,
        "message": job.get("message", ""),
    }
    if status == "COMPLETED":
        result["chapter_id"] = job.get("storedDataId", "")
    return result
