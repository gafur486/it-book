from sqlmodel import SQLModel, create_engine, Session

engine = create_engine("sqlite:///it_book.db", echo=False)

def init_db():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session
