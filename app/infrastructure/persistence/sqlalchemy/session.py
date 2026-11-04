from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.persistence.sqlalchemy.models import Base


def create_engine_and_session_factory(database_url: str):
    connect_args = {"check_same_thread": False, "timeout": 30.0} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args, future=True)

    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def configure_sqlite_pragmas(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

    return engine, sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def initialize_database(engine) -> None:
    Path("instance").mkdir(exist_ok=True)
    Base.metadata.create_all(engine)
    # TODO(tech-debt): Remove once teammates have migrated their local SQLite DBs
    from app.infrastructure.persistence.sqlalchemy.migrations import apply_legacy_schema_migration
    apply_legacy_schema_migration(engine)
