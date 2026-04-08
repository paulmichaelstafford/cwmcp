# src/cwmcp/lib/translations_auto.py
from cwmcp.lib.cwbe_client import CwbeClient
from cwmcp.lib.translations_helper import check_coverage, min_coverage_for, ALL_LANGS


def build_translations_auto(
    client: CwbeClient,
    source_lang: str,
    marks: list[dict],
    manual_overrides: dict | None = None,
    target_lang: str | None = None,
) -> tuple[list, list, list]:
    """Build translations.json using cwbe translate + align endpoints.

    Args:
        client: CwbeClient instance
        source_lang: Source language code (e.g. "EN")
        marks: List of mark dicts from marks.json
        manual_overrides: Optional {mark_idx: {lang: {"text": ..., "tokenAlignments": [...]}}}
        target_lang: Optional single target language to process (e.g. "DE").
                     If set, only translates+aligns for that language.

    Returns: (translations_list, errors, warnings)
    """
    manual_overrides = manual_overrides or {}
    if target_lang:
        target_langs = [target_lang.upper()]
    else:
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
