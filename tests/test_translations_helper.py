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
