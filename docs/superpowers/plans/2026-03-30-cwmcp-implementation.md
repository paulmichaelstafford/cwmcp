# cwmcp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python MCP server that exposes CollapsingWave audiobook pipeline tools (status, translations, alignment, upload) to Claude Code.

**Architecture:** Single Python process using the `mcp` SDK over stdin/stdout. Lib modules are refactored copies of cwaudio scripts with credentials passed as parameters. Tool modules are thin wrappers that read config and call lib functions.

**Tech Stack:** Python 3.14, `mcp` SDK, `requests` for HTTP

**Spec:** `docs/superpowers/specs/2026-03-30-cwmcp-design.md`

---

## File Map

```
cwmcp/
├── pyproject.toml                        # Project config, dependencies
├── config.example.properties             # Template config
├── README.md                             # Setup + usage docs
├── CLAUDE.md                             # Instructions for Claude
├── src/
│   └── cwmcp/
│       ├── __init__.py
│       ├── server.py                     # MCP server entry point
│       ├── config.py                     # Config reader
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── list_books.py
│       │   ├── chapter_status.py
│       │   ├── check_coverage.py
│       │   ├── align_text.py
│       │   ├── build_translations.py
│       │   └── upload.py                 # Both single + batch
│       └── lib/
│           ├── __init__.py
│           ├── cwbe_client.py            # Shared HTTP client for cwbe API
│           ├── translations_auto.py      # Auto builder logic
│           ├── translations_helper.py    # Alignment computation + coverage
│           ├── uploader.py               # Single chapter upload logic
│           └── batch_uploader.py         # Batch upload logic
├── tests/
│   ├── __init__.py
│   ├── test_config.py
│   ├── test_translations_helper.py
│   ├── test_coverage.py
│   ├── test_list_books.py
│   └── test_chapter_status.py
```

---

### Task 1: Project scaffolding and config

**Files:**
- Create: `pyproject.toml`
- Create: `config.example.properties`
- Create: `src/cwmcp/__init__.py`
- Create: `src/cwmcp/config.py`
- Create: `tests/__init__.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "cwmcp"
version = "0.1.0"
description = "CollapsingWave MCP Server — audiobook pipeline tools for Claude Code"
requires-python = ">=3.11"
dependencies = [
    "mcp[cli]",
    "requests",
]

[project.optional-dependencies]
dev = [
    "pytest",
]
```

- [ ] **Step 2: Create config.example.properties**

```properties
# cwmcp configuration
# Copy to ~/.cwmcp/config.properties and fill in your values

# cwbe service account credentials
cwbe_user=your-email@example.com
cwbe_password=your-password

# Path to directory containing onetime/ and continuous/ book folders
content_path=/path/to/your/audio/content
```

- [ ] **Step 3: Create src/cwmcp/__init__.py**

Empty file.

- [ ] **Step 4: Write failing test for config reader**

```python
# tests/test_config.py
import os
import tempfile
import pytest
from cwmcp.config import load_config, ConfigError

def test_load_config_reads_properties(tmp_path):
    config_file = tmp_path / "config.properties"
    config_file.write_text(
        "cwbe_user=test@example.com\n"
        "cwbe_password=secret123\n"
        "content_path=/tmp/audio\n"
    )
    config = load_config(str(config_file))
    assert config.cwbe_user == "test@example.com"
    assert config.cwbe_password == "secret123"
    assert config.content_path == "/tmp/audio"

def test_load_config_missing_file():
    with pytest.raises(ConfigError, match="not found"):
        load_config("/nonexistent/config.properties")

def test_load_config_missing_required_field(tmp_path):
    config_file = tmp_path / "config.properties"
    config_file.write_text("cwbe_user=test@example.com\n")
    with pytest.raises(ConfigError, match="cwbe_password"):
        load_config(str(config_file))

def test_load_config_ignores_comments_and_blank_lines(tmp_path):
    config_file = tmp_path / "config.properties"
    config_file.write_text(
        "# This is a comment\n"
        "\n"
        "cwbe_user=test@example.com\n"
        "cwbe_password=secret123\n"
        "content_path=/tmp/audio\n"
    )
    config = load_config(str(config_file))
    assert config.cwbe_user == "test@example.com"
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `cd /Users/paulstafford/workspace/temp/sandbox/cw/cwmcp && python3 -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cwmcp'`

- [ ] **Step 6: Implement config.py**

```python
# src/cwmcp/config.py
from dataclasses import dataclass
from pathlib import Path

CWBE_URL = "https://be.collapsingwave.com"
DEFAULT_CONFIG_PATH = str(Path.home() / ".cwmcp" / "config.properties")
REQUIRED_FIELDS = ["cwbe_user", "cwbe_password", "content_path"]


class ConfigError(Exception):
    pass


@dataclass
class Config:
    cwbe_user: str
    cwbe_password: str
    content_path: str
    cwbe_url: str = CWBE_URL


def load_config(path: str = DEFAULT_CONFIG_PATH) -> Config:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {path}")

    props = {}
    for line in config_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            props[key.strip()] = value.strip()

    for field in REQUIRED_FIELDS:
        if field not in props:
            raise ConfigError(f"Missing required config field: {field}")

    return Config(
        cwbe_user=props["cwbe_user"],
        cwbe_password=props["cwbe_password"],
        content_path=props["content_path"],
    )
```

- [ ] **Step 7: Create tests/__init__.py**

Empty file.

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd /Users/paulstafford/workspace/temp/sandbox/cw/cwmcp && PYTHONPATH=src python3 -m pytest tests/test_config.py -v`
Expected: 4 tests PASS

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml config.example.properties src/ tests/
git commit -m "feat: project scaffolding and config reader"
```

---

### Task 2: cwbe HTTP client

**Files:**
- Create: `src/cwmcp/lib/__init__.py`
- Create: `src/cwmcp/lib/cwbe_client.py`

- [ ] **Step 1: Create src/cwmcp/lib/__init__.py**

Empty file.

- [ ] **Step 2: Create cwbe_client.py**

This is a shared HTTP client used by translations, alignment, and upload tools. No tests — it's a thin wrapper over `requests` that will be integration-tested through the tools.

```python
# src/cwmcp/lib/cwbe_client.py
import requests
from requests.auth import HTTPBasicAuth

CWBE_URL = "https://be.collapsingwave.com"


class CwbeClient:
    def __init__(self, user: str, password: str):
        self.auth = HTTPBasicAuth(user, password)
        self.base_url = CWBE_URL

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
```

- [ ] **Step 3: Commit**

```bash
git add src/cwmcp/lib/
git commit -m "feat: cwbe HTTP client"
```

---

### Task 3: translations_helper (coverage + alignment logic)

**Files:**
- Create: `src/cwmcp/lib/translations_helper.py`
- Create: `tests/test_translations_helper.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_translations_helper.py
from cwmcp.lib.translations_helper import align, check_coverage, min_coverage_for

def test_align_simple_pair():
    source = "Hello world"
    target = "Bonjour monde"
    pairs = [("Hello", "Bonjour"), ("world", "monde")]
    result = align(source, target, pairs)
    assert len(result) == 2
    assert result[0] == {"sourceStart": 0, "sourceEnd": 4, "targetStart": 0, "targetEnd": 6}
    assert result[1] == {"sourceStart": 6, "sourceEnd": 10, "targetStart": 8, "targetEnd": 12}

def test_align_missing_source_word_raises():
    import pytest
    with pytest.raises(ValueError, match="not found"):
        align("Hello world", "Bonjour monde", [("Missing", "Bonjour")])

def test_align_missing_target_word_raises():
    import pytest
    with pytest.raises(ValueError, match="not found"):
        align("Hello world", "Bonjour monde", [("Hello", "Missing")])

def test_check_coverage_full():
    text = "Hello"
    alignments = [{"targetStart": 0, "targetEnd": 4}]
    assert check_coverage(text, alignments) == 100

def test_check_coverage_partial():
    text = "Hello world"
    alignments = [{"targetStart": 0, "targetEnd": 4}]
    coverage = check_coverage(text, alignments)
    assert coverage > 0
    assert coverage < 100

def test_check_coverage_empty_text():
    assert check_coverage("", []) == 100

def test_check_coverage_punctuation_only():
    assert check_coverage("...", []) == 100

def test_min_coverage_european():
    assert min_coverage_for("EN", "FR") == 70
    assert min_coverage_for("DE", "ES") == 70

def test_min_coverage_cjk():
    assert min_coverage_for("EN", "ZH") == 40
    assert min_coverage_for("JA", "FR") == 40
    assert min_coverage_for("KO", "ZH") == 40
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/paulstafford/workspace/temp/sandbox/cw/cwmcp && PYTHONPATH=src python3 -m pytest tests/test_translations_helper.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement translations_helper.py**

Refactored from `cwaudio/translations_helper.py`. Same logic, no hardcoded credentials, clean imports.

```python
# src/cwmcp/lib/translations_helper.py
import json
import sys

CJK_LANGS = {"ZH", "JA", "KO"}
ALL_LANGS = {"EN", "FR", "ES", "DE", "IT", "PT", "ZH", "JA", "KO"}


def align(source: str, target: str, pairs: list[tuple[str, str]]) -> list[dict]:
    """Compute token alignments from word-pair mappings.
    pairs: list of (source_substring, target_substring)
    Returns list of {sourceStart, sourceEnd, targetStart, targetEnd} (all inclusive).
    """
    result = []
    src_used = set()
    tgt_used = set()
    for src_word, tgt_word in pairs:
        si = -1
        search_from = 0
        while True:
            si = source.find(src_word, search_from)
            if si == -1:
                break
            if si not in src_used:
                break
            search_from = si + 1
        if si == -1:
            raise ValueError(f"Source word '{src_word}' not found in: {source}")

        ti = -1
        search_from = 0
        while True:
            ti = target.find(tgt_word, search_from)
            if ti == -1:
                break
            if ti not in tgt_used:
                break
            search_from = ti + 1
        if ti == -1:
            raise ValueError(f"Target word '{tgt_word}' not found in: {target}")

        se = si + len(src_word) - 1
        te = ti + len(tgt_word) - 1
        src_used.add(si)
        tgt_used.add(ti)
        result.append({
            "sourceStart": si, "sourceEnd": se,
            "targetStart": ti, "targetEnd": te
        })
    return result


def min_coverage_for(src_lang: str, tgt_lang: str) -> int:
    """70% for European-European, 40% for anything involving CJK."""
    if src_lang in CJK_LANGS or tgt_lang in CJK_LANGS:
        return 40
    return 70


def check_coverage(text: str, alignments: list[dict], side: str = "target") -> int:
    """Compute alignment coverage percentage for alphanumeric characters.
    side: "target" uses targetStart/targetEnd, "source" uses sourceStart/sourceEnd.
    """
    letter_indices = [i for i, c in enumerate(text) if c.isalnum()]
    if not letter_indices:
        return 100
    start_key = f"{side}Start"
    end_key = f"{side}End"
    covered = sum(
        1 for i in letter_indices
        if any(a[start_key] <= i <= a[end_key] for a in alignments)
    )
    return (covered * 100) // len(letter_indices)


def build_translations(src_lang: str, marks_data: list) -> tuple[list, list]:
    """Build translations list from marks data.
    marks_data: list of (source_text, {lang: (translation, [(src_word, tgt_word), ...])})
    Returns (translations_list, errors_list)
    """
    target_langs = sorted(ALL_LANGS - {src_lang})
    result = []
    errors = []

    for mark_idx, (source_text, translations) in enumerate(marks_data):
        entry = {
            "language": src_lang,
            "text": source_text,
            "isTranslatable": True,
            "translationResults": []
        }

        for lang in target_langs:
            if lang not in translations:
                errors.append(f"Mark {mark_idx}: missing language {lang}")
                continue

            target_text, word_pairs = translations[lang]
            try:
                alignments = align(source_text, target_text, word_pairs)
            except ValueError as e:
                errors.append(f"Mark {mark_idx} -> {lang}: {e}")
                continue

            threshold = min_coverage_for(src_lang, lang)
            src_ranges = [(a["sourceStart"], a["sourceEnd"]) for a in alignments]
            tgt_ranges = [(a["targetStart"], a["targetEnd"]) for a in alignments]

            src_letters = [i for i, c in enumerate(source_text) if c.isalnum()]
            tgt_letters = [i for i, c in enumerate(target_text) if c.isalnum()]

            if src_letters:
                sc = sum(1 for i in src_letters if any(s <= i <= e for s, e in src_ranges))
                sc_pct = (sc * 100) // len(src_letters)
                if sc_pct < threshold:
                    errors.append(f"Mark {mark_idx} -> {lang}: source coverage {sc_pct}% < {threshold}%")

            if tgt_letters:
                tc = sum(1 for i in tgt_letters if any(s <= i <= e for s, e in tgt_ranges))
                tc_pct = (tc * 100) // len(tgt_letters)
                if tc_pct < threshold:
                    errors.append(f"Mark {mark_idx} -> {lang}: target coverage {tc_pct}% < {threshold}%")

            entry["translationResults"].append({
                "language": lang,
                "text": target_text,
                "tokenAlignments": alignments
            })

        result.append(entry)

    return result, errors


def build_and_save(src_lang: str, marks_data: list, output_path: str):
    """Build translations and save to file. Raises on error."""
    translations, errors = build_translations(src_lang, marks_data)

    if errors:
        raise ValueError(f"{len(errors)} translation errors: " + "; ".join(errors))

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(translations, f, ensure_ascii=False, indent=2)

    return translations
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/paulstafford/workspace/temp/sandbox/cw/cwmcp && PYTHONPATH=src python3 -m pytest tests/test_translations_helper.py -v`
Expected: 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/cwmcp/lib/translations_helper.py tests/test_translations_helper.py
git commit -m "feat: translations helper with alignment and coverage"
```

---

### Task 4: translations_auto (auto builder logic)

**Files:**
- Create: `src/cwmcp/lib/translations_auto.py`

- [ ] **Step 1: Create translations_auto.py**

Refactored from `cwaudio/build_translations_auto.py`. Accepts a `CwbeClient` instead of hardcoded creds.

```python
# src/cwmcp/lib/translations_auto.py
from cwmcp.lib.cwbe_client import CwbeClient
from cwmcp.lib.translations_helper import check_coverage, min_coverage_for, ALL_LANGS


def build_translations_auto(
    client: CwbeClient,
    source_lang: str,
    marks: list[dict],
    manual_overrides: dict | None = None,
) -> tuple[list, list, list]:
    """Build translations.json using cwbe translate + align endpoints.

    Args:
        client: CwbeClient instance
        source_lang: Source language code (e.g. "EN")
        marks: List of mark dicts from marks.json
        manual_overrides: Optional {mark_idx: {lang: {"text": ..., "tokenAlignments": [...]}}}

    Returns: (translations_list, errors, warnings)
    """
    manual_overrides = manual_overrides or {}
    target_langs = sorted(ALL_LANGS - {source_lang})
    texts = [m["text"] for m in marks]

    all_translations = client.translate_texts(source_lang, texts)

    result = []
    errors = []
    warnings = []

    for mark_idx, mark in enumerate(marks):
        source_text = mark["text"]
        entry = {
            "language": source_lang,
            "text": source_text,
            "isTranslatable": True,
            "translationResults": [],
        }

        targets_for_align = {}
        for lang in target_langs:
            if mark_idx in manual_overrides and lang in manual_overrides[mark_idx]:
                continue
            targets_for_align[lang] = all_translations[lang][mark_idx]

        align_result = None
        if targets_for_align:
            try:
                align_result = client.align(source_lang, source_text, targets_for_align)
            except Exception as e:
                errors.append(f"Mark {mark_idx}: align failed: {e}")

        for lang in target_langs:
            if mark_idx in manual_overrides and lang in manual_overrides[mark_idx]:
                override = manual_overrides[mark_idx][lang]
                entry["translationResults"].append({
                    "language": lang,
                    "text": override["text"],
                    "tokenAlignments": override["tokenAlignments"],
                })
                continue

            translated_text = all_translations[lang][mark_idx]
            alignments = []
            if align_result:
                for tr in align_result.get("translationResults", []):
                    if tr["language"] == lang:
                        alignments = tr["tokenAlignments"]
                        break

            threshold = min_coverage_for(source_lang, lang)
            src_cov = check_coverage(source_text, alignments, side="source")
            tgt_cov = check_coverage(translated_text, alignments, side="target")

            if src_cov < threshold or tgt_cov < threshold:
                warnings.append(
                    f"Mark {mark_idx} -> {lang}: src={src_cov}% tgt={tgt_cov}% "
                    f"(threshold={threshold}%)"
                )

            entry["translationResults"].append({
                "language": lang,
                "text": translated_text,
                "tokenAlignments": alignments,
            })

        result.append(entry)

    return result, errors, warnings
```

- [ ] **Step 2: Commit**

```bash
git add src/cwmcp/lib/translations_auto.py
git commit -m "feat: auto translation builder using cwbe endpoints"
```

---

### Task 5: uploader and batch_uploader

**Files:**
- Create: `src/cwmcp/lib/uploader.py`
- Create: `src/cwmcp/lib/batch_uploader.py`

- [ ] **Step 1: Create uploader.py**

Refactored from `cwaudio/upload_chapter.py`. Upload + validation logic, accepts `CwbeClient`.

```python
# src/cwmcp/lib/uploader.py
import json
import os
import re
import time

from cwmcp.lib.cwbe_client import CwbeClient
from cwmcp.lib.translations_helper import ALL_LANGS


def validate_translations(marks: list, translations: list, language: str) -> list[str]:
    """Validate translations match marks. Returns list of error strings."""
    expected_targets = sorted(ALL_LANGS - {language})
    errors = []

    if len(translations) != len(marks):
        errors.append(f"translations count ({len(translations)}) != marks count ({len(marks)})")
        return errors

    for i, (trans, mark) in enumerate(zip(translations, marks)):
        text_preview = mark["text"][:40] + "..." if len(mark["text"]) > 40 else mark["text"]
        prefix = f"mark[{i}] ({text_preview})"

        if trans.get("text") != mark["text"]:
            errors.append(f"{prefix}: source text mismatch")
        if trans.get("language") != language:
            errors.append(f"{prefix}: source language is {trans.get('language')!r}, expected {language!r}")

        if not trans.get("isTranslatable", True):
            continue
        if not any(c.isalnum() for c in trans.get("text", "")):
            continue

        results = trans.get("translationResults", [])
        result_langs = sorted(r.get("language") for r in results)
        if result_langs != expected_targets:
            missing = set(expected_targets) - set(result_langs)
            if missing:
                errors.append(f"{prefix}: missing target languages: {missing}")

        source_text = trans.get("text", "")
        for r in results:
            target_lang = r.get("language", "??")
            target_text = r.get("text", "")
            alignments = r.get("tokenAlignments", [])
            if not target_text:
                errors.append(f"{prefix} -> {target_lang}: empty translation text")
                continue
            if not alignments:
                errors.append(f"{prefix} -> {target_lang}: no alignments")
                continue
            for j, a in enumerate(alignments):
                ss, se = a.get("sourceStart", -1), a.get("sourceEnd", -1)
                ts, te = a.get("targetStart", -1), a.get("targetEnd", -1)
                if ss < 0 or se < 0 or ts < 0 or te < 0:
                    errors.append(f"{prefix} -> {target_lang} alignment[{j}]: negative offset")
                elif se >= len(source_text):
                    errors.append(f"{prefix} -> {target_lang} alignment[{j}]: sourceEnd {se} >= len {len(source_text)}")
                elif te >= len(target_text):
                    errors.append(f"{prefix} -> {target_lang} alignment[{j}]: targetEnd {te} >= len {len(target_text)}")
                elif ss > se or ts > te:
                    errors.append(f"{prefix} -> {target_lang} alignment[{j}]: start > end")

    return errors


def upload_chapter(
    client: CwbeClient,
    chapter_dir: str,
    publication_id: str,
    language: str,
    level: str,
    chapter_id: str | None = None,
) -> dict:
    """Upload a single chapter from a directory containing audio.mp3, marks.json, etc.
    Returns {"status": "COMPLETED"|"FAILED", "message": ..., "job_id": ...}
    """
    audio_path = os.path.join(chapter_dir, "audio.mp3")
    marks_path = os.path.join(chapter_dir, "marks.json")
    marks_ms_path = os.path.join(chapter_dir, "marks_in_milliseconds.json")
    translations_path = os.path.join(chapter_dir, "translations.json")
    chapter_path = os.path.join(chapter_dir, "chapter.md")

    for f in [audio_path, marks_path, marks_ms_path, translations_path, chapter_path]:
        if not os.path.exists(f):
            return {"status": "FAILED", "message": f"Missing file: {os.path.basename(f)}"}

    with open(audio_path, "rb") as f:
        audio_bytes = f.read()
    with open(marks_path) as f:
        marks = json.load(f)
    with open(marks_ms_path) as f:
        marks_in_ms = json.load(f)
    with open(translations_path) as f:
        translations = json.load(f)
    with open(chapter_path) as f:
        content = f.read()

    # Extract title
    title = "Untitled"
    if content.startswith("---"):
        end = content.index("---", 3)
        m = re.search(r"title:\s*(.+)", content[3:end])
        if m:
            title = m.group(1).strip()
    chapter_num_match = re.search(r"(?:chapter|episode)-(\d+)", chapter_dir)
    if chapter_num_match:
        title = f"{chapter_num_match.group(1)} - {title}"

    # Validate
    errors = validate_translations(marks, translations, language)
    if errors:
        return {"status": "FAILED", "message": f"{len(errors)} validation errors: {'; '.join(errors[:3])}"}

    # Upload
    try:
        job = client.upload_chapter(
            publication_id, audio_bytes, marks, marks_in_ms,
            title, language, level, chapter_id, translations,
        )
    except Exception as e:
        return {"status": "FAILED", "message": f"Upload error: {e}"}

    # Wait for job
    job_id = job["id"]
    start = time.time()
    while time.time() - start < 300:
        try:
            job = client.get_job(job_id)
            if job["status"] != "PROCESSING":
                if job["status"] == "COMPLETED":
                    os.remove(audio_path)
                return {
                    "status": job["status"],
                    "job_id": job_id,
                    "message": job.get("message", ""),
                }
        except Exception:
            pass
        time.sleep(2)

    return {"status": "TIMEOUT", "job_id": job_id, "message": "Job did not complete within 300s"}
```

- [ ] **Step 2: Create batch_uploader.py**

```python
# src/cwmcp/lib/batch_uploader.py
import os
import json
import concurrent.futures
from cwmcp.lib.cwbe_client import CwbeClient
from cwmcp.lib.uploader import upload_chapter

ALL_LANGS = ["en", "fr", "es", "de", "it", "pt", "zh", "ja", "ko"]
ALL_LEVELS = ["b1", "b2"]


def is_ready(chapter_base: str, lang: str, level: str) -> bool:
    """Check if a lang/level combo has all files needed for upload."""
    base = os.path.join(chapter_base, lang, level)
    required = ["audio.mp3", "marks.json", "marks_in_milliseconds.json", "translations.json", "chapter.md"]
    if not all(os.path.exists(os.path.join(base, f)) for f in required):
        return False
    marks_path = os.path.join(base, "marks.json")
    trans_path = os.path.join(base, "translations.json")
    with open(marks_path) as f:
        mc = len(json.load(f))
    with open(trans_path) as f:
        tc = len(json.load(f))
    return mc == tc


def upload_batch(
    client: CwbeClient,
    chapter_base: str,
    publication_id: str,
    workers: int = 3,
) -> list[dict]:
    """Upload all ready lang/level combos for a chapter.
    Returns list of {lang, level, status, message}.
    """
    combos = [(lang, level) for lang in ALL_LANGS for level in ALL_LEVELS]
    ready = [(lang, level) for lang, level in combos if is_ready(chapter_base, lang, level)]

    if not ready:
        return [{"lang": "-", "level": "-", "status": "SKIPPED", "message": "Nothing ready to upload"}]

    results = []

    def do_upload(lang: str, level: str) -> dict:
        chapter_dir = os.path.join(chapter_base, lang, level)
        result = upload_chapter(client, chapter_dir, publication_id, lang.upper(), level.upper())
        return {"lang": lang.upper(), "level": level.upper(), **result}

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(do_upload, lang, level): (lang, level) for lang, level in ready}
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    return results
```

- [ ] **Step 3: Commit**

```bash
git add src/cwmcp/lib/uploader.py src/cwmcp/lib/batch_uploader.py
git commit -m "feat: chapter uploader and batch uploader"
```

---

### Task 6: MCP server entry point and list_books tool

**Files:**
- Create: `src/cwmcp/tools/__init__.py`
- Create: `src/cwmcp/tools/list_books.py`
- Create: `src/cwmcp/server.py`
- Create: `tests/test_list_books.py`

- [ ] **Step 1: Create src/cwmcp/tools/__init__.py**

Empty file.

- [ ] **Step 2: Write failing test for list_books**

```python
# tests/test_list_books.py
import os
from cwmcp.tools.list_books import find_books

def test_find_books_discovers_onetime_and_continuous(tmp_path):
    # Set up fake content directory
    onetime = tmp_path / "onetime" / "1984"
    onetime.mkdir(parents=True)
    (onetime / "README.md").write_text(
        "# 1984\n\n## Metadata\n- **Publication ID (cwbe):** abc-123\n"
    )
    continuous = tmp_path / "continuous" / "everyday-life"
    continuous.mkdir(parents=True)
    (continuous / "README.md").write_text(
        "# Everyday Life\n\n## Metadata\n- **Publication ID (cwbe):** def-456\n"
    )
    books = find_books(str(tmp_path))
    assert len(books) == 2
    names = {b["name"] for b in books}
    assert names == {"1984", "everyday-life"}
    by_name = {b["name"]: b for b in books}
    assert by_name["1984"]["publication_id"] == "abc-123"
    assert by_name["1984"]["type"] == "onetime"
    assert by_name["everyday-life"]["publication_id"] == "def-456"
    assert by_name["everyday-life"]["type"] == "continuous"

def test_find_books_no_readme(tmp_path):
    (tmp_path / "onetime" / "orphan").mkdir(parents=True)
    books = find_books(str(tmp_path))
    assert len(books) == 1
    assert books[0]["publication_id"] is None

def test_find_books_empty(tmp_path):
    books = find_books(str(tmp_path))
    assert books == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/paulstafford/workspace/temp/sandbox/cw/cwmcp && PYTHONPATH=src python3 -m pytest tests/test_list_books.py -v`
Expected: FAIL

- [ ] **Step 4: Implement list_books.py**

```python
# src/cwmcp/tools/list_books.py
import os
import re


def find_books(content_path: str) -> list[dict]:
    """Scan content_path for books in onetime/ and continuous/ directories.
    Returns list of {name, path, publication_id, type}.
    """
    books = []
    for book_type in ["onetime", "continuous"]:
        type_dir = os.path.join(content_path, book_type)
        if not os.path.isdir(type_dir):
            continue
        for name in sorted(os.listdir(type_dir)):
            book_dir = os.path.join(type_dir, name)
            if not os.path.isdir(book_dir):
                continue
            pub_id = None
            readme = os.path.join(book_dir, "README.md")
            if os.path.exists(readme):
                with open(readme) as f:
                    content = f.read()
                m = re.search(r"\*\*Publication ID \(cwbe\):\*\*\s*(\S+)", content)
                if m:
                    pub_id = m.group(1)
            books.append({
                "name": name,
                "path": book_dir,
                "publication_id": pub_id,
                "type": book_type,
            })
    return books
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/paulstafford/workspace/temp/sandbox/cw/cwmcp && PYTHONPATH=src python3 -m pytest tests/test_list_books.py -v`
Expected: 3 tests PASS

- [ ] **Step 6: Create server.py (MCP entry point)**

```python
# src/cwmcp/server.py
import json
import os
from mcp.server.fastmcp import FastMCP

from cwmcp.config import load_config
from cwmcp.tools.list_books import find_books

mcp = FastMCP("cwmcp", instructions="CollapsingWave audiobook pipeline tools")

_config = None

def get_config():
    global _config
    if _config is None:
        _config = load_config()
    return _config


@mcp.tool()
def list_books() -> str:
    """List all books in the content directory with their publication IDs."""
    config = get_config()
    books = find_books(config.content_path)
    return json.dumps(books, indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

- [ ] **Step 7: Commit**

```bash
git add src/cwmcp/tools/ src/cwmcp/server.py tests/test_list_books.py
git commit -m "feat: MCP server entry point and list_books tool"
```

---

### Task 7: chapter_status tool

**Files:**
- Create: `src/cwmcp/tools/chapter_status.py`
- Create: `tests/test_chapter_status.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_chapter_status.py
import json
import os
from cwmcp.tools.chapter_status import get_chapter_status, find_chapter_dir

def test_find_chapter_dir(tmp_path):
    chapter = tmp_path / "onetime" / "1984" / "chapter-0003-the-ministry"
    chapter.mkdir(parents=True)
    result = find_chapter_dir(str(tmp_path / "onetime" / "1984"), 3)
    assert result == str(chapter)

def test_find_chapter_dir_not_found(tmp_path):
    book = tmp_path / "onetime" / "1984"
    book.mkdir(parents=True)
    result = find_chapter_dir(str(book), 99)
    assert result is None

def test_chapter_status_reports_files(tmp_path):
    book = tmp_path / "onetime" / "test-book"
    ch = book / "chapter-0001-intro" / "en" / "b1"
    ch.mkdir(parents=True)
    (ch / "chapter.md").write_text("---\ntitle: Intro\n---\n[narrator] Hello world.")
    (ch / "audio.mp3").write_bytes(b"fake audio")
    (ch / "marks.json").write_text('[{"id":"1","text":"Hello world."}]')
    (ch / "marks_in_milliseconds.json").write_text('{"1": 0}')
    # No translations.json

    status = get_chapter_status(str(book), 1)
    en_b1 = None
    for combo in status["combos"]:
        if combo["lang"] == "en" and combo["level"] == "b1":
            en_b1 = combo
            break
    assert en_b1 is not None
    assert en_b1["has_chapter"] is True
    assert en_b1["has_audio"] is True
    assert en_b1["has_marks"] is True
    assert en_b1["has_translations"] is False
    assert en_b1["status"] == "missing_translations"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/paulstafford/workspace/temp/sandbox/cw/cwmcp && PYTHONPATH=src python3 -m pytest tests/test_chapter_status.py -v`
Expected: FAIL

- [ ] **Step 3: Implement chapter_status.py**

```python
# src/cwmcp/tools/chapter_status.py
import os
import re
import glob

ALL_LANGS = ["en", "fr", "es", "de", "it", "pt", "zh", "ja", "ko"]
ALL_LEVELS = ["b1", "b2"]


def find_chapter_dir(book_path: str, chapter_number: int) -> str | None:
    """Find a chapter directory by number. Matches chapter-NNNN-* pattern."""
    pattern = os.path.join(book_path, f"chapter-{chapter_number:04d}-*")
    matches = glob.glob(pattern)
    return matches[0] if matches else None


def get_chapter_status(book_path: str, chapter_number: int) -> dict:
    """Get status of all lang/level combos for a chapter.
    Returns {chapter_dir, chapter_number, combos: [{lang, level, has_*, status}]}
    """
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/paulstafford/workspace/temp/sandbox/cw/cwmcp && PYTHONPATH=src python3 -m pytest tests/test_chapter_status.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Register chapter_status in server.py**

Add to `src/cwmcp/server.py`:

```python
from cwmcp.tools.chapter_status import get_chapter_status
from cwmcp.tools.list_books import find_books as _find_books

@mcp.tool()
def chapter_status(book: str, chapter_number: int) -> str:
    """Get the status of all lang/level combos for a chapter.
    Reports which files exist locally (chapter.md, audio, marks, translations).

    Args:
        book: Book directory name (e.g. "1984", "everyday-life")
        chapter_number: Chapter number (e.g. 7)
    """
    config = get_config()
    # Find book path
    books = _find_books(config.content_path)
    book_info = next((b for b in books if b["name"] == book), None)
    if not book_info:
        return json.dumps({"error": f"Book '{book}' not found"})
    status = get_chapter_status(book_info["path"], chapter_number)
    return json.dumps(status, indent=2)
```

- [ ] **Step 6: Commit**

```bash
git add src/cwmcp/tools/chapter_status.py tests/test_chapter_status.py src/cwmcp/server.py
git commit -m "feat: chapter_status tool"
```

---

### Task 8: check_coverage tool

**Files:**
- Create: `src/cwmcp/tools/check_coverage.py`
- Create: `tests/test_coverage.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_coverage.py
import json
from cwmcp.tools.check_coverage import check_translations_coverage

def test_check_coverage_reports_per_mark(tmp_path):
    translations = [
        {
            "language": "EN",
            "text": "Hello world",
            "isTranslatable": True,
            "translationResults": [
                {
                    "language": "FR",
                    "text": "Bonjour monde",
                    "tokenAlignments": [
                        {"sourceStart": 0, "sourceEnd": 4, "targetStart": 0, "targetEnd": 6},
                        {"sourceStart": 6, "sourceEnd": 10, "targetStart": 8, "targetEnd": 12},
                    ],
                },
            ],
        }
    ]
    path = tmp_path / "translations.json"
    path.write_text(json.dumps(translations))
    result = check_translations_coverage(str(path))
    assert len(result) == 1
    assert result[0]["mark_idx"] == 0
    fr = result[0]["languages"]["FR"]
    assert fr["source_coverage"] == 100
    assert fr["target_coverage"] == 100
    assert fr["pass"] is True

def test_check_coverage_detects_failure(tmp_path):
    translations = [
        {
            "language": "EN",
            "text": "Hello world today",
            "isTranslatable": True,
            "translationResults": [
                {
                    "language": "FR",
                    "text": "Bonjour monde aujourd'hui",
                    "tokenAlignments": [
                        {"sourceStart": 0, "sourceEnd": 4, "targetStart": 0, "targetEnd": 6},
                    ],
                },
            ],
        }
    ]
    path = tmp_path / "translations.json"
    path.write_text(json.dumps(translations))
    result = check_translations_coverage(str(path))
    fr = result[0]["languages"]["FR"]
    assert fr["pass"] is False
    assert fr["target_coverage"] < 70
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/paulstafford/workspace/temp/sandbox/cw/cwmcp && PYTHONPATH=src python3 -m pytest tests/test_coverage.py -v`
Expected: FAIL

- [ ] **Step 3: Implement check_coverage.py**

```python
# src/cwmcp/tools/check_coverage.py
import json
from cwmcp.lib.translations_helper import check_coverage, min_coverage_for


def check_translations_coverage(translations_path: str) -> list[dict]:
    """Check alignment coverage for all marks in a translations.json file.
    Returns per-mark, per-language coverage report.
    """
    with open(translations_path) as f:
        translations = json.load(f)

    report = []
    for mark_idx, trans in enumerate(translations):
        source_lang = trans["language"]
        source_text = trans["text"]
        languages = {}

        for tr in trans.get("translationResults", []):
            target_lang = tr["language"]
            target_text = tr["text"]
            alignments = tr.get("tokenAlignments", [])
            threshold = min_coverage_for(source_lang, target_lang)
            src_cov = check_coverage(source_text, alignments, side="source")
            tgt_cov = check_coverage(target_text, alignments, side="target")
            languages[target_lang] = {
                "source_coverage": src_cov,
                "target_coverage": tgt_cov,
                "threshold": threshold,
                "pass": src_cov >= threshold and tgt_cov >= threshold,
            }

        report.append({
            "mark_idx": mark_idx,
            "source_text": source_text[:60],
            "source_lang": source_lang,
            "languages": languages,
        })

    return report
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/paulstafford/workspace/temp/sandbox/cw/cwmcp && PYTHONPATH=src python3 -m pytest tests/test_coverage.py -v`
Expected: 2 tests PASS

- [ ] **Step 5: Register check_coverage in server.py**

Add to `src/cwmcp/server.py`:

```python
from cwmcp.tools.check_coverage import check_translations_coverage

@mcp.tool()
def check_coverage(translations_path: str) -> str:
    """Check alignment coverage for a translations.json file.
    Reports per-mark, per-language coverage with pass/fail status.

    Args:
        translations_path: Absolute path to translations.json
    """
    report = check_translations_coverage(translations_path)
    return json.dumps(report, indent=2)
```

- [ ] **Step 6: Commit**

```bash
git add src/cwmcp/tools/check_coverage.py tests/test_coverage.py src/cwmcp/server.py
git commit -m "feat: check_coverage tool"
```

---

### Task 9: align_text tool

**Files:**
- Create: `src/cwmcp/tools/align_text.py`

- [ ] **Step 1: Implement align_text.py**

```python
# src/cwmcp/tools/align_text.py
from cwmcp.lib.cwbe_client import CwbeClient
from cwmcp.lib.translations_helper import check_coverage, min_coverage_for


def align_text_pair(
    client: CwbeClient,
    source_lang: str,
    source_text: str,
    target_lang: str,
    target_text: str,
) -> dict:
    """Call awesome-align on a single source/target pair.
    Returns {alignments, source_coverage, target_coverage, threshold, pass}.
    """
    result = client.align(source_lang, source_text, {target_lang: target_text})

    alignments = []
    for tr in result.get("translationResults", []):
        if tr["language"] == target_lang:
            alignments = tr["tokenAlignments"]
            break

    threshold = min_coverage_for(source_lang, target_lang)
    src_cov = check_coverage(source_text, alignments, side="source")
    tgt_cov = check_coverage(target_text, alignments, side="target")

    return {
        "alignments": alignments,
        "source_coverage": src_cov,
        "target_coverage": tgt_cov,
        "threshold": threshold,
        "pass": src_cov >= threshold and tgt_cov >= threshold,
    }
```

- [ ] **Step 2: Register align_text in server.py**

Add to `src/cwmcp/server.py`:

```python
from cwmcp.tools.align_text import align_text_pair
from cwmcp.lib.cwbe_client import CwbeClient

def get_client() -> CwbeClient:
    config = get_config()
    return CwbeClient(config.cwbe_user, config.cwbe_password)

@mcp.tool()
def align_text(source_lang: str, source_text: str, target_lang: str, target_text: str) -> str:
    """Call awesome-align on a source/target text pair.
    Returns alignments with coverage percentages and pass/fail status.
    Useful for testing individual translations before committing.

    Args:
        source_lang: Source language code (e.g. "EN")
        source_text: Source text
        target_lang: Target language code (e.g. "JA")
        target_text: Target translation text
    """
    client = get_client()
    result = align_text_pair(client, source_lang, source_text, target_lang, target_text)
    return json.dumps(result, indent=2)
```

- [ ] **Step 3: Commit**

```bash
git add src/cwmcp/tools/align_text.py src/cwmcp/server.py
git commit -m "feat: align_text tool"
```

---

### Task 10: build_translations tool

**Files:**
- Create: `src/cwmcp/tools/build_translations.py`

- [ ] **Step 1: Implement build_translations.py**

```python
# src/cwmcp/tools/build_translations.py
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
    """Build translations.json for a chapter/level using auto builder.
    Returns {output_path, warnings, errors, mark_count, translation_count}.
    """
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

    # Convert string keys in overrides to int
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
```

- [ ] **Step 2: Register build_translations in server.py**

Add to `src/cwmcp/server.py`:

```python
from cwmcp.tools.build_translations import build_chapter_translations

@mcp.tool()
def build_translations(book: str, chapter_number: int, level: str, overrides: str | None = None) -> str:
    """Build translations.json for a chapter using Azure Translate + awesome-align.
    Optionally accepts manual overrides for marks that fail coverage.

    Args:
        book: Book directory name (e.g. "everyday-life")
        chapter_number: Chapter number (e.g. 7)
        level: "b1" or "b2"
        overrides: Optional JSON string with manual overrides: {"mark_idx": {"lang": {"text": "...", "tokenAlignments": [...]}}}
    """
    config = get_config()
    client = get_client()
    override_data = json.loads(overrides) if overrides else None
    result = build_chapter_translations(
        client, config.content_path, book, chapter_number, level, override_data,
    )
    return json.dumps(result, indent=2)
```

- [ ] **Step 3: Commit**

```bash
git add src/cwmcp/tools/build_translations.py src/cwmcp/server.py
git commit -m "feat: build_translations tool"
```

---

### Task 11: upload tools

**Files:**
- Create: `src/cwmcp/tools/upload.py`

- [ ] **Step 1: Implement upload.py**

```python
# src/cwmcp/tools/upload.py
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
```

- [ ] **Step 2: Register upload tools in server.py**

Add to `src/cwmcp/server.py`:

```python
from cwmcp.tools.upload import upload_single, upload_chapter_batch

@mcp.tool()
def upload_chapter(book: str, chapter_number: int, lang: str, level: str) -> str:
    """Upload a single lang/level combo to cwbe.
    Requires audio.mp3, marks.json, marks_in_milliseconds.json, and translations.json.

    Args:
        book: Book directory name (e.g. "everyday-life")
        chapter_number: Chapter number (e.g. 7)
        lang: Language code (e.g. "EN", "FR", "JA")
        level: "B1" or "B2"
    """
    config = get_config()
    client = get_client()
    result = upload_single(client, config.content_path, book, chapter_number, lang, level)
    return json.dumps(result, indent=2)

@mcp.tool()
def upload_batch(book: str, chapter_number: int, workers: int = 3) -> str:
    """Upload all ready lang/level combos for a chapter.
    Scans all 18 combos, uploads those with all required files.

    Args:
        book: Book directory name (e.g. "everyday-life")
        chapter_number: Chapter number (e.g. 7)
        workers: Max concurrent uploads (default 3, max 3)
    """
    config = get_config()
    client = get_client()
    workers = min(workers, 3)
    result = upload_chapter_batch(client, config.content_path, book, chapter_number, workers)
    return json.dumps(result, indent=2)
```

- [ ] **Step 3: Commit**

```bash
git add src/cwmcp/tools/upload.py src/cwmcp/server.py
git commit -m "feat: upload_chapter and upload_batch tools"
```

---

### Task 12: Final server.py assembly, README, and CLAUDE.md

**Files:**
- Modify: `src/cwmcp/server.py` (assemble all imports into final version)
- Rewrite: `README.md`
- Create: `CLAUDE.md`

- [ ] **Step 1: Write final server.py**

Assemble all tool registrations into the final version:

```python
# src/cwmcp/server.py
import json
from mcp.server.fastmcp import FastMCP

from cwmcp.config import load_config
from cwmcp.lib.cwbe_client import CwbeClient
from cwmcp.tools.list_books import find_books as _find_books
from cwmcp.tools.chapter_status import get_chapter_status
from cwmcp.tools.check_coverage import check_translations_coverage
from cwmcp.tools.align_text import align_text_pair
from cwmcp.tools.build_translations import build_chapter_translations
from cwmcp.tools.upload import upload_single, upload_chapter_batch

mcp = FastMCP("cwmcp", instructions="CollapsingWave audiobook pipeline tools")

_config = None
_client = None


def get_config():
    global _config
    if _config is None:
        _config = load_config()
    return _config


def get_client() -> CwbeClient:
    global _client
    if _client is None:
        config = get_config()
        _client = CwbeClient(config.cwbe_user, config.cwbe_password)
    return _client


@mcp.tool()
def list_books() -> str:
    """List all books in the content directory with their publication IDs."""
    config = get_config()
    books = _find_books(config.content_path)
    return json.dumps(books, indent=2)


@mcp.tool()
def chapter_status(book: str, chapter_number: int) -> str:
    """Get the status of all lang/level combos for a chapter.
    Reports which files exist locally (chapter.md, audio, marks, translations).

    Args:
        book: Book directory name (e.g. "1984", "everyday-life")
        chapter_number: Chapter number (e.g. 7)
    """
    config = get_config()
    books = _find_books(config.content_path)
    book_info = next((b for b in books if b["name"] == book), None)
    if not book_info:
        return json.dumps({"error": f"Book '{book}' not found"})
    status = get_chapter_status(book_info["path"], chapter_number)
    return json.dumps(status, indent=2)


@mcp.tool()
def check_coverage(translations_path: str) -> str:
    """Check alignment coverage for a translations.json file.
    Reports per-mark, per-language coverage with pass/fail status.

    Args:
        translations_path: Absolute path to translations.json
    """
    report = check_translations_coverage(translations_path)
    return json.dumps(report, indent=2)


@mcp.tool()
def align_text(source_lang: str, source_text: str, target_lang: str, target_text: str) -> str:
    """Call awesome-align on a source/target text pair.
    Returns alignments with coverage percentages and pass/fail status.
    Useful for testing individual translations before committing.

    Args:
        source_lang: Source language code (e.g. "EN")
        source_text: Source text
        target_lang: Target language code (e.g. "JA")
        target_text: Target translation text
    """
    client = get_client()
    result = align_text_pair(client, source_lang, source_text, target_lang, target_text)
    return json.dumps(result, indent=2)


@mcp.tool()
def build_translations(book: str, chapter_number: int, level: str, overrides: str | None = None) -> str:
    """Build translations.json for a chapter using Azure Translate + awesome-align.
    Optionally accepts manual overrides for marks that fail coverage.

    Args:
        book: Book directory name (e.g. "everyday-life")
        chapter_number: Chapter number (e.g. 7)
        level: "b1" or "b2"
        overrides: Optional JSON string with manual overrides: {"mark_idx": {"lang": {"text": "...", "tokenAlignments": [...]}}}
    """
    config = get_config()
    client = get_client()
    override_data = json.loads(overrides) if overrides else None
    result = build_chapter_translations(
        client, config.content_path, book, chapter_number, level, override_data,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
def upload_chapter(book: str, chapter_number: int, lang: str, level: str) -> str:
    """Upload a single lang/level combo to cwbe.
    Requires audio.mp3, marks.json, marks_in_milliseconds.json, and translations.json.

    Args:
        book: Book directory name (e.g. "everyday-life")
        chapter_number: Chapter number (e.g. 7)
        lang: Language code (e.g. "EN", "FR", "JA")
        level: "B1" or "B2"
    """
    config = get_config()
    client = get_client()
    result = upload_single(client, config.content_path, book, chapter_number, lang, level)
    return json.dumps(result, indent=2)


@mcp.tool()
def upload_batch(book: str, chapter_number: int, workers: int = 3) -> str:
    """Upload all ready lang/level combos for a chapter.
    Scans all 18 combos, uploads those with all required files.

    Args:
        book: Book directory name (e.g. "everyday-life")
        chapter_number: Chapter number (e.g. 7)
        workers: Max concurrent uploads (default 3, max 3)
    """
    config = get_config()
    client = get_client()
    workers = min(workers, 3)
    result = upload_chapter_batch(client, config.content_path, book, chapter_number, workers)
    return json.dumps(result, indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

- [ ] **Step 2: Write README.md**

```markdown
# cwmcp — CollapsingWave MCP Server

MCP server that exposes audiobook pipeline tools for the [CollapsingWave](https://collapsingwave.com) platform. Designed for use with Claude Code.

## Setup

### 1. Install

```bash
git clone <repo-url>
cd cwmcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Configure

Copy the example config and fill in your credentials:

```bash
mkdir -p ~/.cwmcp
cp config.example.properties ~/.cwmcp/config.properties
```

Edit `~/.cwmcp/config.properties`:

```properties
cwbe_user=your-email@example.com
cwbe_password=your-password
content_path=/path/to/your/audio/content
```

- `cwbe_user` / `cwbe_password`: Your cwbe service account credentials
- `content_path`: Path to directory containing `onetime/` and `continuous/` book folders

### 3. Register with Claude Code

Add to your Claude Code MCP settings:

```json
{
  "mcpServers": {
    "cwmcp": {
      "command": "/path/to/cwmcp/.venv/bin/python3",
      "args": ["/path/to/cwmcp/src/cwmcp/server.py"]
    }
  }
}
```

## Tools

| Tool | Description |
|------|-------------|
| `list_books` | List all books with publication IDs |
| `chapter_status` | Check what files exist locally for a chapter |
| `check_coverage` | Report alignment coverage for a translations.json |
| `align_text` | Test awesome-align on a single text pair |
| `build_translations` | Build translations.json using Azure Translate + awesome-align |
| `upload_chapter` | Upload a single lang/level combo |
| `upload_batch` | Upload all ready combos for a chapter |

## Content Directory Layout

The `content_path` should contain:

```
content_path/
├── onetime/
│   └── book-name/
│       ├── README.md          # Must contain: **Publication ID (cwbe):** <uuid>
│       └── chapter-NNNN-slug/
│           └── en/b1/
│               ├── chapter.md
│               ├── audio.mp3
│               ├── marks.json
│               ├── marks_in_milliseconds.json
│               └── translations.json
└── continuous/
    └── book-name/
        └── ...
```

## License

Apache 2.0
```

- [ ] **Step 3: Write CLAUDE.md**

```markdown
# CLAUDE.md — cwmcp

## What This Is

MCP server for the CollapsingWave audiobook pipeline. Exposes tools for checking chapter status, building translations, testing alignments, and uploading chapters.

## Running Tests

```bash
cd /path/to/cwmcp
PYTHONPATH=src python3 -m pytest tests/ -v
```

## Project Structure

- `src/cwmcp/server.py` — MCP entry point, all tool registrations
- `src/cwmcp/config.py` — Reads ~/.cwmcp/config.properties
- `src/cwmcp/tools/` — Tool implementations (thin wrappers)
- `src/cwmcp/lib/` — Core logic (translations, uploads, cwbe client)
- `tests/` — Unit tests

## Key Concepts

- 9 languages: EN, FR, ES, DE, IT, PT, ZH, JA, KO
- 2 levels: B1 (simple), B2 (intermediate)
- 18 combos per chapter (9 langs x 2 levels)
- Coverage thresholds: 70% European-European, 40% involving CJK
- cwbe URL is hardcoded: https://be.collapsingwave.com
```

- [ ] **Step 4: Commit**

```bash
git add src/cwmcp/server.py README.md CLAUDE.md
git commit -m "feat: final server assembly, README, and CLAUDE.md"
```

---

### Task 13: Create venv and run all tests

- [ ] **Step 1: Create virtual environment and install**

```bash
cd /Users/paulstafford/workspace/temp/sandbox/cw/cwmcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

- [ ] **Step 2: Run all tests**

```bash
cd /Users/paulstafford/workspace/temp/sandbox/cw/cwmcp
.venv/bin/python3 -m pytest tests/ -v
```

Expected: All tests PASS

- [ ] **Step 3: Add .gitignore and commit**

```
# .gitignore
.venv/
__pycache__/
*.egg-info/
dist/
build/
```

```bash
git add .gitignore
git commit -m "chore: add .gitignore"
```
