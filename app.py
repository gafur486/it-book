import os
import json
import hmac
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin

from db import init_db, get_session, engine
from models import Lesson, Exercise

# =========================
# CONFIG
# =========================
ADMIN_LOGIN = os.getenv("ADMIN_LOGIN", "abdu0004")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "12345678")
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_SUPER_SECRET_KEY_2026").encode("utf-8")

BASE_DIR = Path(__file__).parent

# Content import folders
CONTENT_ROOT = Path(os.getenv("CONTENT_DIR", str(BASE_DIR / "content")))
CONTENT_PENDING = CONTENT_ROOT / "pending"
CONTENT_APPROVED = CONTENT_ROOT / "approved"
CONTENT_PENDING.mkdir(parents=True, exist_ok=True)
CONTENT_APPROVED.mkdir(parents=True, exist_ok=True)

# PDF folders (keep your existing feature)
_default_desktop_pdf = str(Path.home() / "Desktop" / "pdf-book")
PDF_ROOT = Path(os.getenv("PDF_BOOK_DIR", _default_desktop_pdf))
if not PDF_ROOT.exists():
    PDF_ROOT = BASE_DIR / "pdf-book"
PDF_ROOT.mkdir(parents=True, exist_ok=True)
PDF_PENDING = PDF_ROOT / "pending"
PDF_APPROVED = PDF_ROOT / "approved"
PDF_PENDING.mkdir(parents=True, exist_ok=True)
PDF_APPROVED.mkdir(parents=True, exist_ok=True)

SECTIONS = [
    ("phrases", "Phrases / Sentences"),
    ("words", "Words / Vocabulary"),
    ("alphabet", "Alphabet & Pronunciation"),
    ("verbs", "Verbs"),
    ("grammar", "Grammar"),
    ("exams", "Practice / Tests"),
]

# =========================
# APP INIT
# =========================
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/pdf", StaticFiles(directory=str(PDF_APPROVED)), name="pdf")  # only approved PDFs

env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html", "xml"])
)

md = MarkdownIt("commonmark", {"html": False, "linkify": True, "typographer": True}).use(tasklists_plugin)

def render_md(text: str) -> str:
    return md.render(text or "")

# =========================
# AUTH (signed cookie)
# =========================
def _sign(value: str) -> str:
    sig = hmac.new(SECRET_KEY, value.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{value}.{sig}"

def _verify(signed: str) -> bool:
    if not signed or "." not in signed:
        return False
    value, sig = signed.rsplit(".", 1)
    expected = hmac.new(SECRET_KEY, value.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected) and value == "admin"

def is_admin(request: Request) -> bool:
    return _verify(request.cookies.get("itbook_admin", ""))

def require_admin(request: Request) -> Optional[RedirectResponse]:
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)
    return None

# =========================
# DB INIT
# =========================
@app.on_event("startup")
def on_startup():
    init_db()

# =========================
# HELPERS: CONTENT IMPORT
# =========================
def safe_name(name: str) -> bool:
    return all(x not in name for x in ["..", "/", "\\"])

def read_json_file(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON root must be object")
    return data

def upsert_lesson_from_payload(session: Session, payload: Dict[str, Any]) -> Lesson:
    section = (payload.get("section") or "").strip()
    title = (payload.get("title") or "").strip()
    order_no = int(payload.get("order_no") or 0)
    body_md = payload.get("body_md") or ""

    if not section or not title:
        raise ValueError("section/title required")

    lesson = Lesson(section=section, title=title, order_no=order_no, body_md=body_md)
    session.add(lesson)
    session.commit()
    session.refresh(lesson)

    # exercises
    exs = payload.get("exercises") or []
    if isinstance(exs, list):
        for ex in exs:
            if not isinstance(ex, dict):
                continue
            q = (ex.get("question") or "").strip()
            choices = ex.get("choices") or []
            correct = (ex.get("correct") or "").strip()
            explanation_md = ex.get("explanation_md") or ""
            if not q or not correct:
                continue
            choices_json = json.dumps(choices, ensure_ascii=False) if isinstance(choices, list) else "[]"
            session.add(Exercise(
                lesson_id=lesson.id,
                question=q,
                choices_json=choices_json,
                correct_answer=correct,
                explanation_md=explanation_md
            ))
        session.commit()

    return lesson

# =========================
# PUBLIC ROUTES
# =========================
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    tpl = env.get_template("home.html")
    return tpl.render(
        title="English Learning",
        request=request,
        sections=SECTIONS
    )

@app.get("/section/{section_key}", response_class=HTMLResponse)
def section_page(request: Request, section_key: str, session: Session = Depends(get_session)):
    if section_key not in [s[0] for s in SECTIONS]:
        raise HTTPException(status_code=404, detail="Section not found")

    lessons = session.exec(
        select(Lesson).where(Lesson.section == section_key).order_by(Lesson.order_no, Lesson.id)
    ).all()

    label = dict(SECTIONS).get(section_key, section_key)

    tpl = env.get_template("section.html")
    return tpl.render(
        title=label,
        request=request,
        section_key=section_key,
        section_label=label,
        lessons=lessons
    )

@app.get("/lesson/{lesson_id}", response_class=HTMLResponse)
def lesson_view(request: Request, lesson_id: int, session: Session = Depends(get_session)):
    lesson = session.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    exercises = session.exec(select(Exercise).where(Exercise.lesson_id == lesson_id).order_by(Exercise.id)).all()

    tpl = env.get_template("lesson.html")
    return tpl.render(
        title=lesson.title,
        request=request,
        lesson=lesson,
        body_html=render_md(lesson.body_md),
        exercises=exercises
    )

@app.post("/exercise/{exercise_id}/check", response_class=JSONResponse)
def check_exercise(exercise_id: int, request: Request, answer: str = Form(""), session: Session = Depends(get_session)):
    ex = session.get(Exercise, exercise_id)
    if not ex:
        raise HTTPException(status_code=404, detail="Exercise not found")

    user = (answer or "").strip()
    correct = (ex.correct_answer or "").strip()

    # Simple normalization for text answers
    def norm(s: str) -> str:
        return " ".join(s.lower().split())

    ok = norm(user) == norm(correct)

    return {
        "ok": ok,
        "correct": ex.correct_answer,
        "explanation_html": render_md(ex.explanation_md) if ex.explanation_md else ""
    }

# =========================
# BOOKS (PDF) keep
# =========================
def list_pdf_books(q: str = "") -> List[Dict]:
    items: List[Dict] = []
    for p in sorted(PDF_APPROVED.glob("*.pdf")):
        title = p.stem
        if q and q.strip().lower() not in title.lower():
            continue
        items.append({"title": title, "filename": p.name})
    return items

def file_exists_approved(filename: str) -> bool:
    if not safe_name(filename):
        return False
    return (PDF_APPROVED / filename).exists()

@app.get("/books", response_class=HTMLResponse)
def books_page(request: Request, q: str = ""):
    tpl = env.get_template("section.html")
    # reuse template: show as a pseudo-section
    books = list_pdf_books(q=q)
    # convert to “lessons-like”
    lessons_like = [{"id": -1, "title": b["title"], "filename": b["filename"]} for b in books]
    return tpl.render(
        title="Books (PDF)",
        request=request,
        section_key="books",
        section_label="Books (PDF)",
        lessons=lessons_like,
        is_books=True,
        q=q
    )

@app.get("/book/{filename}", response_class=HTMLResponse)
def book_viewer(request: Request, filename: str):
    if not file_exists_approved(filename):
        raise HTTPException(status_code=404, detail="PDF not found")
    tpl = env.get_template("lesson.html")
    # Minimal viewer via iframe in same lesson template
    fake_lesson = {"title": filename, "section": "books"}
    return tpl.render(
        title=filename,
        request=request,
        lesson=fake_lesson,
        body_html=f'<iframe src="/pdf/{filename}#view=FitH" style="width:100%;height:80vh;border:0;"></iframe>',
        exercises=[]
    )

# =========================
# ADMIN ROUTES
# =========================
@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_get(request: Request, msg: str = ""):
    tpl = env.get_template("admin_login.html")
    return tpl.render(title="Admin — Login", request=request, msg=msg)

@app.post("/admin/login")
def admin_login_post(login: str = Form(...), password: str = Form(...)):
    if login.strip() == ADMIN_LOGIN and password == ADMIN_PASSWORD:
        resp = RedirectResponse("/admin", status_code=303)
        resp.set_cookie("itbook_admin", _sign("admin"), httponly=True, samesite="lax", max_age=60*60*12)
        return resp
    return RedirectResponse("/admin/login?msg=Wrong+login+or+password", status_code=303)

@app.get("/admin/logout")
def admin_logout():
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("itbook_admin")
    return resp

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, session: Session = Depends(get_session)):
    guard = require_admin(request)
    if guard:
        return guard

    # counts
    pending_files = sorted(CONTENT_PENDING.glob("*.json"))
    lessons_count = len(session.exec(select(Lesson)).all())

    tpl = env.get_template("admin.html")
    return tpl.render(
        title="Admin",
        request=request,
        pending_count=len(pending_files),
        lessons_count=lessons_count,
        content_root=str(CONTENT_ROOT),
        pending_path=str(CONTENT_PENDING),
        approved_path=str(CONTENT_APPROVED),
        pdf_pending=str(PDF_PENDING),
        pdf_approved=str(PDF_APPROVED)
    )

@app.get("/admin/import", response_class=HTMLResponse)
def admin_import(request: Request):
    guard = require_admin(request)
    if guard:
        return guard

    pending = sorted(CONTENT_PENDING.glob("*.json"))
    tpl = env.get_template("admin_import.html")
    return tpl.render(title="Admin — Import", request=request, pending=pending)

@app.post("/admin/import/approve")
def admin_import_approve(request: Request, filename: str = Form(...), session: Session = Depends(get_session)):
    guard = require_admin(request)
    if guard:
        return guard

    if not safe_name(filename) or not filename.lower().endswith(".json"):
        return RedirectResponse("/admin/import", status_code=303)

    src = CONTENT_PENDING / filename
    if not src.exists():
        return RedirectResponse("/admin/import", status_code=303)

    try:
        payload = read_json_file(src)
        lesson = upsert_lesson_from_payload(session, payload)
    except Exception:
        # you can add debug later
        return RedirectResponse("/admin/import?msg=Import+failed", status_code=303)

    # move file to approved
    dst = CONTENT_APPROVED / filename
    if dst.exists():
        dst.unlink()
    src.rename(dst)

    return RedirectResponse(f"/lesson/{lesson.id}", status_code=303)

@app.get("/admin/lesson/new", response_class=HTMLResponse)
def admin_lesson_new(request: Request):
    guard = require_admin(request)
    if guard:
        return guard
    tpl = env.get_template("admin_lesson_new.html")
    return tpl.render(title="Admin — New Lesson", request=request, sections=SECTIONS)

@app.post("/admin/lesson/new")
def admin_lesson_new_post(
    request: Request,
    section: str = Form(...),
    order_no: int = Form(0),
    title: str = Form(...),
    body_md: str = Form(""),
    session: Session = Depends(get_session)
):
    guard = require_admin(request)
    if guard:
        return guard

    lesson = Lesson(section=section.strip(), order_no=int(order_no), title=title.strip(), body_md=body_md)
    session.add(lesson)
    session.commit()
    session.refresh(lesson)
    return RedirectResponse(f"/lesson/{lesson.id}", status_code=303)

@app.post("/admin/exercise/add")
def admin_exercise_add(
    request: Request,
    lesson_id: int = Form(...),
    question: str = Form(...),
    choices: str = Form(""),   # newline separated
    correct: str = Form(...),
    explanation_md: str = Form(""),
    session: Session = Depends(get_session)
):
    guard = require_admin(request)
    if guard:
        return guard

    lesson = session.get(Lesson, lesson_id)
    if not lesson:
        return RedirectResponse("/admin", status_code=303)

    choices_list = [c.strip() for c in (choices or "").splitlines() if c.strip()]
    ex = Exercise(
        lesson_id=lesson_id,
        question=question.strip(),
        choices_json=json.dumps(choices_list, ensure_ascii=False),
        correct_answer=correct.strip(),
        explanation_md=explanation_md
    )
    session.add(ex)
    session.commit()
    return RedirectResponse(f"/lesson/{lesson_id}", status_code=303)

# -------------------------
# PDF APPROVE (keep)
# -------------------------
@app.get("/admin/pdfs", response_class=HTMLResponse)
def admin_pdfs(request: Request):
    guard = require_admin(request)
    if guard:
        return guard
    pending = sorted(PDF_PENDING.glob("*.pdf"))
    tpl = env.get_template("admin_import.html")
    # reuse import template for pdf
    return tpl.render(title="Admin — PDF Approve", request=request, pending=pending, is_pdf=True)

@app.post("/admin/pdfs/approve")
def approve_pdf(request: Request, filename: str = Form(...)):
    guard = require_admin(request)
    if guard:
        return guard

    if not safe_name(filename) or not filename.lower().endswith(".pdf"):
        return RedirectResponse("/admin/pdfs", status_code=303)

    src = PDF_PENDING / filename
    dst = PDF_APPROVED / filename
    if src.exists():
        if dst.exists():
            # rename
            i = 2
            while (PDF_APPROVED / f"{dst.stem} ({i}){dst.suffix}").exists():
                i += 1
            dst = PDF_APPROVED / f"{dst.stem} ({i}){dst.suffix}"
        src.rename(dst)

    return RedirectResponse("/admin/pdfs", status_code=303)
