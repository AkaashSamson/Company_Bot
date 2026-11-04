from unittest.mock import MagicMock
from app.domain.ports.authorization_service import AuthenticatedPrincipal
from app.infrastructure.logging.database_employee_id_provider import DatabaseEmployeeIdProvider


def test_default_fallback_anonymous():
    provider = DatabaseEmployeeIdProvider()
    assert provider.get_employee_id(None) == "anonymous"
    assert provider.get_employee_id("") == "anonymous"


def test_dict_with_employee_id():
    provider = DatabaseEmployeeIdProvider()
    assert provider.get_employee_id({"employee_id": "MSS123"}) == "MSS123"


def test_authenticated_principal_db_lookup():
    mock_user = MagicMock()
    mock_user.employee_id = "MSS777"
    mock_user.uid = "USR001"

    mock_uow = MagicMock()
    mock_uow.users.get_by_uid.return_value = mock_user

    mock_uow_factory = MagicMock()
    mock_uow_factory.return_value.__enter__.return_value = mock_uow

    provider = DatabaseEmployeeIdProvider(unit_of_work_factory=mock_uow_factory)
    principal = AuthenticatedPrincipal(uid="USR001")

    assert provider.get_employee_id(principal) == "MSS777"
    mock_uow.users.get_by_uid.assert_called_once_with("USR001")


def test_db_lookup_fallback_to_uid_when_employee_id_missing():
    mock_user = MagicMock()
    mock_user.employee_id = None
    mock_user.uid = "USR002"

    mock_uow = MagicMock()
    mock_uow.users.get_by_uid.return_value = mock_user

    mock_uow_factory = MagicMock()
    mock_uow_factory.return_value.__enter__.return_value = mock_uow

    provider = DatabaseEmployeeIdProvider(unit_of_work_factory=mock_uow_factory)
    principal = AuthenticatedPrincipal(uid="USR002")

    assert provider.get_employee_id(principal) == "USR002"


def test_db_lookup_error_graceful_fallback():
    mock_uow_factory = MagicMock()
    mock_uow_factory.return_value.__enter__.side_effect = RuntimeError("DB connection dropped")

    provider = DatabaseEmployeeIdProvider(unit_of_work_factory=mock_uow_factory)
    principal = AuthenticatedPrincipal(uid="USR003")

    # Should safely return the candidate uid without raising
    assert provider.get_employee_id(principal) == "USR003"
