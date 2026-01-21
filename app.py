import os
import re
import uuid
from pathlib import Path

import requests
from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, Header, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin

from db import init_db, get_session, engine
from models import Topic, Book


# ---------------- App / Static ----------------
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html", "xml"]),
)

md = (
    MarkdownIt("commonmark", {"html": False, "linkify": True, "typographer": True})
    .use(tasklists_plugin)
)

def render_md(text: str) -> str:
    if not text:
        return ""
    return md.render(text)


# ---------------- Config ----------------
BOOKS_DIR = Path("static/books")
BOOKS_DIR.mkdir(parents=True, exist_ok=True)

# Put this in Render env vars
# ADMIN_TOKEN=some_strong_secret
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

WIKI_TIMEOUT = 4


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


# ---------------- Pages: Topics ----------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request, grade: int = 9, session: Session = Depends(get_session)):
    topics = session.exec(
        select(Topic).where(Topic.grade == grade).order_by(Topic.order_no)
    ).all()

    tpl = env.get_template("index.html")
    return tpl.render(
        title=f"Китоб — синфи {grade}",
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
    prev_id = all_topics[idx - 1].id if idx > 0 else None
    next_id = all_topics[idx + 1].id if idx < len(all_topics) - 1 else None

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


# ---------------- Wikipedia (partial) ----------------
def _clean_q(q: str) -> str:
    q = (q or "").strip()
    q = re.sub(r"\s+", " ", q)
    return q[:80]

@app.get("/partials/wiki", response_class=HTMLResponse)
def partial_wiki(request: Request, wq: str = "", lang: str = "tg"):
    q = _clean_q(wq)
    if not q:
        tpl = env.get_template("partials/wiki.html")
        return tpl.render(q="", results=[], error=None)

    # Allow only tg/ru to avoid weird endpoints
    wiki_lang = "tg" if lang not in ("tg", "ru") else lang

    try:
        url = f"https://{wiki_lang}.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": q,
            "format": "json",
            "utf8": 1,
            "srlimit": 5,
        }
        r = requests.get(url, params=params, timeout=WIKI_TIMEOUT)
        r.raise_for_status()
        data = r.json()

        results = []
        for item in data.get("query", {}).get("search", []):
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            snippet = re.sub(r"<.*?>", "", snippet)
            page_url = f"https://{wiki_lang}.wikipedia.org/wiki/" + title.replace(" ", "_")
            results.append({"title": title, "snippet": snippet, "url": page_url})

        tpl = env.get_template("partials/wiki.html")
        return tpl.render(q=q, results=results, error=None)

    except Exception:
        tpl = env.get_template("partials/wiki.html")
        return tpl.render(q=q, results=[], error="Хатои ҷустуҷӯ дар Википедия. Баъдтар такрор кунед.")


# ---------------- Books page + search ----------------
@app.get("/books", response_class=HTMLResponse)
def books_page(request: Request, q: str = "", session: Session = Depends(get_session)):
    stmt = select(Book)
    if q:
        stmt = stmt.where(Book.title.ilike(f"%{q.strip()}%"))
    books = session.exec(stmt.order_by(Book.created_at.desc())).all()

    tpl = env.get_template("books.html")
    return tpl.render(
        title="Китобҳо",
        request=request,
        q=q,
        books=books,
    )


# ---------------- Upload PDF books (admin token) ----------------
@app.post("/admin/books/upload")
def upload_book(
    title: str = Form(...),
    grade: int | None = Form(None),
    pdf: UploadFile = File(...),
    x_admin_token: str | None = Header(default=None),
    session: Session = Depends(get_session),
):
    if not ADMIN_TOKEN or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not pdf.filename or not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF allowed")

    safe_id = uuid.uuid4().hex
    filename = f"{safe_id}.pdf"
    save_path = BOOKS_DIR / filename

    with save_path.open("wb") as f:
        f.write(pdf.file.read())

    b = Book(
        title=title.strip(),
        grade=grade,
        file_path=f"books/{filename}",
    )
    session.add(b)
    session.commit()
    session.refresh(b)

    return {"ok": True, "id": b.id, "title": b.title, "url": f"/static/{b.file_path}"}
