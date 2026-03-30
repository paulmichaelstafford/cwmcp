import os
from cwmcp.lib.cwbe_client import CwbeClient
from cwmcp.lib.uploader import upload_chapter as do_upload
from cwmcp.lib.batch_uploader import upload_batch as do_batch
from cwmcp.tools.list_books import find_books
from cwmcp.tools.chapter_status import find_chapter_dir


def upload_single(
    client: CwbeClient,
    content_path: str,
    book: str,
    chapter_number: int,
    lang: str,
    level: str,
) -> dict:
    """Upload a single lang/level combo."""
    books = find_books(content_path)
    book_info = next((b for b in books if b["name"] == book), None)
    if not book_info:
        return {"status": "FAILED", "message": f"Book '{book}' not found"}
    if not book_info["publication_id"]:
        return {"status": "FAILED", "message": f"No publication ID found for '{book}'"}

    chapter_dir = find_chapter_dir(book_info["path"], chapter_number)
    if not chapter_dir:
        return {"status": "FAILED", "message": f"Chapter {chapter_number} not found"}

    combo_dir = os.path.join(chapter_dir, lang.lower(), level.lower())
    return do_upload(client, combo_dir, book_info["publication_id"], lang.upper(), level.upper())


def upload_chapter_batch(
    client: CwbeClient,
    content_path: str,
    book: str,
    chapter_number: int,
    workers: int = 3,
) -> dict:
    """Upload all ready combos for a chapter."""
    books = find_books(content_path)
    book_info = next((b for b in books if b["name"] == book), None)
    if not book_info:
        return {"error": f"Book '{book}' not found"}
    if not book_info["publication_id"]:
        return {"error": f"No publication ID found for '{book}'"}

    chapter_dir = find_chapter_dir(book_info["path"], chapter_number)
    if not chapter_dir:
        return {"error": f"Chapter {chapter_number} not found"}

    results = do_batch(client, chapter_dir, book_info["publication_id"], workers)
    succeeded = sum(1 for r in results if r["status"] == "COMPLETED")
    failed = sum(1 for r in results if r["status"] == "FAILED")
    return {
        "results": results,
        "summary": f"{succeeded} succeeded, {failed} failed, {len(results)} total",
    }
