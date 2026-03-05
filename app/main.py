import os
from pathlib import Path
from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from .models import Book
from .auth import check_credentials, require_admin, is_admin
from .services import (
    ensure_dirs, list_inbox_pdfs, move_inbox_to_books, save_uploaded_pdf
)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="it-book")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "dev_secret"))

# static
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# storage books (pdf)
ensure_dirs()

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    ensure_dirs()

@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db), grade: int | None = None, q: str | None = None):
    query = db.query(Book).filter(Book.approved == True)
    if grade is not None:
        query = query.filter(Book.grade == grade)
    if q:
        query = query.filter(Book.title.ilike(f"%{q}%"))
    books = query.order_by(Book.grade.asc(), Book.created_at.desc()).all()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "books": books,
        "grade": grade,
        "q": q or "",
        "is_admin": is_admin(request),
    })

@app.get("/book/{book_id}", response_class=HTMLResponse)
def book_page(book_id: int, request: Request, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id, Book.approved == True).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return templates.TemplateResponse("book.html", {
        "request": request,
        "book": book,
        "is_admin": is_admin(request),
    })

@app.get("/pdf/{filename}")
def serve_pdf(filename: str):
    path = Path("storage/books") / os.path.basename(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(str(path), media_type="application/pdf", filename=path.name)

# ---------------- Wiki ----------------
@app.get("/wiki", response_class=HTMLResponse)
def wiki(request: Request):
    return templates.TemplateResponse("wiki.html", {"request": request, "is_admin": is_admin(request)})

# ---------------- Settings ----------------
@app.get("/settings", response_class=HTMLResponse)
def settings(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request, "is_admin": is_admin(request)})

# ---------------- Admin ----------------
@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request, "error": None, "is_admin": is_admin(request)})

@app.post("/admin/login")
def admin_login(request: Request, username: str = Form(...), password: str = Form(...)):
    if check_credentials(username, password):
        request.session["is_admin"] = True
        return RedirectResponse(url="/admin", status_code=303)
    return templates.TemplateResponse("admin_login.html", {"request": request, "error": "Логин ё парол нодуруст аст.", "is_admin": False})

@app.post("/admin/logout")
def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)

@app.get("/admin", response_class=HTMLResponse)
def admin_panel(request: Request, db: Session = Depends(get_db)):
    guard = require_admin(request)
    if guard:
        return guard

    # Approved + Pending DB
    approved = db.query(Book).filter(Book.approved == True).order_by(Book.created_at.desc()).all()
    pending_db = db.query(Book).filter(Book.approved == False).order_by(Book.created_at.desc()).all()

    # Inbox PDFs not yet in DB (raw)
    inbox = list_inbox_pdfs()

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "approved": approved,
        "pending_db": pending_db,
        "inbox": inbox,
        "is_admin": True,
    })

@app.post("/admin/upload")
def admin_upload(
    request: Request,
    db: Session = Depends(get_db),
    title: str = Form(...),
    grade: int = Form(...),
    pdf: UploadFile = File(...),
):
    guard = require_admin(request)
    if guard:
        return guard

    if pdf.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="Only PDF allowed")

    saved_name = save_uploaded_pdf(pdf)
    book = Book(title=title.strip(), grade=int(grade), filename=saved_name, approved=True)
    db.add(book)
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/import-inbox")
def admin_import_inbox(
    request: Request,
    db: Session = Depends(get_db),
    filename: str = Form(...),
    title: str = Form(...),
    grade: int = Form(...),
):
    guard = require_admin(request)
    if guard:
        return guard

    # move from inbox to books
    moved_name = move_inbox_to_books(filename)
    book = Book(title=title.strip(), grade=int(grade), filename=moved_name, approved=True)
    db.add(book)
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/approve/{book_id}")
def admin_approve(book_id: int, request: Request, db: Session = Depends(get_db)):
    guard = require_admin(request)
    if guard:
        return guard

    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Not found")
    book.approved = True
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/delete/{book_id}")
def admin_delete(book_id: int, request: Request, db: Session = Depends(get_db)):
    guard = require_admin(request)
    if guard:
        return guard

    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        return RedirectResponse(url="/admin", status_code=303)

    # delete file if exists
    path = Path("storage/books") / book.filename
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass

    db.delete(book)
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)

# ---------------- Simple API (optional) ----------------
@app.get("/api/books")
def api_books(db: Session = Depends(get_db)):
    books = db.query(Book).filter(Book.approved == True).order_by(Book.grade.asc()).all()
    return JSONResponse([{
        "id": b.id,
        "title": b.title,
        "grade": b.grade,
        "filename": b.filename
    } for b in books])