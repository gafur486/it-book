import os
import hmac
import hashlib
from typing import Optional

from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from sqlmodel import Session, select

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin

from db import init_db, get_session, engine
from models import Topic, Book

# ---------------------------
# Config (ADMIN + Sessions)
# ---------------------------

# 1) Барои cookie-session лозим аст (ХУБ аст дар ENV нигоҳ доред)
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_TO_A_LONG_RANDOM_SECRET")

# 2) Admin credentials: беҳтараш ENV
ADMIN_USER = os.getenv("ADMIN_USER", "abdu004")
ADMIN_PASS = os.getenv("ADMIN_PASS", "12345678")

def _hash_pw(pw: str, salt: bytes) -> bytes:
    # PBKDF2 (бе китобхонаҳои иловагӣ)
    return hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, 120_000, dklen=32)

# Барои ин мисол salt-ро доимӣ мегузорем (аммо беҳтар аст аз ENV)
_ADMIN_SALT = os.getenv("ADMIN_SALT", "itbook_salt_v1").encode("utf-8")
_ADMIN_HASH = _hash_pw(ADMIN_PASS, _ADMIN_SALT)

def verify_admin(user: str, pw: str) -> bool:
    if user != ADMIN_USER:
        return False
    test = _hash_pw(pw, _ADMIN_SALT)
    return hmac.compare_digest(test, _ADMIN_HASH)

def require_admin(request: Request):
    if not request.session.get("is_admin"):
        # redirect to login
        raise HTTPException(status_code=401, detail="Unauthorized")

# ---------------------------
# App
# ---------------------------

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.mount("/static", StaticFiles(directory="static"), name="static")

env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html", "xml"])
)

md = (
    MarkdownIt("commonmark", {"html": False, "linkify": True, "typographer": True})
    .use(tasklists_plugin)
)

def render_md(text: str) -> str:
    return md.render(text or "")

@app.on_event("startup")
def on_startup():
    init_db()
    with Session(engine) as s:
        any_topic = s.exec(select(Topic).limit(1)).first()
        if not any_topic:
            seed_topics(s)
            seed_books(s)
            s.commit()

def seed_topics(s: Session) -> None:
    topics = [
        (7, 1, "МУҚАДДИМА. ҚОИДАҲОИ БЕХАТАРӢ"),
        (8, 1, "АСОСҲОИ КОМПЮТЕР"),
        (9, 1, "АСОСҲОИ ПОЙДОИШИ ШАБАКАҲОИ КОМПЮТЕРӢ"),
        (9, 2, "ИНТЕРНЕТ"),
        (9, 3, "ХАДАМОТИ АБРӢ. ХАДАМОТИ ЗАХИРАСОЗИИ АБРӢ"),
        (9, 4, "АСОСҲОИ ЗАБОНИ HTML"),
        (10, 1, "АЛГОРИТМҲО ВА БАРНОМАСОЗӢ (ОҒОЗ)"),
        (11, 1, "ЛОИҲАСОЗИИ НИЗОМҲОИ ИТТИЛООТӢ"),
    ]
    for grade, order_no, title in topics:
        s.add(Topic(
            grade=grade,
            order_no=order_no,
            title=title,
            body_md=(
                f"## {title}\n\n"
                "Ин ҷо матни мавзӯъ (Markdown) ҷойгир мешавад.\n\n"
                "### Нуқтаҳои асосӣ\n"
                "- Таъриф\n- Мисол\n- Хулоса\n"
            ),
            practical_md="### Кори амалӣ\n- Қадами 1\n- Қадами 2\n",
            groupwork_md="### Кори гурӯҳӣ\n- Гурӯҳ 3–4 нафар\n",
            questions_md="### Саволҳо\n1) ...?\n2) ...?\n",
            code_md="```html\n<h1>Салом</h1>\n```"
        ))

def seed_books(s: Session) -> None:
    demo = [
        ("Китоби тестӣ (намуна)", "books/test.pdf", 9),
    ]
    for title, file_path, grade in demo:
        s.add(Book(title=title, file_path=file_path, grade=grade))

# ---------------------------
# Public pages
# ---------------------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request, grade: int = 9, session: Session = Depends(get_session)):
    topics = session.exec(
        select(Topic).where(Topic.grade == grade).order_by(Topic.order_no)
    ).all()

    tpl = env.get_template("index.html")
    return tpl.render(
        request=request,
        page_title=f"Китобча — синфи {grade}",
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
        is_admin=bool(request.session.get("is_admin")),
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
        request=request,
        page_title=topic.title,
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
        is_admin=bool(request.session.get("is_admin")),
    )

@app.get("/partials/toc", response_class=HTMLResponse)
def partial_toc(request: Request, grade: int = 9, q: str = "", session: Session = Depends(get_session)):
    stmt = select(Topic).where(Topic.grade == grade)
    if q.strip():
        stmt = stmt.where(Topic.title.ilike(f"%{q.strip()}%"))
    topics = session.exec(stmt.order_by(Topic.order_no)).all()

    tpl = env.get_template("partials/toc.html")
    return tpl.render(request=request, topics=topics, active_id=None)

@app.get("/books", response_class=HTMLResponse)
def books(request: Request, q: str = "", session: Session = Depends(get_session)):
    stmt = select(Book)
    if q.strip():
        stmt = stmt.where(Book.title.ilike(f"%{q.strip()}%"))
    items = session.exec(stmt.order_by(Book.id.desc())).all()

    tpl = env.get_template("books.html")
    return tpl.render(request=request, page_title="Китобҳо", books=items, q=q, is_admin=bool(request.session.get("is_admin")))

# ---------------------------
# Auth (Login/Logout)
# ---------------------------

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/admin"):
    tpl = env.get_template("login.html")
    return tpl.render(request=request, page_title="Login", error=None, next=next)

@app.post("/login")
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/admin"),
):
    if verify_admin(username.strip(), password):
        request.session["is_admin"] = True
        return RedirectResponse(next or "/admin", status_code=303)

    tpl = env.get_template("login.html")
    return HTMLResponse(
        tpl.render(request=request, page_title="Login", error="Логин ё парол нодуруст аст.", next=next),
        status_code=401
    )

@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)

# ---------------------------
# Admin (Protected)
# ---------------------------

@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    if not request.session.get("is_admin"):
        return RedirectResponse("/login?next=/admin", status_code=303)
    tpl = env.get_template("admin.html")
    return tpl.render(request=request, page_title="Админ", is_admin=True)

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
    if not request.session.get("is_admin"):
        return RedirectResponse("/login?next=/admin", status_code=303)

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

@app.post("/admin/book")
def admin_add_book(
    request: Request,
    title: str = Form(...),
    file_path: str = Form(...),
    grade: int = Form(0),
    session: Session = Depends(get_session),
):
    if not request.session.get("is_admin"):
        return RedirectResponse("/login?next=/admin", status_code=303)

    b = Book(title=title.strip(), file_path=file_path.strip(), grade=(grade or None))
    session.add(b)
    session.commit()
    return RedirectResponse("/books", status_code=303)
