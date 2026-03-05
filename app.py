from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from db import init_db, get_session, engine
from models import Lesson, Exercise

from jinja2 import Environment, FileSystemLoader

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

env = Environment(loader=FileSystemLoader("templates"))

@app.on_event("startup")
def start():
    init_db()
    with Session(engine) as s:
        if not s.exec(select(Lesson)).first():
            lesson = Lesson(
                section="grammar",
                title="Present Simple",
                body="We use Present Simple for daily actions."
            )
            s.add(lesson)
            s.commit()
            s.refresh(lesson)

            ex = Exercise(
                lesson_id=lesson.id,
                question="I ___ to school every day.",
                answer="go"
            )
            s.add(ex)
            s.commit()

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    tpl = env.get_template("home.html")
    return tpl.render(request=request)

@app.get("/section/{section}", response_class=HTMLResponse)
def section(section: str, request: Request):
    with Session(engine) as s:
        lessons = s.exec(select(Lesson).where(Lesson.section == section)).all()
    tpl = env.get_template("section.html")
    return tpl.render(request=request, lessons=lessons)

@app.get("/lesson/{lesson_id}", response_class=HTMLResponse)
def lesson(lesson_id: int, request: Request):
    with Session(engine) as s:
        lesson = s.get(Lesson, lesson_id)
        exercises = s.exec(
            select(Exercise).where(Exercise.lesson_id == lesson_id)
        ).all()
    tpl = env.get_template("lesson.html")
    return tpl.render(
        request=request,
        lesson=lesson,
        exercises=exercises
    )

@app.post("/check/{ex_id}")
def check(ex_id: int, answer: str = Form(...)):
    with Session(engine) as s:
        ex = s.get(Exercise, ex_id)
        ok = answer.strip().lower() == ex.answer.lower()
    return {"ok": ok, "correct": ex.answer}
