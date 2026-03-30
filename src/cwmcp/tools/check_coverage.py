import json
from cwmcp.lib.translations_helper import check_coverage, min_coverage_for


def check_translations_coverage(translations_path: str) -> list[dict]:
    """Check alignment coverage for all marks in a translations.json file."""
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
