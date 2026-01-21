import os
from fastapi import FastAPI, Request, Depends, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from jinja2 import Environment, FileSystemLoader, select_autoescape

from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin

from pygments import highlight
from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.formatters import HtmlFormatter

from db import init_db, get_session, engine
from models import Topic, ChatMessage


# ----------------------------
# App + Static + Templates
# ----------------------------
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html", "xml"]),
)

# ----------------------------
# Markdown + code highlight
# ----------------------------
formatter = HtmlFormatter(nowrap=False)
PYGMENTS_CSS = formatter.get_style_defs(".highlight")

md = MarkdownIt("commonmark", {"html": False, "linkify": True, "typographer": True})
md.use(tasklists_plugin)

def _render_fence(renderer, tokens, idx, options, env_):
    token = tokens[idx]
    info = (token.info or "").strip()
    lang = info.split()[0] if info else ""
    code = token.content

    try:
        lexer = get_lexer_by_name(lang) if lang else TextLexer()
    except Exception:
        lexer = TextLexer()

    return highlight(code, lexer, formatter)

md.add_render_rule("fence", _render_fence)

def md_to_html(text: str) -> str:
    if not text:
        return ""
    return md.render(text)


# ----------------------------
# Admin guard (ADMIN_KEY)
# ----------------------------
ADMIN_KEY = os.getenv("ADMIN_KEY", "").strip()

def require_admin(request: Request) -> None:
    # Агар ADMIN_KEY монда нашуда бошад -> дар dev админ кушода мемонад
    if not ADMIN_KEY:
        return
    key = request.query_params.get("key", "")
    if key != ADMIN_KEY:
        raise PermissionError("Unauthorized")


# ----------------------------
# Startup: DB init + seed
# ----------------------------
@app.on_event("startup")
def on_startup():
    init_db()

    # Seed танҳо агар синфи 9 холӣ бошад
    with Session(engine) as s:
        exists = s.exec(select(Topic).where(Topic.grade == 9)).first()
        if not exists:
            seed_grade9(s)
            s.commit()


def seed_grade9(s: Session) -> None:
    topics = [
        (1, "АСОСҲОИ ПОЙДОИШИ ШАБАКАҲОИ КОМПЮТЕРӢ"),
        (2, "ИНТЕРНЕТ"),
        (3, "ХАДАМОТИ АБРӢ. ХАДАМОТИ ЗАХИРАСОЗИИ АБРӢ"),
        (4, "АСОСҲОИ ЗАБОНИ HTML"),
    ]
    for order_no, title in topics:
        s.add(
            Topic(
                grade=9,
                order_no=order_no,
                title=title,
                body_md=f"**{title}** — ИН ҶО МАТНИ АСОСӢ МЕОЯД.\n\n- Нуқта 1\n- Нуқта 2",
                practical_md="- 3 ҚАДАМРО ИҶРО КУНЕД...\n- НАТИҶАРО НАВИСЕД...",
                groupwork_md="- ГУРӮҲ БА 3 НАФАР...\n- МАЪРУЗА ТАЙЁР КУНЕД...",
                questions_md="- САВОЛ 1?\n- САВОЛ 2?\n- САВОЛ 3?",
                code_md="```html\n<h1>САЛОМ</h1>\n```",
            )
        )


# ----------------------------
# Home + Topic pages
# ----------------------------
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
        admin_key=request.query_params.get("key", ""),
        pygments_css=PYGMENTS_CSS,
    )


@app.get("/topic/{topic_id}", response_class=HTMLResponse)
def topic_page(
    request: Request,
    topic_id: int,
    session: Session = Depends(get_session),
    uppercase: bool = False,
):
    topic = session.get(Topic, topic_id)
    if not topic:
        return PlainTextResponse("Topic not found", status_code=404)

    grade = topic.grade
    topics = session.exec(
        select(Topic).where(Topic.grade == grade).order_by(Topic.order_no)
    ).all()

    ids = [t.id for t in topics]
    idx = ids.index(topic_id)
    prev_id = ids[idx - 1] if idx > 0 else None
    next_id = ids[idx + 1] if idx < len(ids) - 1 else None

    tpl = env.get_template("index.html")
    return tpl.render(
        title=f"{topic.title} — синфи {grade}",
        request=request,
        grade=grade,
        topics=topics,
        total=len(topics),
        topic=topic,
        body_html=md_to_html(topic.body_md),
        practical_html=md_to_html(topic.practical_md),
        groupwork_html=md_to_html(topic.groupwork_md),
        questions_html=md_to_html(topic.questions_md),
        code_html=md_to_html(topic.code_md),
        prev_id=prev_id,
        next_id=next_id,
        active_id=topic_id,
        uppercase=uppercase,
        admin_key=request.query_params.get("key", ""),
        pygments_css=PYGMENTS_CSS,
    )


# ----------------------------
# HTMX partial: TOC (search)
# ----------------------------
@app.get("/partials/toc", response_class=HTMLResponse)
def partial_toc(
    request: Request,
    grade: int = 9,
    q: str = "",
    session: Session = Depends(get_session),
):
    q = (q or "").strip().lower()
    topics = session.exec(
        select(Topic).where(Topic.grade == grade).order_by(Topic.order_no)
    ).all()

    if q:
        topics = [t for t in topics if q in t.title.lower()]

    tpl = env.get_template("partials/toc.html")
    return tpl.render(
        request=request,
        topics=topics,
        active_id=None,
    )


# ----------------------------
# Admin (protected)
# ----------------------------
@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    try:
        require_admin(request)
    except PermissionError:
        return PlainTextResponse("Unauthorized", status_code=403)

    tpl = env.get_template("admin.html")
    return tpl.render(
        title="Админ",
        request=request,
        admin_key=request.query_params.get("key", ""),
        pygments_css=PYGMENTS_CSS,
    )


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
    try:
        require_admin(request)
    except PermissionError:
        return PlainTextResponse("Unauthorized", status_code=403)

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

    k = request.query_params.get("key", "")
    suffix = f"?key={k}" if k else ""
    return RedirectResponse(f"/topic/{t.id}{suffix}", status_code=303)


# ----------------------------
# Chat: manager + page + websocket
# ----------------------------
class ConnectionManager:
    def __init__(self) -> None:
        self.active: dict[str, set[WebSocket]] = {}

    async def connect(self, room: str, ws: WebSocket) -> None:
        await ws.accept()
        self.active.setdefault(room, set()).add(ws)

    def disconnect(self, room: str, ws: WebSocket) -> None:
        if room in self.active:
            self.active[room].discard(ws)
            if not self.active[room]:
                self.active.pop(room, None)

    async def broadcast(self, room: str, message: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self.active.get(room, set()):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(room, ws)


manager = ConnectionManager()


@app.get("/chat", response_class=HTMLResponse)
def chat_page(
    request: Request,
    room: str = "main",
    session: Session = Depends(get_session),
):
    msgs = session.exec(
        select(ChatMessage)
        .where(ChatMessage.room == room)
        .order_by(ChatMessage.created_at.desc())
        .limit(80)
    ).all()
    msgs = list(reversed(msgs))

    tpl = env.get_template("chat.html")
    return tpl.render(
        title="Чат",
        request=request,
        room=room,
        messages=msgs,
        admin_key=request.query_params.get("key", ""),
        pygments_css=PYGMENTS_CSS,
    )


@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket, room: str = "main"):
    await manager.connect(room, ws)

    try:
        while True:
            data = await ws.receive_json()
            name = (data.get("name") or "").strip()[:32]
            text = (data.get("text") or "").strip()[:800]
            if not name or not text:
                continue

            with Session(engine) as s:
                m = ChatMessage(room=room, name=name, text=text)
                s.add(m)
                s.commit()
                s.refresh(m)

                payload = {
                    "id": m.id,
                    "room": m.room,
                    "name": m.name,
                    "text": m.text,
                    "created_at": m.created_at.isoformat(),
                }

            await manager.broadcast(room, payload)

    except WebSocketDisconnect:
        manager.disconnect(room, ws)
    except Exception:
        manager.disconnect(room, ws)
