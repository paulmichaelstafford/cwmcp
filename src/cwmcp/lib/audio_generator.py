# src/cwmcp/lib/audio_generator.py
"""Generate audio from chapter.md via cwbe /api/service/tts/generate-chapter.

Parses the chapter markdown, sends marks to cwbe (which proxies to cwtts),
saves the returned audio.mp3, marks.json, and marks_in_milliseconds.json next to chapter.md.
"""
import base64
import json
import logging
import os
import re


MAX_WORDS = 250

log = logging.getLogger("cwmcp.audio")


def parse_chapter(filepath: str) -> tuple[str, list[str]]:
    """Parse chapter.md into title and a flat list of mark texts.

    Each [narrator] line is one mark. Returns (title, marks).
    """
    with open(filepath) as f:
        content = f.read()

    title = "Untitled"
    if content.startswith("---"):
        end = content.index("---", 3)
        front_matter = content[3:end]
        title_match = re.search(r"title:\s*(.+)", front_matter)
        if title_match:
            title = title_match.group(1).strip()
        content = content[end + 3:].strip()

    marks = []
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("[") and "]" in line:
            bracket_end = line.index("]")
            text = line[bracket_end + 1:].strip()
            if text:
                marks.append(text)

    return title, marks


async def generate_chapter_audio(
    chapter_md_path: str,
    language: str,
    cwbe_client,
) -> dict:
    """Generate audio for a chapter.md file via cwbe /api/service/tts/generate-chapter.

    Returns: {"status": "ok"|"skipped"|"error", ...}
    """
    chapter_dir = os.path.dirname(os.path.abspath(chapter_md_path))
    audio_cache = os.path.join(chapter_dir, "audio.mp3")
    marks_cache = os.path.join(chapter_dir, "marks.json")
    marks_ms_cache = os.path.join(chapter_dir, "marks_in_milliseconds.json")

    if os.path.exists(audio_cache) and os.path.exists(marks_cache):
        return {"status": "skipped", "message": f"Audio already cached at {audio_cache}"}

    title, mark_texts = parse_chapter(chapter_md_path)

    total_words = sum(len(t.split()) for t in mark_texts)
    if total_words > MAX_WORDS:
        return {
            "status": "error",
            "message": f"Chapter has {total_words} words, max is {MAX_WORDS}. Trim before generating.",
        }

    if not mark_texts:
        return {"status": "error", "message": "No marks found in chapter.md"}

    log.info("tts %s marks=%d words=%d", language, len(mark_texts), total_words)
    try:
        data = await cwbe_client.generate_chapter(language=language.upper(), marks=mark_texts)
    except Exception as e:
        return {"status": "error", "message": f"cwbe generate_chapter failed: {e}"}

    audio_bytes = base64.b64decode(data["audio_base64"])
    with open(audio_cache, "wb") as f:
        f.write(audio_bytes)

    marks = []
    marks_in_ms = {}
    for i, m in enumerate(data["marks"]):
        mark_id = m["id"]
        marks.append({
            "id": mark_id,
            "sentence": 0,
            "paragraph": i,
            "text": m["text"],
        })
        marks_in_ms[mark_id] = m["start_ms"]

    with open(marks_cache, "w") as f:
        json.dump(marks, f, indent=2)
    with open(marks_ms_cache, "w") as f:
        json.dump(marks_in_ms, f, indent=2)

    return {
        "status": "ok",
        "message": f"Generated {len(marks)} marks, {len(audio_bytes)} bytes audio",
        "marks_count": len(marks),
        "audio_bytes": len(audio_bytes),
        "title": title,
        "words": total_words,
    }
