import os
import shutil
from pathlib import Path
from typing import List

INBOX_DIR = Path("pdf-book")
BOOKS_DIR = Path("storage/books")

def ensure_dirs():
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)

def list_inbox_pdfs() -> List[str]:
    ensure_dirs()
    return sorted([p.name for p in INBOX_DIR.glob("*.pdf") if p.is_file()])

def move_inbox_to_books(filename: str) -> str:
    """
    Move PDF from pdf-book/ -> storage/books/
    Returns destination filename (same).
    """
    ensure_dirs()
    src = INBOX_DIR / filename
    if not src.exists():
        raise FileNotFoundError(filename)
    dst = BOOKS_DIR / filename
    # If exists, add suffix
    if dst.exists():
        stem = dst.stem
        suffix = dst.suffix
        i = 2
        while True:
            candidate = BOOKS_DIR / f"{stem}_{i}{suffix}"
            if not candidate.exists():
                dst = candidate
                break
            i += 1
    shutil.move(str(src), str(dst))
    return dst.name

def save_uploaded_pdf(upload_file, desired_name: str | None = None) -> str:
    ensure_dirs()
    name = desired_name.strip() if desired_name else upload_file.filename
    if not name.lower().endswith(".pdf"):
        name = f"{name}.pdf"
    # sanitize
    name = os.path.basename(name).replace("..", "_").replace("/", "_").replace("\\", "_")

    dst = BOOKS_DIR / name
    if dst.exists():
        stem, suffix = dst.stem, dst.suffix
        i = 2
        while True:
            candidate = BOOKS_DIR / f"{stem}_{i}{suffix}"
            if not candidate.exists():
                dst = candidate
                break
            i += 1

    with open(dst, "wb") as f:
        shutil.copyfileobj(upload_file.file, f)

    return dst.name