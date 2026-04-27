"""Unit tests for the chapter release sanity check structural validator.

Drives `_check_zip` directly with synthetic in-memory zips so the test
suite stays offline.
"""

from __future__ import annotations

import io
import json
import zipfile

from cwmcp.tools.sanity import _check_zip, ALL_LANGS


def _build_zip(
    *,
    source_lang: str,
    marks: list[dict],
    marks_ms: dict[str, int],
    trans_by_id: dict[str, dict],
    audio_size: int = 100_000,
) -> zipfile.ZipFile:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("marks.json", json.dumps(marks))
        zf.writestr("marks_in_milli_seconds.json", json.dumps(marks_ms))
        zf.writestr("mark_ids_to_translation.json", json.dumps(trans_by_id))
        zf.writestr("audio.mp3", b"\x00" * audio_size)
    buf.seek(0)
    return zipfile.ZipFile(buf, "r")


CJK_SET = {"ZH", "JA", "KO"}


def _good_translation(source_lang: str, target_langs: set[str], src_text: str) -> dict:
    """Build a translationResults list. Pair is CJK if either side is CJK."""
    results = []
    for tl in target_langs:
        ttext = f"[{tl}] {src_text}"
        is_cjk_pair = (source_lang in CJK_SET) or (tl in CJK_SET)
        if is_cjk_pair:
            results.append({
                "language": tl,
                "text": ttext,
                "tokens": [{"text": "x"}, {"text": "y"}],
                "tokenAlignments": [],
            })
        else:
            results.append({
                "language": tl,
                "text": ttext,
                "tokenAlignments": [
                    {"sourceStart": 0, "sourceEnd": 5, "targetStart": 0, "targetEnd": 5},
                ],
            })
    return {
        "language": source_lang,
        "text": src_text,
        "translationResults": results,
    }


def _good_eu_translation(target_langs: set[str], src_text: str) -> dict:
    """EN-source convenience wrapper for older tests."""
    return _good_translation("EN", target_langs, src_text)


def _build_clean_en_b1():
    src1 = "Before the great battle began, Paris stepped forward from the Trojan ranks."
    src2 = "Both armies agreed with deep relief, laying down their heavy weapons in hope."
    marks = [
        {"id": "uuid-1", "sentence": 0, "paragraph": 0, "text": src1},
        {"id": "uuid-2", "sentence": 1, "paragraph": 0, "text": src2},
    ]
    marks_ms = {"uuid-1": 0, "uuid-2": 5000}
    targets = ALL_LANGS - {"EN"}
    trans_by_id = {
        "uuid-1": _good_eu_translation(targets, src1),
        "uuid-2": _good_eu_translation(targets, src2),
    }
    # Override source lang in trans entries
    for v in trans_by_id.values():
        v["language"] = "EN"
    return marks, marks_ms, trans_by_id


def test_clean_chapter_passes():
    marks, marks_ms, trans_by_id = _build_clean_en_b1()
    zf = _build_zip(source_lang="EN", marks=marks, marks_ms=marks_ms, trans_by_id=trans_by_id)
    errors, warnings, stats = _check_zip("EN", "B1", zf)
    assert errors == [], errors
    # CJK targets should not warn here (we provided non-empty tokens)
    assert warnings == [], warnings
    assert stats["marks"] == 2
    # 2 marks × 5 EU targets × 1 alignment each = 10
    assert stats["alignments"] == 10
    # 2 marks × 3 CJK targets × 2 tokens each = 12
    assert stats["tokens_total"] == 12
    assert stats["tokens_filled"] == 12


def test_missing_required_file_is_error():
    marks, marks_ms, trans_by_id = _build_clean_en_b1()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("marks.json", json.dumps(marks))
        # deliberately omit the rest
    buf.seek(0)
    zf = zipfile.ZipFile(buf, "r")
    errors, _, _ = _check_zip("EN", "B1", zf)
    assert any("missing file in zip: marks_in_milli_seconds.json" in e for e in errors)


def test_blank_translation_flagged():
    marks, marks_ms, trans_by_id = _build_clean_en_b1()
    # blank one target's text
    trans_by_id["uuid-1"]["translationResults"][0]["text"] = ""
    zf = _build_zip(source_lang="EN", marks=marks, marks_ms=marks_ms, trans_by_id=trans_by_id)
    errors, _, stats = _check_zip("EN", "B1", zf)
    assert any("blank text" in e for e in errors)
    assert stats["blank_translations"] == 1


def test_missing_target_lang_flagged():
    marks, marks_ms, trans_by_id = _build_clean_en_b1()
    # drop FR from the targets of mark 1
    trans_by_id["uuid-1"]["translationResults"] = [
        r for r in trans_by_id["uuid-1"]["translationResults"] if r["language"] != "FR"
    ]
    zf = _build_zip(source_lang="EN", marks=marks, marks_ms=marks_ms, trans_by_id=trans_by_id)
    errors, _, stats = _check_zip("EN", "B1", zf)
    assert any("missing target langs" in e and "'FR'" in e for e in errors)
    assert stats["missing_target_langs"] == 1


def test_non_monotonic_ms_flagged():
    marks, marks_ms, trans_by_id = _build_clean_en_b1()
    marks_ms["uuid-2"] = 0  # equal to uuid-1, not strictly increasing
    zf = _build_zip(source_lang="EN", marks=marks, marks_ms=marks_ms, trans_by_id=trans_by_id)
    errors, _, _ = _check_zip("EN", "B1", zf)
    assert any("non-monotonic" in e for e in errors)


def test_eu_pair_no_alignments_warns_only():
    marks, marks_ms, trans_by_id = _build_clean_en_b1()
    # remove alignments from FR target on mark 1
    for r in trans_by_id["uuid-1"]["translationResults"]:
        if r["language"] == "FR":
            r["tokenAlignments"] = []
    zf = _build_zip(source_lang="EN", marks=marks, marks_ms=marks_ms, trans_by_id=trans_by_id)
    errors, warnings, stats = _check_zip("EN", "B1", zf)
    assert errors == []
    assert any("FR EU pair: no alignments" in w for w in warnings)
    assert stats["no_alignment_pairs"] == 1


def test_alignment_out_of_bounds_is_error():
    marks, marks_ms, trans_by_id = _build_clean_en_b1()
    for r in trans_by_id["uuid-1"]["translationResults"]:
        if r["language"] == "FR":
            r["tokenAlignments"] = [
                {"sourceStart": 0, "sourceEnd": 9999, "targetStart": 0, "targetEnd": 5},
            ]
    zf = _build_zip(source_lang="EN", marks=marks, marks_ms=marks_ms, trans_by_id=trans_by_id)
    errors, _, _ = _check_zip("EN", "B1", zf)
    assert any("source range out of bounds" in e for e in errors)


def test_cjk_pair_empty_tokens_is_error():
    marks, marks_ms, trans_by_id = _build_clean_en_b1()
    for r in trans_by_id["uuid-1"]["translationResults"]:
        if r["language"] == "ZH":
            r["tokens"] = []
    zf = _build_zip(source_lang="EN", marks=marks, marks_ms=marks_ms, trans_by_id=trans_by_id)
    errors, _, _ = _check_zip("EN", "B1", zf)
    assert any("ZH CJK pair: empty tokens" in e for e in errors)


def test_cjk_source_chapter_clean():
    """A KO source chapter — every target is a CJK pair."""
    src = "큰 전투가 시작되기 전에, 파리스 왕자는 트로이아 군대 사이에서 나왔다."
    marks = [{"id": "uuid-1", "sentence": 0, "paragraph": 0, "text": src}]
    marks_ms = {"uuid-1": 0}
    targets = ALL_LANGS - {"KO"}
    trans = _good_translation("KO", targets, src)
    zf = _build_zip(source_lang="KO", marks=marks, marks_ms=marks_ms,
                    trans_by_id={"uuid-1": trans})
    errors, warnings, stats = _check_zip("KO", "B1", zf)
    assert errors == []
    # all 8 targets are CJK pairs, so 0 alignments and 16 tokens
    assert stats["alignments"] == 0
    assert stats["tokens_total"] == 16


def test_short_eu_mark_is_warning():
    marks = [
        {"id": "uuid-1", "sentence": 0, "paragraph": 0, "text": "Too short."},
        {"id": "uuid-2", "sentence": 1, "paragraph": 0,
         "text": "This second mark is comfortably long enough for the threshold check."},
    ]
    marks_ms = {"uuid-1": 0, "uuid-2": 5000}
    targets = ALL_LANGS - {"EN"}
    trans_by_id = {
        "uuid-1": _good_eu_translation(targets, marks[0]["text"]),
        "uuid-2": _good_eu_translation(targets, marks[1]["text"]),
    }
    for v in trans_by_id.values():
        v["language"] = "EN"
    zf = _build_zip(source_lang="EN", marks=marks, marks_ms=marks_ms, trans_by_id=trans_by_id)
    errors, warnings, _ = _check_zip("EN", "B1", zf)
    assert errors == []
    assert any("EU short" in w for w in warnings)
