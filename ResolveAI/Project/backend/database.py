from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os

_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/support.db")

# Enable WAL mode for SQLite (better concurrent reads)
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    if DATABASE_URL.startswith("sqlite:///"):
        db_path = DATABASE_URL.replace("sqlite:///", "", 1)
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    from backend import models  # noqa: F401 — registers all models
    Base.metadata.create_all(bind=engine)
    _migrate_schema_if_needed()
    _create_fts_index()
    from backend.seed import seed_if_empty

    seed_if_empty()


def _migrate_schema_if_needed():
    """Lightweight SQLite migrations for existing local databases."""
    if not DATABASE_URL.startswith("sqlite:///"):
        return
    with engine.connect() as conn:
        cols = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(users)")).fetchall()
        }
        if "google_sub" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN google_sub TEXT"))
        if "password_hash" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN password_hash TEXT"))
        if "picture" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN picture TEXT"))
        conn.commit()

def _create_fts_index():
    """Create SQLite FTS5 virtual table for fast KB search."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts
            USING fts5(
                title, content, tags,
                content='knowledge_base',
                content_rowid='id'
            )
        """))
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS kb_ai AFTER INSERT ON knowledge_base BEGIN
                INSERT INTO kb_fts(rowid, title, content, tags)
                VALUES (new.id, new.title, new.content, new.tags);
            END
        """))
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS kb_au AFTER UPDATE ON knowledge_base BEGIN
                INSERT INTO kb_fts(kb_fts, rowid, title, content, tags)
                VALUES ('delete', old.id, old.title, old.content, old.tags);
                INSERT INTO kb_fts(rowid, title, content, tags)
                VALUES (new.id, new.title, new.content, new.tags);
            END
        """))
        conn.commit()
