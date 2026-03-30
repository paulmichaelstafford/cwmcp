import json
import os

from cwmcp.lib.cwbe_client import CwbeClient
from cwmcp.lib.translations_auto import build_translations_auto
from cwmcp.tools.list_books import find_books
from cwmcp.tools.chapter_status import find_chapter_dir


def build_chapter_translations(
    client: CwbeClient,
    content_path: str,
    book: str,
    chapter_number: int,
    level: str,
    overrides: dict | None = None,
) -> dict:
    """Build translations.json for a chapter/level using auto builder."""
    books = find_books(content_path)
    book_info = next((b for b in books if b["name"] == book), None)
    if not book_info:
        return {"error": f"Book '{book}' not found"}

    chapter_dir = find_chapter_dir(book_info["path"], chapter_number)
    if not chapter_dir:
        return {"error": f"Chapter {chapter_number} not found in {book}"}

    marks_path = os.path.join(chapter_dir, "en", level.lower(), "marks.json")
    if not os.path.exists(marks_path):
        return {"error": f"marks.json not found at {marks_path}"}

    with open(marks_path) as f:
        marks = json.load(f)

    manual_overrides = {}
    if overrides:
        manual_overrides = {int(k): v for k, v in overrides.items()}

    translations, errors, warnings = build_translations_auto(
        client, "EN", marks, manual_overrides
    )

    output_path = os.path.join(chapter_dir, "en", level.lower(), "translations.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(translations, f, ensure_ascii=False, indent=2)

    return {
        "output_path": output_path,
        "mark_count": len(translations),
        "translation_count": sum(len(t["translationResults"]) for t in translations),
        "warnings": warnings,
        "errors": errors,
    }
