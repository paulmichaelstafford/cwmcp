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
    target_lang: str | None = None,
    source_lang: str = "EN",
) -> dict:
    """Build translations.json for a chapter/level using auto builder.

    If target_lang is set, only processes that one language and merges
    the result into the existing translations.json (preserving other languages).
    """
    books = find_books(content_path)
    book_info = next((b for b in books if b["name"] == book), None)
    if not book_info:
        return {"error": f"Book '{book}' not found"}

    chapter_dir = find_chapter_dir(book_info["path"], chapter_number)
    if not chapter_dir:
        return {"error": f"Chapter {chapter_number} not found in {book}"}

    src_lang = source_lang.lower()
    marks_path = os.path.join(chapter_dir, src_lang, level.lower(), "marks.json")
    if not os.path.exists(marks_path):
        return {"error": f"marks.json not found at {marks_path}"}

    with open(marks_path) as f:
        marks = json.load(f)

    manual_overrides = {}
    if overrides:
        manual_overrides = {int(k): v for k, v in overrides.items()}

    translations, errors, warnings = build_translations_auto(
        client, source_lang.upper(), marks, manual_overrides, target_lang=target_lang,
    )

    output_path = os.path.join(chapter_dir, src_lang, level.lower(), "translations.json")

    # If targeting a single language, merge into existing translations.json
    if target_lang and os.path.exists(output_path):
        with open(output_path, encoding="utf-8") as f:
            existing = json.load(f)

        tl = target_lang.upper()
        for i, new_entry in enumerate(translations):
            if i >= len(existing):
                break
            # Find and replace the target language in existing entry
            new_result = next(
                (r for r in new_entry["translationResults"] if r["language"] == tl),
                None,
            )
            if not new_result:
                continue
            # Remove old entry for this language if present
            existing[i]["translationResults"] = [
                r for r in existing[i]["translationResults"] if r["language"] != tl
            ]
            # Add updated entry
            existing[i]["translationResults"].append(new_result)
            # Sort for consistency
            existing[i]["translationResults"].sort(key=lambda r: r["language"])

        translations = existing

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(translations, f, ensure_ascii=False, indent=2)

    return {
        "output_path": output_path,
        "mark_count": len(translations),
        "translation_count": sum(len(t["translationResults"]) for t in translations),
        "target_lang": target_lang.upper() if target_lang else "all",
        "warnings": warnings,
        "errors": errors,
    }
