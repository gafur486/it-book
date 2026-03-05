from typing import Optional
from sqlmodel import SQLModel, Field


class Lesson(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    section: str
    title: str
    body: str


class Exercise(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    lesson_id: int
    question: str
    answer: str
