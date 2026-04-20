# src/cwmcp/lib/cwbe_client.py
import asyncio
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
        # cwtts is single-threaded — serialize concurrent callers here so they
        # queue in asyncio (cancels cleanly) instead of stacking inside httpx's
        # connection pool (where cancellation can hang and crash the MCP stdio).
        self._tts_semaphore = asyncio.Semaphore(1)

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

    async def generate_chapter(self, language: str, marks: list[str]) -> dict:
        # cwtts takes ~30-90s per chapter and processes serially. The semaphore
        # queues concurrent callers on our side so we don't pile requests into
        # httpx where cancellation gets tangled up in pool state.
        async with self._tts_semaphore:
            resp = await self._request(
                "POST",
                "/api/service/tts/generate-chapter",
                json={"language": language, "marks": marks},
                deadline=240.0,
            )
        return resp.json()

    async def translate_texts(self, source_lang: str, texts: list[str], batch_size: int = 5) -> dict[str, list[str]]:
        all_results: dict[str, list[str]] | None = None
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            resp = await self._request(
                "POST",
                "/api/service/translate-texts",
                json={"sourceLanguage": source_lang, "texts": batch},
                timeout=60,
            )
            batch_result = resp.json()
            if all_results is None:
                all_results = batch_result
            else:
                for lang in all_results:
                    all_results[lang].extend(batch_result[lang])
        return all_results or {}

    async def align(self, source_lang: str, source_text: str, targets: dict[str, str]) -> dict:
        resp = await self._request(
            "POST",
            "/api/service/align",
            json={
                "sourceLanguage": source_lang,
                "sourceText": source_text,
                "targets": targets,
            },
            timeout=60,
        )
        return resp.json()

    async def upload_chapter(self, publication_id: str, audio_bytes: bytes, marks: list,
                              marks_in_ms: dict, title: str, language: str, level: str,
                              chapter_id: str | None = None, translations: list | None = None) -> dict:
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
        # Upload is multipart + server-side processing; 180s is plenty for queueing.
        resp = await self._request(method, path, files=files, deadline=180.0)
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
