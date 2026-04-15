# src/cwmcp/lib/cwbe_client.py
import requests
from requests.auth import HTTPBasicAuth

CWBE_URL = "https://be.collapsingwave.com"


class CwbeClient:
    def __init__(self, user: str, password: str):
        self.auth = HTTPBasicAuth(user, password)
        self.base_url = CWBE_URL

    def generate_chapter(self, language: str, marks: list[str]) -> dict:
        """Call /api/service/tts/generate-chapter. Returns {audio_base64, marks: [{id, text, start_ms, end_ms}]}."""
        resp = requests.post(
            f"{self.base_url}/api/service/tts/generate-chapter",
            auth=self.auth,
            json={"language": language, "marks": marks},
            timeout=300,
        )
        resp.raise_for_status()
        return resp.json()

    def translate_texts(self, source_lang: str, texts: list[str], batch_size: int = 5) -> dict[str, list[str]]:
        """Call /api/service/translate-texts. Returns {lang: [translated_text, ...]}."""
        all_results = None
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            resp = requests.post(
                f"{self.base_url}/api/service/translate-texts",
                auth=self.auth,
                json={"sourceLanguage": source_lang, "texts": batch},
                timeout=60,
            )
            resp.raise_for_status()
            batch_result = resp.json()
            if all_results is None:
                all_results = batch_result
            else:
                for lang in all_results:
                    all_results[lang].extend(batch_result[lang])
        return all_results or {}

    def align(self, source_lang: str, source_text: str, targets: dict[str, str]) -> dict:
        """Call /api/service/align. Returns Translation object with tokenAlignments."""
        resp = requests.post(
            f"{self.base_url}/api/service/align",
            auth=self.auth,
            json={
                "sourceLanguage": source_lang,
                "sourceText": source_text,
                "targets": targets,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    def upload_chapter(self, publication_id: str, audio_bytes: bytes, marks: list,
                       marks_in_ms: dict, title: str, language: str, level: str,
                       chapter_id: str | None = None, translations: list | None = None) -> dict:
        """Upload chapter to cwbe. Returns job dict."""
        url = f"{self.base_url}/api/service/publications/{publication_id}/chapters/from-audio"
        dto = {
            "title": title,
            "language": language,
            "level": level,
            "audioAiGenerated": True,
        }
        if chapter_id:
            dto["id"] = chapter_id

        import json
        files = {
            "dto": (None, json.dumps(dto), "application/json"),
            "audio_file": ("audio.mp3", audio_bytes, "audio/mpeg"),
            "marks": (None, json.dumps(marks), "application/json"),
            "marks_in_milliseconds": (None, json.dumps(marks_in_ms), "application/json"),
        }
        if translations is not None:
            files["translations"] = (None, json.dumps(translations), "application/json")

        if chapter_id:
            resp = requests.put(url, files=files, auth=self.auth, timeout=300)
        else:
            resp = requests.post(url, files=files, auth=self.auth, timeout=300)

        resp.raise_for_status()
        return resp.json()

    def get_job(self, job_id: str) -> dict:
        """Get job status."""
        resp = requests.get(
            f"{self.base_url}/api/service/jobs/{job_id}",
            auth=self.auth,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def get_chapters(self, publication_id: str) -> list[dict]:
        """Get chapters for a publication (for checking upload status)."""
        resp = requests.get(
            f"{self.base_url}/api/service/publications/{publication_id}/chapters",
            auth=self.auth,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def get_all_chapters(self, publication_id: str) -> list[dict]:
        """Get all chapters using pagination."""
        chapters = []
        page = 0
        while True:
            resp = requests.get(
                f"{self.base_url}/api/service/publications/{publication_id}/chapters",
                params={"page": page, "size": 100, "direction": "ASC"},
                auth=self.auth,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            chapters.extend(data.get("content", []))
            if page + 1 >= data.get("totalPages", 1):
                break
            page += 1
        return chapters

    def get_chapter_download_url(self, publication_id: str, chapter_id: str) -> str:
        """Get signed download URL for a chapter."""
        resp = requests.get(
            f"{self.base_url}/api/service/publications/{publication_id}/chapters/{chapter_id}/download-url",
            auth=self.auth,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.text.strip().strip('"')

    def update_chapter_metadata(self, publication_id: str, chapter_id: str,
                                title: str, language: str, level: str,
                                audio_ai_generated: bool = True) -> dict:
        """Update chapter metadata (title, language, level) without re-uploading audio."""
        resp = requests.patch(
            f"{self.base_url}/api/service/publications/{publication_id}/chapters/{chapter_id}",
            auth=self.auth,
            json={
                "id": chapter_id,
                "title": title,
                "language": language,
                "level": level,
                "audioAiGenerated": audio_ai_generated,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def update_publication_readme(self, publication_id: str, readme: str) -> dict:
        """Update readme for a publication. Fetches current state, patches readme, PUTs back."""
        import json as _json
        pubs = self.get_publications()
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
        resp = requests.put(
            f"{self.base_url}/api/service/publications/{publication_id}",
            auth=self.auth,
            files={"dto": (None, _json.dumps(dto), "application/json")},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def get_publications(self) -> list[dict]:
        """Get all publications."""
        resp = requests.get(
            f"{self.base_url}/api/service/publications",
            params={"page": 0, "size": 100},
            auth=self.auth,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("content", [])
