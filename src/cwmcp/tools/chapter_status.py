import os
import glob

ALL_LANGS = ["en", "fr", "es", "de", "it", "pt", "zh", "ja", "ko"]
ALL_LEVELS = ["b1", "b2"]


def find_chapter_dir(book_path: str, chapter_number: int) -> str | None:
    """Find a chapter directory by number. Matches chapter-NNNN-* pattern."""
    pattern = os.path.join(book_path, f"chapter-{chapter_number:04d}-*")
    matches = glob.glob(pattern)
    return matches[0] if matches else None


def get_chapter_status(book_path: str, chapter_number: int) -> dict:
    """Get status of all lang/level combos for a chapter."""
    chapter_dir = find_chapter_dir(book_path, chapter_number)
    if chapter_dir is None:
        return {
            "chapter_dir": None,
            "chapter_number": chapter_number,
            "combos": [],
            "error": f"No chapter directory found for chapter {chapter_number}",
        }

    combos = []
    for lang in ALL_LANGS:
        for level in ALL_LEVELS:
            base = os.path.join(chapter_dir, lang, level)
            has_chapter = os.path.exists(os.path.join(base, "chapter.md"))
            has_audio = os.path.exists(os.path.join(base, "audio.mp3"))
            has_marks = os.path.exists(os.path.join(base, "marks.json"))
            has_marks_ms = os.path.exists(os.path.join(base, "marks_in_milliseconds.json"))
            has_translations = os.path.exists(os.path.join(base, "translations.json"))

            if has_chapter and has_audio and has_marks and has_marks_ms and has_translations:
                status = "ready_to_upload"
            elif not has_chapter:
                status = "missing_chapter"
            elif not has_audio:
                status = "missing_audio"
            elif not has_marks:
                status = "missing_marks"
            elif not has_translations:
                status = "missing_translations"
            else:
                status = "missing_marks_ms"

            combos.append({
                "lang": lang,
                "level": level,
                "has_chapter": has_chapter,
                "has_audio": has_audio,
                "has_marks": has_marks,
                "has_marks_ms": has_marks_ms,
                "has_translations": has_translations,
                "status": status,
            })

    return {
        "chapter_dir": chapter_dir,
        "chapter_number": chapter_number,
        "combos": combos,
    }
