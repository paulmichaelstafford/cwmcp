# src/cwmcp/tools/align_text.py
from cwmcp.lib.cwbe_client import CwbeClient
from cwmcp.lib.translations_helper import check_coverage, min_coverage_for


async def align_text_pair(
    client: CwbeClient,
    source_lang: str,
    source_text: str,
    target_lang: str,
    target_text: str,
) -> dict:
    """Call awesome-align on a single source/target pair."""
    result = await client.align(source_lang, source_text, {target_lang: target_text})

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
