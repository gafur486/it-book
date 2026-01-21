from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin
from pygments.formatters import HtmlFormatter

from db import init_db, get_session
from models import Topic

app = FastAPI()
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
    if not text:
        return ""
    return md.render(text)

@app.on_event("startup")
def on_startup():
    init_db()
    # илова кардани seed, агар база холӣ бошад
    from sqlmodel import Session
    from db import engine
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
        s.add(Topic(
            grade=9,
            order_no=order_no,
            title=title,
            body_md=(
                f"**{title}** — ИН ҶО МАТНИ АСОСӢ БО 50–60 ҶУМЛА МЕОЯД.\n\n"
                "### ТАЪРИХ\n"
                "- 1969 — ARPANET (БАРОИ МАВЗӮЪҲОИ ШАБАКА)\n"
                "- 1991 — WWW (БАРОИ МАВЗӮЪҲОИ ВЕБ)\n\n"
                "### ФОИДА\n"
                "- ДАСТРАСӢ БА ИТТИЛООТ\n"
                "- КОРИ ГУРӮҲӢ\n"
            ),
            practical_md="- 3 ҚАДАМРО ИҶРО КУНЕД...\n- НАТИҶАРО НАВИСЕД...",
            groupwork_md="- ГУРӮҲ БА 3 НАФАР...\n- МАЪРУЗА ТАЙЁР КУНЕД...",
            questions_md="- САВОЛ 1?\n- САВОЛ 2?\n- САВОЛ 3?",
            code_md="```html\n<h1>САЛОМ</h1>\n```"
        ))

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

    idx = next((i for i,t in enumerate(all_topics) if t.id == topic_id), 0)
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

@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    tpl = env.get_template("admin.html")
    return tpl.render(title="Админ", request=request)

@app.post("/admin/create")
def admin_create(
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
