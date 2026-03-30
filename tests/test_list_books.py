import os
from cwmcp.tools.list_books import find_books

def test_find_books_discovers_onetime_and_continuous(tmp_path):
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
