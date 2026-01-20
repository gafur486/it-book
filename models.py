from typing import Optional
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
