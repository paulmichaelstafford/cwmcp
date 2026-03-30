import os
import re


def find_books(content_path: str) -> list[dict]:
    """Scan content_path for books in onetime/ and continuous/ directories."""
    books = []
    for book_type in ["onetime", "continuous"]:
        type_dir = os.path.join(content_path, book_type)
        if not os.path.isdir(type_dir):
            continue
        for name in sorted(os.listdir(type_dir)):
            book_dir = os.path.join(type_dir, name)
            if not os.path.isdir(book_dir):
                continue
            pub_id = None
            readme = os.path.join(book_dir, "README.md")
            if os.path.exists(readme):
                with open(readme) as f:
                    content = f.read()
                m = re.search(r"\*\*Publication ID \(cwbe\):\*\*\s*(\S+)", content)
                if m:
                    pub_id = m.group(1)
            books.append({
                "name": name,
                "path": book_dir,
                "publication_id": pub_id,
                "type": book_type,
            })
    return books
