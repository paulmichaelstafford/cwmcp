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
