# src/cwmcp/tools/chapters.py
"""Chapter-level destructive operations. Non-destructive ones
(create_chapter_from_marks, update_chapter_metadata, list_uploaded_chapters)
live elsewhere — this file is the confirm-guarded delete surface."""
from cwmcp.lib.cwbe_client import CwbeClient


async def delete_chapter(
    client: CwbeClient, publication_id: str, chapter_id: str, confirm: bool,
) -> dict:
    """Delete a single chapter variant and its blob. Irreversible —
    requires confirm=True."""
    if not confirm:
        return {
            "status": "REFUSED",
            "message": "delete_chapter requires confirm=True (destroys audio + marks + translations blob)",
        }
    # Best-effort fetch so the response can confirm what was deleted.
    found: dict | None = None
    try:
        chapters = await client.get_all_chapters(publication_id)
        found = next((c for c in chapters if c["id"] == chapter_id), None)
    except Exception:
        pass
    result = await client.delete_chapter(publication_id, chapter_id)
    return {
        "status": "OK",
        "deleted_chapter": found if found else {"id": chapter_id},
        "job": result,
    }
