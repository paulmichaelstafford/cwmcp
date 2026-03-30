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
