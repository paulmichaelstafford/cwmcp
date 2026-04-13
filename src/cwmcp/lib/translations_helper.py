# src/cwmcp/lib/translations_helper.py
import json
import sys
from enum import Enum


class LanguageFamily(str, Enum):
    EUROPEAN = "EUROPEAN"
    ASIAN = "ASIAN"


LANGUAGE_FAMILY: dict[str, LanguageFamily] = {
    "EN": LanguageFamily.EUROPEAN,
    "FR": LanguageFamily.EUROPEAN,
    "ES": LanguageFamily.EUROPEAN,
    "DE": LanguageFamily.EUROPEAN,
    "IT": LanguageFamily.EUROPEAN,
    "PT": LanguageFamily.EUROPEAN,
    "ZH": LanguageFamily.ASIAN,
    "JA": LanguageFamily.ASIAN,
    "KO": LanguageFamily.ASIAN,
}

CJK_LANGS = {"ZH", "JA", "KO"}
ALL_LANGS = {"EN", "FR", "ES", "DE", "IT", "PT", "ZH", "JA", "KO"}


def same_family(lang_a: str, lang_b: str) -> bool:
    """Return True if both languages are in the same family (both European or both Asian)."""
    return LANGUAGE_FAMILY[lang_a.upper()] == LANGUAGE_FAMILY[lang_b.upper()]


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
