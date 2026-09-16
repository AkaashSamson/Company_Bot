from functools import lru_cache
import logging
import time

from app.core.settings import BASE_DIR, DATABASE_URL
from app.infrastructure.persistence.sqlalchemy.session import (
    create_engine_and_session_factory,
    initialize_database,
)
from app.infrastructure.persistence.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.persistence.rbac_seed import seed_rbac
from app.infrastructure.authentication.bootstrap import bootstrap_admin
from app.infrastructure.authentication.password_hasher import PasswordHasher


logger = logging.getLogger("knowlayer.persistence")


@lru_cache(maxsize=1)
def get_session_factory():
    database_url = DATABASE_URL
    if database_url == "sqlite:///./instance/knowlayer.db":
        database_url = f"sqlite:///{BASE_DIR / 'instance' / 'knowlayer.db'}"
    engine, session_factory = create_engine_and_session_factory(database_url)
    initialize_database(engine)
    bootstrap_admin(lambda: SqlAlchemyUnitOfWork(session_factory), PasswordHasher())
    seed_rbac(lambda: SqlAlchemyUnitOfWork(session_factory))
    return session_factory


def initialize_persistence(session_factory_factory=get_session_factory):
    """Warm the default session factory and provision the seed admin account.

    Runs eagerly during FastAPI startup so that the schema and bootstrap
    account are ready before the first request arrives, instead of being
    created lazily while a login request is already in flight.
    """
    last_error = None
    for attempt in range(1, 4):
        try:
            session_factory_factory()
            logger.info("database schema and seed data initialized")
            return
        except Exception as error:  # pragma: no cover - defensive startup handling
            last_error = error
            logger.warning("persistence initialization attempt %s failed: %s", attempt, error)
            time.sleep(0.5)
    raise RuntimeError("Failed to initialize persistence: %s" % last_error)


def create_unit_of_work() -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(get_session_factory())
