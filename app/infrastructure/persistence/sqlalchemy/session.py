from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.persistence.sqlalchemy.models import Base


def create_engine_and_session_factory(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args, future=True)

    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine, sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def initialize_database(engine) -> None:
    Path("instance").mkdir(exist_ok=True)
    Base.metadata.create_all(engine)
    if engine.url.drivername.startswith("sqlite"):
        with engine.begin() as connection:
            columns = {column["name"] for column in inspect(connection).get_columns("users")}
            additions = {
                "username": "VARCHAR(128) NOT NULL DEFAULT ''",
                "password_representation": "VARCHAR(512) NOT NULL DEFAULT ''",
                "password_changed_at": "DATETIME NULL",
                "must_change_password": "BOOLEAN NOT NULL DEFAULT 0",
            }
            for name, definition in additions.items():
                if name not in columns:
                    connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} {definition}"))
            connection.execute(text("UPDATE users SET username = uid WHERE username = ''"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)"))
