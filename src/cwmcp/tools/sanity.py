# src/cwmcp/tools/sanity.py
"""Chapter release sanity check.

A "chapter release" is the 18 variants of one story chapter (9 languages
× 2 levels) shipped as a unit. This tool downloads every variant whose
title matches a prefix (e.g. "0005 - "), parses the per-chapter zip,
and verifies structural integrity:

    - 18 variants present (one per (lang, level) combo)
    - mark UUIDs consistent across marks.json, mark_ids_to_translation.json,
      and marks_in_milli_seconds.json
    - monotonic mark timings
    - every mark has exactly the 8 expected target languages
    - no blank target translations
    - EU↔EU pairs have non-empty tokenAlignments with in-bounds ranges
    - CJK pairs have non-empty tokens (no stray tokenAlignments)
    - audio.mp3 present and non-trivial in size

Returns a structured report. Pure I/O; logic is in `_check_zip` which is
unit-tested directly without hitting cwbe.
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

import httpx

from cwmcp.lib.cwbe_client import CwbeClient

ALL_LANGS = {"EN", "FR", "ES", "DE", "IT", "PT", "ZH", "JA", "KO"}
ALL_LEVELS = {"B1", "B2"}
CJK = {"ZH", "JA", "KO"}
EXPECTED_VARIANTS = len(ALL_LANGS) * len(ALL_LEVELS)  # 18


def _check_zip(language: str, level: str, zf: zipfile.ZipFile) -> tuple[list[str], list[str], dict[str, int]]:
    """Run structural checks on one variant's zip. Returns (errors, warnings, stats)."""
    errors: list[str] = []
    warnings: list[str] = []
    stats: dict[str, int] = {
        "marks": 0, "alignments": 0,
        "tokens_filled": 0, "tokens_total": 0,
        "blank_translations": 0, "missing_target_langs": 0,
        "no_alignment_pairs": 0, "audio_bytes": 0,
    }

    names = set(zf.namelist())
    required = ("marks.json", "marks_in_milli_seconds.json",
                "mark_ids_to_translation.json", "audio.mp3")
    for name in required:
        if name not in names:
            errors.append(f"missing file in zip: {name}")
    if errors:
        return errors, warnings, stats

    stats["audio_bytes"] = zf.getinfo("audio.mp3").file_size
    if stats["audio_bytes"] < 1024:
        errors.append(f"audio.mp3 suspiciously small: {stats['audio_bytes']} bytes")

    marks = json.loads(zf.read("marks.json").decode("utf-8"))
    marks_ms = json.loads(zf.read("marks_in_milli_seconds.json").decode("utf-8"))
    trans_by_id = json.loads(zf.read("mark_ids_to_translation.json").decode("utf-8"))

    stats["marks"] = len(marks)
    if len(marks) != len(trans_by_id):
        errors.append(f"marks ({len(marks)}) != translations ({len(trans_by_id)})")

    expected_targets = ALL_LANGS - {language}
    last_ms = -1

    for i, m in enumerate(marks):
        text = m.get("text", "")
        uuid = m.get("id")
        if not text.strip():
            errors.append(f"mark[{i}] empty text")
        if language not in CJK:
            wc = len(text.split())
            if wc < 5:
                warnings.append(f"mark[{i}] EU short ({wc} words): {text!r}")

        if uuid in marks_ms:
            ms = marks_ms[uuid]
            if not isinstance(ms, int):
                errors.append(f"mark[{i}] ms not int: {ms!r}")
            elif ms <= last_ms:
                errors.append(f"mark[{i}] non-monotonic ms ({ms} <= {last_ms})")
            else:
                last_ms = ms
        else:
            errors.append(f"mark[{i}] uuid {uuid} missing from marks_in_milli_seconds")

        mt = trans_by_id.get(uuid)
        if mt is None:
            errors.append(f"mark[{i}] uuid {uuid} missing from mark_ids_to_translation")
            continue

        if mt.get("language") != language:
            errors.append(f"mark[{i}] source lang {mt.get('language')} != chapter {language}")
        if mt.get("text") != text:
            warnings.append(f"mark[{i}] source text mismatch between marks.json and translation entry")

        results = mt.get("translationResults", []) or []
        target_langs = {r.get("language") for r in results}
        missing = expected_targets - target_langs
        extra = target_langs - expected_targets
        if missing:
            errors.append(f"mark[{i}] missing target langs: {sorted(missing)}")
            stats["missing_target_langs"] += len(missing)
        if extra:
            errors.append(f"mark[{i}] unexpected target langs: {sorted(extra)}")

        for r in results:
            tlang = r.get("language")
            ttext = r.get("text", "")
            if not ttext.strip():
                errors.append(f"mark[{i}] {tlang} blank text")
                stats["blank_translations"] += 1
                continue

            tokens = r.get("tokens") or []
            aligns = r.get("tokenAlignments") or []
            is_cjk_pair = (language in CJK) or (tlang in CJK)

            if is_cjk_pair:
                if aligns:
                    warnings.append(f"mark[{i}] {tlang} unexpected alignments on CJK pair: {len(aligns)}")
                if not tokens:
                    errors.append(f"mark[{i}] {tlang} CJK pair: empty tokens")
                else:
                    filled = sum(1 for t in tokens if (t.get("text", "") or "").strip())
                    stats["tokens_filled"] += filled
                    stats["tokens_total"] += len(tokens)
                    if filled < len(tokens):
                        warnings.append(
                            f"mark[{i}] {tlang} {len(tokens) - filled}/{len(tokens)} blank tokens"
                        )
            else:
                stats["alignments"] += len(aligns)
                if not aligns:
                    warnings.append(f"mark[{i}] {tlang} EU pair: no alignments")
                    stats["no_alignment_pairs"] += 1
                src_len = len(text)
                tgt_len = len(ttext)
                for a in aligns:
                    ss, se = a.get("sourceStart"), a.get("sourceEnd")
                    ts, te = a.get("targetStart"), a.get("targetEnd")
                    if not (isinstance(ss, int) and isinstance(se, int)
                            and 0 <= ss <= se <= src_len):
                        errors.append(f"mark[{i}] {tlang} source range out of bounds: {a}")
                        break
                    if not (isinstance(ts, int) and isinstance(te, int)
                            and 0 <= ts <= te <= tgt_len):
                        errors.append(f"mark[{i}] {tlang} target range out of bounds: {a}")
                        break

    return errors, warnings, stats


async def chapter_release_sanity_check(
    client: CwbeClient,
    publication_id: str,
    title_prefix: str,
) -> dict[str, Any]:
    """Verify all 18 variants of a chapter release.

    Returns:
        {
          "ok": bool,
          "publication_id": str,
          "title_prefix": str,
          "variants_found": int,
          "variants_expected": 18,
          "missing_combos": [(lang, level), ...],
          "errors": int,
          "warnings": int,
          "variants": [
            {
              "language": str, "level": str, "chapter_id": str, "title": str,
              "ok": bool, "errors": [...], "warnings": [...], "stats": {...},
            },
            ...
          ],
        }
    """
    all_chapters = await client.get_all_chapters(publication_id)
    matching = [c for c in all_chapters if c.get("title", "").startswith(title_prefix)]

    found_combos = {(c.get("language"), c.get("level")) for c in matching}
    expected_combos = {(lang, level) for lang in ALL_LANGS for level in ALL_LEVELS}
    missing_combos = sorted(expected_combos - found_combos)

    variants: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=120) as http:
        for ch in matching:
            chap_id = ch["id"]
            lang = ch.get("language", "??")
            level = ch.get("level", "??")
            title = ch.get("title", "")
            try:
                url = await client.get_chapter_download_url(publication_id, chap_id)
                resp = await http.get(url)
                resp.raise_for_status()
                with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                    errors, warnings, stats = _check_zip(lang, level, zf)
            except Exception as e:
                errors = [f"download/parse failed: {type(e).__name__}: {e}"]
                warnings = []
                stats = {}

            variants.append({
                "language": lang,
                "level": level,
                "chapter_id": chap_id,
                "title": title,
                "ok": not errors,
                "errors": errors,
                "warnings": warnings,
                "stats": stats,
            })

    total_errors = sum(len(v["errors"]) for v in variants)
    total_warnings = sum(len(v["warnings"]) for v in variants)

    overall_ok = (
        total_errors == 0
        and not missing_combos
        and len(variants) == EXPECTED_VARIANTS
    )

    return {
        "ok": overall_ok,
        "publication_id": publication_id,
        "title_prefix": title_prefix,
        "variants_found": len(variants),
        "variants_expected": EXPECTED_VARIANTS,
        "missing_combos": [list(c) for c in missing_combos],
        "errors": total_errors,
        "warnings": total_warnings,
        "variants": variants,
    }
