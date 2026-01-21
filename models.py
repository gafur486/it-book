from typing import Optional
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


class Topic(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    grade: int = Field(index=True)
    order_no: int = Field(index=True)
    title: str

    # матни асосӣ (Markdown)
    body_md: str

    # блокҳои иловагӣ (Markdown)
    practical_md: str = ""
    groupwork_md: str = ""
    questions_md: str = ""
    code_md: str = ""  # метавон чанд блоки код ҳам бо Markdown навишт


class ChatMessage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    # Агар баъдтар хоҳед: room = grade, group, class, ...
    room: str = Field(index=True, default="main")

    # номи шогирд
    name: str = Field(index=True, max_length=32)

    # матни паём
    text: str = Field(max_length=800)

    # вақти фиристодан (UTC)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        index=True,
    )
