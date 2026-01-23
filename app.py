import os
import re
import hmac
import hashlib
from pathlib import Path
from typing import Optional, List, Dict

import httpx
from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin

from db import init_db, get_session, engine
from models import Topic

# =========================
# CONFIG
# =========================
# Муҳим: беҳтараш инҳоро ба ENV гузоред (Render / .env)
ADMIN_LOGIN = os.getenv("ADMIN_LOGIN", "abdu0004")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "12345678")

SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_SUPER_SECRET_KEY_2026").encode("utf-8")

# PDF root:
_default_desktop_pdf = str(Path.home() / "Desktop" / "pdf-book")
PDF_ROOT = Path(os.getenv("PDF_BOOK_DIR", _default_desktop_pdf))
if not PDF_ROOT.exists():
    PDF_ROOT = Path("pdf-book")
PDF_ROOT.mkdir(parents=True, exist_ok=True)

PDF_PENDING = PDF_ROOT / "pending"
PDF_APPROVED = PDF_ROOT / "approved"
PDF_PENDING.mkdir(parents=True, exist_ok=True)
PDF_APPROVED.mkdir(parents=True, exist_ok=True)

# =========================
# APP INIT
# =========================
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve ONLY approved PDFs
app.mount("/pdf", StaticFiles(directory=str(PDF_APPROVED)), name="pdf")

env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html", "xml"])
)

md = (
    MarkdownIt("commonmark", {"html": False, "linkify": True, "typographer": True})
    .use(tasklists_plugin)
)

def render_md(text: str) -> str:
    if not text:
        return ""
    return md.render(text)

# =========================
# AUTH (cookie with signature)
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
    cookie = request.cookies.get("itbook_admin", "")
    return _verify(cookie)

def require_admin(request: Request) -> Optional[RedirectResponse]:
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)
    return None

# =========================
# SEED
# =========================
def seed_grade9(s: Session) -> None:
    topics = [
        (1, "АСОСҲОИ ПОЙДОИШИ ШАБАКАҲОИ КОМПЮТЕРӢ"),
        (2, "ИНТЕРНЕТ"),
        (3, "ХАДАМОТИ АБРӢ. ХАДАМОТИ ЗАХИРАСОЗИИ АБРӢ"),
        (4, "АСОСҲОИ ЗАБОНИ HTML"),
    ]
    for order_no, title in topics:
        s.add(Topic(
            grade=9,
            order_no=order_no,
            title=title,
            body_md=(
                f"**{title}** — ИН ҶО МАТНИ АСОСӢ МЕОЯД.\n\n"
                "### ТАЪРИХ\n"
                "- 1969 — ARPANET\n"
                "- 1991 — WWW\n\n"
                "### ФОИДА\n"
                "- ДАСТРАСӢ БА ИТТИЛООТ\n"
                "- КОРИ ГУРӮҲӢ\n"
            ),
            practical_md="- 3 ҚАДАМРО ИҶРО КУНЕД...\n- НАТИҶАРО НАВИСЕД...",
            groupwork_md="- ГУРӮҲ БА 3 НАФАР...\n- МАЪРУЗА ТАЙЁР КУНЕД...",
            questions_md="- САВОЛ 1?\n- САВОЛ 2?\n- САВОЛ 3?",
            code_md="```html\n<h1>САЛОМ</h1>\n```"
        ))

@app.on_event("startup")
def on_startup():
    init_db()
    with Session(engine) as s:
        exists = s.exec(select(Topic).where(Topic.grade == 9)).first()
        if not exists:
            seed_grade9(s)
            s.commit()

# =========================
# PDF BOOKS
# =========================
_pdf_grade_re = re.compile(r"^\s*(\d{1,2})[\s_\-]+(.+?)\.pdf\s*$", re.IGNORECASE)

def _parse_pdf_name(filename: str) -> Dict:
    """
    Title derived from filename.
    Supported filename formats:
      "9 - Китоби тестӣ.pdf"
      "10_Алгоритмҳо.pdf"
      "11-Modeling.pdf"
    If no grade prefix -> grade = None
    """
    title = filename[:-4] if filename.lower().endswith(".pdf") else filename
    grade = None
    m = _pdf_grade_re.match(filename)
    if m:
        grade = int(m.group(1))
        title = m.group(2).strip()
    return {"title": title, "grade": grade}

def list_pdf_books(q: str = "") -> List[Dict]:
    items: List[Dict] = []
    for p in sorted(PDF_APPROVED.glob("*.pdf")):
        meta = _parse_pdf_name(p.name)
        title = meta["title"]
        grade = meta["grade"]

        if q and q.strip().lower() not in title.lower():
            continue

        items.append({
            "title": title,
            "filename": p.name,
            "grade": grade
        })
    return items

def file_exists_approved(filename: str) -> bool:
    if "/" in filename or "\\" in filename or ".." in filename:
        return False
    return (PDF_APPROVED / filename).exists()

# =========================
# ROUTES
# =========================
@app.get("/", response_class=HTMLResponse)
def home(request: Request, grade: int = 9, session: Session = Depends(get_session)):
    topics = session.exec(
        select(Topic).where(Topic.grade == grade).order_by(Topic.order_no)
    ).all()

    tpl = env.get_template("index.html")
    return tpl.render(
        title=f"Китобча — синфи {grade}",
        request=request,
        grade=grade,
        topics=topics,
        total=len(topics),
        topic=None,
        body_html="",
        practical_html="",
        groupwork_html="",
        questions_html="",
        code_html="",
        prev_id=None,
        next_id=None,
        active_id=None,
        uppercase=False,
    )

@app.get("/topic/{topic_id}", response_class=HTMLResponse)
def view_topic(request: Request, topic_id: int, session: Session = Depends(get_session)):
    topic = session.get(Topic, topic_id)
    if not topic:
        return RedirectResponse("/", status_code=303)

    all_topics = session.exec(
        select(Topic).where(Topic.grade == topic.grade).order_by(Topic.order_no)
    ).all()

    idx = next((i for i, t in enumerate(all_topics) if t.id == topic_id), 0)
    prev_id = all_topics[idx-1].id if idx > 0 else None
    next_id = all_topics[idx+1].id if idx < len(all_topics)-1 else None

    tpl = env.get_template("index.html")
    return tpl.render(
        title=topic.title,
        request=request,
        grade=topic.grade,
        topics=all_topics,
        total=len(all_topics),
        topic=topic,
        body_html=render_md(topic.body_md),
        practical_html=render_md(topic.practical_md),
        groupwork_html=render_md(topic.groupwork_md),
        questions_html=render_md(topic.questions_md),
        code_html=render_md(topic.code_md),
        prev_id=prev_id,
        next_id=next_id,
        active_id=topic_id,
        uppercase=False,
    )

@app.get("/partials/toc", response_class=HTMLResponse)
def partial_toc(request: Request, grade: int = 9, q: str = "", session: Session = Depends(get_session)):
    stmt = select(Topic).where(Topic.grade == grade)
    if q:
        q_like = f"%{q.strip()}%"
        stmt = stmt.where(Topic.title.ilike(q_like))

    topics = session.exec(stmt.order_by(Topic.order_no)).all()
    tpl = env.get_template("partials/toc.html")
    return tpl.render(request=request, topics=topics, active_id=None)

# -------- BOOKS (PDF) --------
@app.get("/books", response_class=HTMLResponse)
def books_page(request: Request, q: str = ""):
    books = list_pdf_books(q=q)
    tpl = env.get_template("books.html")
    return tpl.render(title="Китобҳо", request=request, books=books, q=q)

# PDF reader page (fullscreen-ish)
@app.get("/book/{filename}", response_class=HTMLResponse)
def book_viewer(request: Request, filename: str):
    if not file_exists_approved(filename):
        raise HTTPException(status_code=404, detail="PDF not found")

    meta = _parse_pdf_name(filename)
    tpl = env.get_template("pdf_viewer.html")
    return tpl.render(
        title=meta["title"],
        request=request,
        filename=filename,
        book_title=meta["title"],
        grade=meta["grade"],
    )

# -------- WIKI (Wikipedia) --------
@app.get("/wiki", response_class=HTMLResponse)
async def wiki_page(request: Request, q: str = ""):
    results = []
    error = None
    debug = None

    q = (q or "").strip()
    if q:
        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                api = "https://en.wikipedia.org/w/api.php"
                params = {
                    "action": "query",
                    "list": "search",
                    "srsearch": q,
                    "format": "json",
                    "utf8": 1,
                    "srlimit": 10,
                }
                headers = {
                    "User-Agent": "IT-Book/1.0 (contact: admin@local)",
                    "Accept": "application/json",
                }
                r = await client.get(api, params=params, headers=headers)
                r.raise_for_status()
                data = r.json()

            search_items = (((data or {}).get("query") or {}).get("search")) or []
            for it in search_items:
                title = it.get("title") or ""
                snippet_html = it.get("snippet") or ""
                snippet_clean = re.sub(r"<.*?>", "", snippet_html)
                page_url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
                results.append({"title": title, "snippet": snippet_clean, "url": page_url})

        except Exception as e:
            # Ба ҷои 500 — мо хаторо нишон медиҳем
            error = "Wikipedia ҳоло дастрас нест ё ҷустуҷӯ хато дод."
            debug = f"{type(e).__name__}: {str(e)}"

    tpl = env.get_template("wiki.html")
    return tpl.render(title="Wikipedia", request=request, q=q, results=results, error=error, debug=debug)

# -------- ADMIN AUTH --------
@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_get(request: Request, msg: str = ""):
    tpl = env.get_template("admin_login.html")
    return tpl.render(title="Админ — Login", request=request, msg=msg)

@app.post("/admin/login")
def admin_login_post(request: Request, login: str = Form(...), password: str = Form(...)):
    if login.strip() == ADMIN_LOGIN and password == ADMIN_PASSWORD:
        resp = RedirectResponse("/admin", status_code=303)
        resp.set_cookie(
            "itbook_admin",
            _sign("admin"),
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 12,
        )
        return resp
    return RedirectResponse("/admin/login?msg=Хато:+login+ё+парол", status_code=303)

@app.get("/admin/logout")
def admin_logout():
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("itbook_admin")
    return resp

@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    guard = require_admin(request)
    if guard:
        return guard
    tpl = env.get_template("admin.html")
    return tpl.render(
        title="Админ",
        request=request,
        pdf_root=str(PDF_ROOT),
        pending=str(PDF_PENDING),
        approved=str(PDF_APPROVED),
    )

# Pending PDFs list
@app.get("/admin/pdfs", response_class=HTMLResponse)
def admin_pdfs(request: Request):
    guard = require_admin(request)
    if guard:
        return guard

    pending = sorted(PDF_PENDING.glob("*.pdf"))
    tpl = env.get_template("admin_pdfs.html")
    return tpl.render(title="Админ — PDF", request=request, pending=pending)

@app.post("/admin/pdfs/approve")
def approve_pdf(request: Request, filename: str = Form(...)):
    guard = require_admin(request)
    if guard:
        return guard

    if "/" in filename or "\\" in filename or ".." in filename:
        return RedirectResponse("/admin/pdfs", status_code=303)

    src = PDF_PENDING / filename
    dst = PDF_APPROVED / filename
    if src.exists():
        # Агар файл бо ҳамин ном дар approved бошад, номи нав диҳем:
        if dst.exists():
            stem = dst.stem
            suffix = dst.suffix
            i = 2
            while (PDF_APPROVED / f"{stem} ({i}){suffix}").exists():
                i += 1
            dst = PDF_APPROVED / f"{stem} ({i}){suffix}"
        src.rename(dst)

    return RedirectResponse("/admin/pdfs", status_code=303)

# Create topic
@app.post("/admin/create")
def admin_create(
    request: Request,
    grade: int = Form(...),
    order_no: int = Form(...),
    title: str = Form(...),
    body_md: str = Form(...),
    practical_md: str = Form(""),
    groupwork_md: str = Form(""),
    questions_md: str = Form(""),
    code_md: str = Form(""),
    session: Session = Depends(get_session),
):
    guard = require_admin(request)
    if guard:
        return guard

    t = Topic(
        grade=grade,
        order_no=order_no,
        title=title.strip(),
        body_md=body_md.strip(),
        practical_md=practical_md.strip(),
        groupwork_md=groupwork_md.strip(),
        questions_md=questions_md.strip(),
        code_md=code_md.strip(),
    )
    session.add(t)
    session.commit()
    session.refresh(t)
    return RedirectResponse(f"/topic/{t.id}", status_code=303)
