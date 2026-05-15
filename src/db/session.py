from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from config import ROOT_DIR, ensure_runtime_dirs, settings
from src.db.migrations import run_sqlite_migrations


def _db_url() -> str:
    if settings.app_db_url.startswith("sqlite:///"):
        raw_path = settings.app_db_url.replace("sqlite:///", "", 1)
        db_path = Path(raw_path)
        if not db_path.is_absolute():
            db_path = ROOT_DIR / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db_path.as_posix()}"
    return settings.app_db_url


engine = create_engine(_db_url(), echo=False, connect_args={"check_same_thread": False})


def sqlite_db_path() -> Path:
    if engine.url.get_backend_name() != "sqlite" or not engine.url.database:
        raise RuntimeError("Dashboard SQL reads require a SQLite APP_DB_URL.")
    return Path(engine.url.database).resolve()


def init_db() -> None:
    ensure_runtime_dirs()
    SQLModel.metadata.create_all(engine)
    if engine.url.get_backend_name() == "sqlite":
        with engine.begin() as conn:
            run_sqlite_migrations(conn)


def get_session() -> Session:
    return Session(engine)
