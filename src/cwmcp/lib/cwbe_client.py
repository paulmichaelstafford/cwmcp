# src/cwmcp/lib/cwbe_client.py
import json
import logging

import httpx

CWBE_URL = "https://be.collapsingwave.com"

log = logging.getLogger("cwmcp.cwbe")


class CwbeClient:
    def __init__(self, user: str, password: str):
        self.auth = httpx.BasicAuth(user, password)
        self.base_url = CWBE_URL
        self._client: httpx.AsyncClient | None = None

    def _get(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                auth=self.auth,
                base_url=self.base_url,
                timeout=httpx.Timeout(connect=15.0, read=240.0, write=60.0, pool=30.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def _request(self, method: str, path: str, *, deadline: float | None = None, **kwargs) -> httpx.Response:
        # Rely on httpx's own timeout — it cancels cleanly through the pool.
        # An earlier asyncio.wait_for wrapper could hang if the underlying
        # httpx task was stuck on a pool/semaphore acquire during cancel.
        if deadline is not None:
            kwargs.setdefault("timeout", deadline)
        log.debug("cwbe %s %s", method, path)
        try:
            resp = await self._get().request(method, path, **kwargs)
        except httpx.TimeoutException as e:
            log.warning("cwbe %s %s timeout: %s", method, path, e)
            raise TimeoutError(f"cwbe {method} {path} timed out: {e}") from e
        log.debug("cwbe %s %s -> %d", method, path, resp.status_code)
        if resp.status_code >= 400:
            body = (resp.text or "")[:500]
            log.warning("cwbe %s %s -> %d body=%r", method, path, resp.status_code, body)
            raise httpx.HTTPStatusError(
                f"HTTP {resp.status_code} on {method} {path}: {body}",
                request=resp.request,
                response=resp,
            )
        return resp

    # -----------------------------------------------------------------
    # Lego-block passthroughs to cwbe service endpoints. Use these when
    # create_chapter_from_marks isn't right — e.g., you're building a
    # chapter zip manually to patch a single mark and upload via
    # upload_chapter_from_zip.
    # -----------------------------------------------------------------

    async def generate_audio(self, language: str, marks: list[str]) -> dict:
        """POST /tts/generate-chapter — cwtts audio + mark timings."""
        resp = await self._request(
            "POST",
            "/api/service/tts/generate-chapter",
            json={"language": language, "marks": marks},
            deadline=240.0,
        )
        return resp.json()

    async def translate_texts(self, source_language: str, texts: list[str]) -> dict[str, list[str]]:
        """POST /translate-texts — Gemini sentence translation; map of lang → list."""
        resp = await self._request(
            "POST",
            "/api/service/translate-texts",
            json={"sourceLanguage": source_language, "texts": texts},
            deadline=240.0,
        )
        return resp.json()

    async def align(self, source_language: str, source_text: str, targets: dict[str, str]) -> dict:
        """POST /align — awesome-align EU↔EU token alignments per target."""
        resp = await self._request(
            "POST",
            "/api/service/align",
            json={
                "sourceLanguage": source_language,
                "sourceText": source_text,
                "targets": targets,
            },
            deadline=240.0,
        )
        return resp.json()

    async def gloss_tokens(
        self,
        source_language: str,
        sentence_text: str,
        sentence_translations: dict[str, str],
        tokens: list[str],
    ) -> dict:
        """POST /debug/gemini/gloss-tokens — per-token glosses for CJK tokens."""
        resp = await self._request(
            "POST",
            "/api/service/debug/gemini/gloss-tokens",
            json={
                "sourceLanguage": source_language,
                "sentenceText": sentence_text,
                "sentenceTranslations": sentence_translations,
                "tokens": tokens,
            },
            deadline=240.0,
        )
        return resp.json()

    async def upload_chapter_from_zip(
        self,
        publication_id: str,
        audio_bytes: bytes,
        marks: list,
        marks_in_ms: dict,
        title: str,
        language: str,
        level: str,
        chapter_id: str | None = None,
        translations: list | None = None,
    ) -> dict:
        """POST/PUT /chapters/from-audio — multipart upload of a pre-built
        chapter. PUTs if chapter_id is given (update), else POST (create)."""
        path = f"/api/service/publications/{publication_id}/chapters/from-audio"
        dto = {
            "title": title,
            "language": language,
            "level": level,
            "audioAiGenerated": True,
        }
        if chapter_id:
            dto["id"] = chapter_id

        files = {
            "dto": (None, json.dumps(dto), "application/json"),
            "audio_file": ("audio.mp3", audio_bytes, "audio/mpeg"),
            "marks": (None, json.dumps(marks), "application/json"),
            "marks_in_milliseconds": (None, json.dumps(marks_in_ms), "application/json"),
        }
        if translations is not None:
            files["translations"] = (None, json.dumps(translations), "application/json")

        method = "PUT" if chapter_id else "POST"
        resp = await self._request(method, path, files=files, deadline=240.0)
        return resp.json()

    # -----------------------------------------------------------------
    # Publication CRUD
    # -----------------------------------------------------------------

    async def create_publication(
        self,
        title: str,
        publication_type: str,
        copyright_terms: list[str],
        headers: dict[str, str],
        descriptions: dict[str, str],
        readme: str,
        cover_bytes: bytes,
        cover_filename: str = "cover.jpg",
        archived: bool = False,
        is_complete: bool = False,
    ) -> dict:
        """POST /publications — create a new publication."""
        dto = {
            "title": title,
            "publicationType": publication_type,
            "copyrightTerms": copyright_terms,
            "archived": archived,
            "isComplete": is_complete,
            "headers": headers,
            "descriptions": descriptions,
            "readme": readme,
        }
        files = {
            "dto": (None, json.dumps(dto), "application/json"),
            "jpeg_file": (cover_filename, cover_bytes, "image/jpeg"),
        }
        resp = await self._request("POST", "/api/service/publications", files=files, deadline=60.0)
        return resp.json()

    async def update_publication(
        self,
        publication_id: str,
        dto: dict,
        cover_bytes: bytes | None = None,
        cover_filename: str = "cover.jpg",
    ) -> dict:
        """PUT /publications/{id} — full-object update. Partial-update MCP
        tools read the current publication, apply their change to `dto`, and
        call this."""
        files: dict = {"dto": (None, json.dumps(dto), "application/json")}
        if cover_bytes is not None:
            files["jpeg_file"] = (cover_filename, cover_bytes, "image/jpeg")
        resp = await self._request(
            "PUT",
            f"/api/service/publications/{publication_id}",
            files=files,
            deadline=60.0,
        )
        return resp.json()

    async def delete_publication(self, publication_id: str) -> dict:
        """DELETE /publications/{id} — removes publication + every chapter + blobs."""
        resp = await self._request(
            "DELETE",
            f"/api/service/publications/{publication_id}",
            deadline=60.0,
        )
        return resp.json()

    async def delete_chapter(self, publication_id: str, chapter_id: str) -> dict:
        """DELETE /publications/{id}/chapters/{chapterId}."""
        resp = await self._request(
            "DELETE",
            f"/api/service/publications/{publication_id}/chapters/{chapter_id}",
            deadline=60.0,
        )
        return resp.json()

    async def create_chapter_from_marks(
        self,
        publication_id: str,
        title: str,
        language: str,
        level: str,
        marks: list[str],
        source_audio_blob_name: str | None = None,
    ) -> dict:
        body: dict = {
            "title": title,
            "language": language,
            "level": level,
            "marks": marks,
        }
        if source_audio_blob_name:
            body["sourceAudioBlobName"] = source_audio_blob_name
        # The /from-marks call itself returns a Job immediately; polling
        # happens in the caller. 240s deadline matches cwbe's
        # jobs.upload-timeout-ms convention — conservative margin for
        # queueing under load.
        resp = await self._request(
            "POST",
            f"/api/service/publications/{publication_id}/chapters/from-marks",
            json=body,
            deadline=240.0,
        )
        return resp.json()

    async def get_job(self, job_id: str) -> dict:
        resp = await self._request("GET", f"/api/service/jobs/{job_id}", timeout=30)
        return resp.json()

    async def get_chapters(self, publication_id: str) -> list[dict]:
        resp = await self._request(
            "GET",
            f"/api/service/publications/{publication_id}/chapters",
            timeout=30,
        )
        return resp.json()

    async def get_all_chapters(self, publication_id: str) -> list[dict]:
        chapters: list[dict] = []
        page = 0
        while True:
            resp = await self._request(
                "GET",
                f"/api/service/publications/{publication_id}/chapters",
                params={"page": page, "size": 100, "direction": "ASC"},
                timeout=30,
            )
            data = resp.json()
            chapters.extend(data.get("content", []))
            if page + 1 >= data.get("totalPages", 1):
                break
            page += 1
        return chapters

    async def get_chapter_download_url(self, publication_id: str, chapter_id: str) -> str:
        resp = await self._request(
            "GET",
            f"/api/service/publications/{publication_id}/chapters/{chapter_id}/download-url",
            timeout=30,
        )
        return resp.text.strip().strip('"')

    async def update_chapter_metadata(self, publication_id: str, chapter_id: str,
                                       title: str, language: str, level: str,
                                       audio_ai_generated: bool = True) -> dict:
        resp = await self._request(
            "PATCH",
            f"/api/service/publications/{publication_id}/chapters/{chapter_id}",
            json={
                "id": chapter_id,
                "title": title,
                "language": language,
                "level": level,
                "audioAiGenerated": audio_ai_generated,
            },
            timeout=30,
        )
        return resp.json()

    async def update_publication_readme(self, publication_id: str, readme: str) -> dict:
        pubs = await self.get_publications()
        pub = next((p for p in pubs if p["id"] == publication_id), None)
        if not pub:
            raise ValueError(f"Publication {publication_id} not found")
        dto = {
            "id": pub["id"],
            "title": pub["title"],
            "publicationType": pub["publicationType"],
            "copyrightTerms": pub["copyrightTerms"],
            "archived": pub["archived"],
            "isComplete": pub["isComplete"],
            "headers": pub["headers"],
            "descriptions": pub["descriptions"],
            "readme": readme,
        }
        resp = await self._request(
            "PUT",
            f"/api/service/publications/{publication_id}",
            files={"dto": (None, json.dumps(dto), "application/json")},
            timeout=30,
        )
        return resp.json()

    async def get_publications(self) -> list[dict]:
        resp = await self._request(
            "GET",
            "/api/service/publications",
            params={"page": 0, "size": 100},
            timeout=30,
        )
        return resp.json().get("content", [])
