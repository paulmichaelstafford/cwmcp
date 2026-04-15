# src/cwmcp/lib/uploader.py
import json
import os
import re
import time

from cwmcp.lib.cwbe_client import CwbeClient
from cwmcp.lib.translations_helper import ALL_LANGS


def validate_translations(marks: list, translations: list, language: str) -> list[str]:
    """Validate translations match marks. Returns list of error strings."""
    expected_targets = sorted(ALL_LANGS - {language})
    errors = []

    if len(translations) != len(marks):
        errors.append(f"translations count ({len(translations)}) != marks count ({len(marks)})")
        return errors

    for i, (trans, mark) in enumerate(zip(translations, marks)):
        text_preview = mark["text"][:40] + "..." if len(mark["text"]) > 40 else mark["text"]
        prefix = f"mark[{i}] ({text_preview})"

        if trans.get("text") != mark["text"]:
            errors.append(f"{prefix}: source text mismatch")
        if trans.get("language") != language:
            errors.append(f"{prefix}: source language is {trans.get('language')!r}, expected {language!r}")

        if not trans.get("isTranslatable", True):
            continue
        if not any(c.isalnum() for c in trans.get("text", "")):
            continue

        results = trans.get("translationResults", [])
        result_langs = sorted(r.get("language") for r in results)
        if result_langs != expected_targets:
            missing = set(expected_targets) - set(result_langs)
            if missing:
                errors.append(f"{prefix}: missing target languages: {missing}")

        source_text = trans.get("text", "")
        for r in results:
            target_lang = r.get("language", "??")
            target_text = r.get("text", "")
            alignments = r.get("tokenAlignments", [])
            if not target_text:
                errors.append(f"{prefix} -> {target_lang}: empty translation text")
                continue
            if not alignments:
                errors.append(f"{prefix} -> {target_lang}: no alignments")
                continue
            for j, a in enumerate(alignments):
                ss, se = a.get("sourceStart", -1), a.get("sourceEnd", -1)
                ts, te = a.get("targetStart", -1), a.get("targetEnd", -1)
                if ss < 0 or se < 0 or ts < 0 or te < 0:
                    errors.append(f"{prefix} -> {target_lang} alignment[{j}]: negative offset")
                elif se >= len(source_text):
                    errors.append(f"{prefix} -> {target_lang} alignment[{j}]: sourceEnd {se} >= len {len(source_text)}")
                elif te >= len(target_text):
                    errors.append(f"{prefix} -> {target_lang} alignment[{j}]: targetEnd {te} >= len {len(target_text)}")
                elif ss > se or ts > te:
                    errors.append(f"{prefix} -> {target_lang} alignment[{j}]: start > end")

    return errors


def upload_chapter(
    client: CwbeClient,
    chapter_dir: str,
    publication_id: str,
    language: str,
    level: str,
    chapter_id: str | None = None,
) -> dict:
    """Upload a single chapter from a directory containing audio.mp3, marks.json, etc.
    Returns {"status": "COMPLETED"|"FAILED", "message": ..., "job_id": ...}
    """
    audio_path = os.path.join(chapter_dir, "audio.mp3")
    marks_path = os.path.join(chapter_dir, "marks.json")
    marks_ms_path = os.path.join(chapter_dir, "marks_in_milliseconds.json")
    translations_path = os.path.join(chapter_dir, "translations.json")
    chapter_path = os.path.join(chapter_dir, "chapter.md")

    for f in [audio_path, marks_path, marks_ms_path, translations_path, chapter_path]:
        if not os.path.exists(f):
            return {"status": "FAILED", "message": f"Missing file: {os.path.basename(f)}"}

    with open(audio_path, "rb") as f:
        audio_bytes = f.read()
    with open(marks_path) as f:
        marks = json.load(f)
    with open(marks_ms_path) as f:
        marks_in_ms = json.load(f)
    with open(translations_path) as f:
        translations = json.load(f)
    with open(chapter_path) as f:
        content = f.read()

    title = "Untitled"
    if content.startswith("---"):
        end = content.index("---", 3)
        m = re.search(r"title:\s*(.+)", content[3:end])
        if m:
            title = m.group(1).strip()
    chapter_num_match = re.search(r"(?:chapter|episode)-(\d+)", chapter_dir)
    if chapter_num_match:
        num = chapter_num_match.group(1)
        # Strip existing numeric prefix to avoid doubling (e.g. "0002 - 0002 - ...")
        title = re.sub(r"^\d+\s*-\s*", "", title)
        title = f"{num} - {title}"

    errors = validate_translations(marks, translations, language)
    if errors:
        return {"status": "FAILED", "message": f"{len(errors)} validation errors: {'; '.join(errors[:3])}"}

    # Auto-detect existing chapter to use PUT (update) instead of POST (create)
    if not chapter_id:
        try:
            existing = client.get_all_chapters(publication_id)
            for ch in existing:
                if ch.get("language") == language and ch.get("level") == level and ch.get("title") == title:
                    chapter_id = ch["id"]
                    break
        except Exception:
            pass  # If lookup fails, fall through to POST

    try:
        job = client.upload_chapter(
            publication_id, audio_bytes, marks, marks_in_ms,
            title, language, level, chapter_id, translations,
        )
    except Exception as e:
        return {"status": "FAILED", "message": f"Upload error: {e}"}

    job_id = job["id"]
    start = time.time()
    while time.time() - start < 300:
        try:
            job = client.get_job(job_id)
            if job["status"] != "PROCESSING":
                if job["status"] == "COMPLETED":
                    os.remove(audio_path)
                return {
                    "status": job["status"],
                    "job_id": job_id,
                    "message": job.get("message", ""),
                }
        except Exception:
            pass
        time.sleep(2)

    return {"status": "TIMEOUT", "job_id": job_id, "message": "Job did not complete within 300s"}
