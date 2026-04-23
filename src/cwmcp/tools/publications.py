# src/cwmcp/tools/publications.py
"""Publication CRUD. All `update_publication_*` tools follow a
read-modify-write pattern: fetch the current publication, mutate the
requested field family, and PUT back the full object. This preserves
untouched fields while keeping the cwmcp surface easy to use."""
from cwmcp.lib.cwbe_client import CwbeClient

ALL_LANGS = {"EN", "FR", "ES", "DE", "IT", "PT", "ZH", "JA", "KO"}


async def _get_publication(client: CwbeClient, publication_id: str) -> dict:
    pubs = await client.get_publications()
    pub = next((p for p in pubs if p["id"] == publication_id), None)
    if not pub:
        raise ValueError(f"Publication {publication_id} not found")
    return pub


def _build_update_dto(pub: dict, readme: str | None = None) -> dict:
    """Build the full UpdatePublication DTO from the current publication
    record, optionally overriding readme (which getPublications doesn't
    always round-trip cleanly)."""
    return {
        "id": pub["id"],
        "title": pub["title"],
        "publicationType": pub["publicationType"],
        "copyrightTerms": pub["copyrightTerms"],
        "archived": pub["archived"],
        "isComplete": pub["isComplete"],
        "headers": pub["headers"],
        "descriptions": pub["descriptions"],
        "readme": readme if readme is not None else pub.get("readme", ""),
    }


async def create_publication(
    client: CwbeClient,
    title: str,
    publication_type: str,
    copyright_terms: list[str],
    headers: dict[str, str],
    descriptions: dict[str, str],
    readme: str,
    cover_path: str,
    archived: bool = False,
    is_complete: bool = False,
) -> dict:
    """Create a new publication. Requires cover image (local path)."""
    missing_headers = ALL_LANGS - set(headers.keys())
    missing_descs = ALL_LANGS - set(descriptions.keys())
    if missing_headers or missing_descs:
        return {
            "status": "FAILED",
            "message": f"all 9 langs required — missing headers={sorted(missing_headers)} descriptions={sorted(missing_descs)}",
        }
    with open(cover_path, "rb") as f:
        cover_bytes = f.read()
    import os
    cover_filename = os.path.basename(cover_path)
    result = await client.create_publication(
        title=title,
        publication_type=publication_type.upper(),
        copyright_terms=[c.upper() for c in copyright_terms],
        headers={k.upper(): v for k, v in headers.items()},
        descriptions={k.upper(): v for k, v in descriptions.items()},
        readme=readme,
        cover_bytes=cover_bytes,
        cover_filename=cover_filename,
        archived=archived,
        is_complete=is_complete,
    )
    return {"status": "OK", "job": result}


async def update_publication_titles(
    client: CwbeClient,
    publication_id: str,
    title: str | None = None,
    headers: dict[str, str] | None = None,
    descriptions: dict[str, str] | None = None,
) -> dict:
    """Partial update of title / per-lang headers / per-lang descriptions.
    Only the fields you pass are changed; others are preserved by reading
    the current publication first. `headers` / `descriptions` are MERGED —
    pass only the languages you want to change."""
    if title is None and not headers and not descriptions:
        return {"status": "NOOP", "message": "nothing to update"}
    pub = await _get_publication(client, publication_id)
    dto = _build_update_dto(pub)
    if title is not None:
        dto["title"] = title
    if headers:
        dto["headers"] = {**dto["headers"], **{k.upper(): v for k, v in headers.items()}}
    if descriptions:
        dto["descriptions"] = {**dto["descriptions"], **{k.upper(): v for k, v in descriptions.items()}}
    result = await client.update_publication(publication_id, dto)
    return {"status": "OK", "job": result}


async def update_publication_flags(
    client: CwbeClient,
    publication_id: str,
    is_complete: bool | None = None,
    archived: bool | None = None,
) -> dict:
    """Partial update of is_complete / archived flags."""
    if is_complete is None and archived is None:
        return {"status": "NOOP", "message": "nothing to update"}
    pub = await _get_publication(client, publication_id)
    dto = _build_update_dto(pub)
    if is_complete is not None:
        dto["isComplete"] = is_complete
    if archived is not None:
        dto["archived"] = archived
    result = await client.update_publication(publication_id, dto)
    return {"status": "OK", "job": result}


async def update_publication_readme(
    client: CwbeClient, publication_id: str, readme: str,
) -> dict:
    """Replace the publication readme markdown (kept for the legacy tool
    name — same read-modify-write pattern)."""
    pub = await _get_publication(client, publication_id)
    dto = _build_update_dto(pub, readme=readme)
    result = await client.update_publication(publication_id, dto)
    return {"status": "OK", "job": result}


async def delete_publication(
    client: CwbeClient, publication_id: str, confirm: bool,
) -> dict:
    """Delete a publication and every chapter + blob it owns.
    Irreversible — requires confirm=True."""
    if not confirm:
        return {
            "status": "REFUSED",
            "message": "delete_publication requires confirm=True (destroys every chapter and blob)",
        }
    pub = await _get_publication(client, publication_id)
    result = await client.delete_publication(publication_id)
    return {
        "status": "OK",
        "deleted_title": pub["title"],
        "job": result,
    }
