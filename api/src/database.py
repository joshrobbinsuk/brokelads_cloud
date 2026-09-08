from datetime import datetime
from typing import Generator
from uuid import uuid4

from sqlalchemy import create_engine, String, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from src.settings import DATABASE_URL

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

# Neon autosuspends and kills pooled connections; pre-ping reconnects instead
# of handing the first request after a quiet spell a dead socket (500).
# Routes run on FastAPI's 40-thread pool, so the connection pool — not the event
# loop — is the limiter: 20 is ample for this app and leaves two instances well
# inside Neon's ceiling at 0.25 CU. connect_timeout matters because pre-ping
# makes reconnects routine, and an unreachable address otherwise costs the
# kernel's full SYN-retry cycle (~127s, as on 2026-09-01) with no error at all.
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=10,
    pool_timeout=10,
    connect_args={"connect_timeout": 5},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class BaseModel(DeclarativeBase):
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4()), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
