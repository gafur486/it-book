from __future__ import annotations
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship


class Lesson(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    # sections: phrases, words, alphabet, verbs, grammar, reading, listening, etc.
    section: str = Field(index=True)
    order_no: int = Field(index=True)
    title: str

    body_md: str = ""

    exercises: List["Exercise"] = Relationship(back_populates="lesson")


class Exercise(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    lesson_id: int = Field(foreign_key="lesson.id", index=True)

    question: str
    # JSON string: ["A","B","C","D"]  OR empty for free-text
    choices_json: str = "[]"
    # correct answer: for MCQ -> exact choice string, for text -> normalized check
    correct_answer: str

    explanation_md: str = ""

    lesson: Optional[Lesson] = Relationship(back_populates="exercises")
