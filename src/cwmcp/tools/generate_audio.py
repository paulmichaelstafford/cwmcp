# src/cwmcp/tools/generate_audio.py
import os
import glob

from cwmcp.lib.audio_generator import generate_chapter_audio

LANGS = ["en", "fr", "es", "de", "it", "pt", "zh", "ja", "ko"]
LEVELS = ["b1", "b2"]


def find_chapter_dir(content_path: str, book: str, chapter_number: int) -> str | None:
    """Find the chapter directory matching the chapter number."""
    for category in ["onetime", "continuous"]:
        book_dir = os.path.join(content_path, category, book)
        if not os.path.isdir(book_dir):
            continue
        pattern = os.path.join(book_dir, f"chapter-{chapter_number:04d}-*")
        matches = glob.glob(pattern)
        if not matches:
            pattern = os.path.join(book_dir, f"episode-{chapter_number:04d}-*")
            matches = glob.glob(pattern)
        if matches:
            return matches[0]
    return None


def generate_single(
    cwtts_url: str,
    content_path: str,
    book: str,
    chapter_number: int,
    lang: str,
    level: str,
    cwbe_client=None,
    mistral_api_key: str = "",
    fish_audio_api_key: str = "",
) -> dict:
    """Generate audio for a single lang/level combo."""
    chapter_base = find_chapter_dir(content_path, book, chapter_number)
    if not chapter_base:
        return {"status": "error", "message": f"Chapter {chapter_number} not found for book '{book}'"}

    chapter_md = os.path.join(chapter_base, lang.lower(), level.lower(), "chapter.md")
    if not os.path.exists(chapter_md):
        return {"status": "error", "message": f"No chapter.md at {chapter_md}"}

    return generate_chapter_audio(
        cwtts_url=cwtts_url,
        chapter_md_path=chapter_md,
        language=lang.upper(),
        cwbe_client=cwbe_client,
        mistral_api_key=mistral_api_key,
        fish_audio_api_key=fish_audio_api_key,
    )


def generate_batch(
    cwtts_url: str,
    content_path: str,
    book: str,
    chapter_number: int,
    cwbe_client=None,
    mistral_api_key: str = "",
    fish_audio_api_key: str = "",
) -> list[dict]:
    """Generate audio for all lang/level combos that have chapter.md but no audio.mp3."""
    chapter_base = find_chapter_dir(content_path, book, chapter_number)
    if not chapter_base:
        return [{"status": "error", "message": f"Chapter {chapter_number} not found for book '{book}'"}]

    results = []
    for lang in LANGS:
        for level in LEVELS:
            chapter_md = os.path.join(chapter_base, lang, level, "chapter.md")
            audio_path = os.path.join(chapter_base, lang, level, "audio.mp3")
            if not os.path.exists(chapter_md):
                continue
            if os.path.exists(audio_path):
                results.append({"lang": lang.upper(), "level": level.upper(), "status": "skipped", "message": "Audio already exists"})
                continue

            result = generate_chapter_audio(
                cwtts_url=cwtts_url,
                chapter_md_path=chapter_md,
                language=lang.upper(),
                cwbe_client=cwbe_client,
                mistral_api_key=mistral_api_key,
                fish_audio_api_key=fish_audio_api_key,
            )
            result["lang"] = lang.upper()
            result["level"] = level.upper()
            results.append(result)

    return results
