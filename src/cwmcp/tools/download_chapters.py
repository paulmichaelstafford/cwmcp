# src/cwmcp/tools/download_chapters.py
import json
import os
import re

import httpx

from cwmcp.lib.cwbe_client import CwbeClient


async def download_publication_chapters(client: CwbeClient, publication_id: str, output_dir: str) -> dict:
    """Download all chapters for a publication to a local directory."""
    os.makedirs(output_dir, exist_ok=True)

    chapters = await client.get_all_chapters(publication_id)

    metadata_path = os.path.join(output_dir, "chapters.json")
    with open(metadata_path, "w") as f:
        json.dump(chapters, f, indent=2, default=str)

    results = {"total": len(chapters), "downloaded": 0, "skipped": 0, "failed": 0, "details": []}

    async with httpx.AsyncClient(timeout=120) as http:
        for ch in chapters:
            ch_id = ch["id"]
            title = ch.get("title", "untitled")
            language = ch.get("language", "??")
            level = ch.get("level", "??")
            filename = re.sub(r"[^\w\s\-.]", "_", f"{title}_{language}_{level}.mp3").strip()
            filepath = os.path.join(output_dir, filename)

            if os.path.exists(filepath):
                results["skipped"] += 1
                results["details"].append({"file": filename, "status": "skipped"})
                continue

            try:
                download_url = await client.get_chapter_download_url(publication_id, ch_id)
                audio_resp = await http.get(download_url)
                audio_resp.raise_for_status()
                with open(filepath, "wb") as f:
                    f.write(audio_resp.content)
                results["downloaded"] += 1
                results["details"].append({"file": filename, "status": "ok", "bytes": len(audio_resp.content)})
            except Exception as e:
                results["failed"] += 1
                results["details"].append({"file": filename, "status": "failed", "error": str(e)})

    return results
