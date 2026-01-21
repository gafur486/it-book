from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field


class Topic(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    grade: int = Field(index=True)
    order_no: int = Field(index=True)
    title: str = Field(index=True)

    body_md: str
    practical_md: str = ""
    groupwork_md: str = ""
    questions_md: str = ""
    code_md: str = ""


class Book(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    grade: Optional[int] = Field(default=None, index=True)

    # relative path inside /static, e.g. "books/xxxx.pdf"
    file_path: str

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
