from functools import lru_cache

from app.core.settings import BASE_DIR, DATABASE_URL
from app.infrastructure.persistence.sqlalchemy.session import (
    create_engine_and_session_factory,
    initialize_database,
)
from app.infrastructure.persistence.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork


@lru_cache(maxsize=1)
def get_session_factory():
    database_url = DATABASE_URL
    if database_url == "sqlite:///./instance/knowlayer.db":
        database_url = f"sqlite:///{BASE_DIR / 'instance' / 'knowlayer.db'}"
    engine, session_factory = create_engine_and_session_factory(database_url)
    initialize_database(engine)
    return session_factory


def create_unit_of_work() -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(get_session_factory())
