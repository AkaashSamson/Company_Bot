import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.domain.entities.organization_models import Department, Project, User
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.domain.services.business_id_generator import build_business_id_generator
from app.infrastructure.persistence.sqlalchemy.session import initialize_database
from app.infrastructure.persistence.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork
from app.use_cases.organization.document_management import DocumentManagementService


def _session_factory(database_url):
    engine = create_engine(database_url, connect_args={"check_same_thread": False, "timeout": 30})
    return engine, sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def _prepare_database(database_url):
    engine, _ = _session_factory(database_url)
    initialize_database(engine)
    engine.dispose()
    return engine


def test_concurrent_allocations_from_separate_connections_never_duplicate():
    threads = 8
    each = 25
    with tempfile.TemporaryDirectory() as directory:
        database_url = f"sqlite:///{os.path.join(directory, 'concurrency.db')}"
        _prepare_database(database_url)
        generator = build_business_id_generator(
            user_prefix="MSS", department_prefix="DEPT", project_prefix="PROJ", document_prefix="DOC"
        )

        def worker(_):
            engine, session_factory = _session_factory(database_url)
            try:
                batch = []
                for _ in range(each):
                    with SqlAlchemyUnitOfWork(session_factory) as uow:
                        batch.append(generator.next(uow, "project"))
                        uow.commit()
                return batch
            finally:
                engine.dispose()

        with ThreadPoolExecutor(max_workers=threads) as pool:
            batches = list(pool.map(worker, range(threads)))

    values = [value for batch in batches for value in batch]
    assert len(values) == threads * each
    assert len(set(values)) == len(values)
    numbers = sorted(int(value.split("-")[1]) for value in values)
    assert numbers == list(range(1, threads * each + 1))


def test_persisted_counter_continues_after_engine_restart():
    with tempfile.TemporaryDirectory() as directory:
        database_url = f"sqlite:///{os.path.join(directory, 'persist.db')}"
        _prepare_database(database_url)
        generator = build_business_id_generator(
            user_prefix="MSS", department_prefix="DEPT", project_prefix="PROJ", document_prefix="DOC"
        )

        engine, session_factory = _session_factory(database_url)
        try:
            with SqlAlchemyUnitOfWork(session_factory) as uow:
                for _ in range(3):
                    generator.next(uow, "document")
                uow.commit()
        finally:
            engine.dispose()

        engine, session_factory = _session_factory(database_url)
        try:
            with SqlAlchemyUnitOfWork(session_factory) as uow:
                allocated = generator.next(uow, "document")
                uow.commit()
        finally:
            engine.dispose()

        assert allocated == "DOC-004"


def test_document_ids_are_not_reused_after_document_deletion():
    with tempfile.TemporaryDirectory() as directory:
        database_url = f"sqlite:///{os.path.join(directory, 'delete.db')}"
        _prepare_database(database_url)
        engine, session_factory = _session_factory(database_url)
        try:
            with SqlAlchemyUnitOfWork(session_factory) as uow:
                uow.departments.save(Department("d1", "Engineering"))
                uow.users.save(User("admin", "Admin", "admin@example.com", "Admin", "d1"))
                uow.projects.save(Project("p1", "Project One", "d1"))
                uow.commit()

            service = DocumentManagementService(lambda: SqlAlchemyUnitOfWork(session_factory))
            first = service.register_document(AuthenticatedPrincipal("admin"), document_name="A", project_id="p1")
            second = service.register_document(AuthenticatedPrincipal("admin"), document_name="B", project_id="p1")
            third = service.register_document(AuthenticatedPrincipal("admin"), document_name="C", project_id="p1")
            assert [first.document_id, second.document_id, third.document_id] == ["DOC-001", "DOC-002", "DOC-003"]

            service.delete_document(AuthenticatedPrincipal("admin"), third.document_id)

            fourth = service.register_document(AuthenticatedPrincipal("admin"), document_name="D", project_id="p1")
            assert fourth.document_id == "DOC-004"
        finally:
            engine.dispose()