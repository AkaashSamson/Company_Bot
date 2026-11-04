import pytest
from app.domain.services.employee_id_provider import EmployeeIdProvider


class CustomTestProvider(EmployeeIdProvider):
    """Custom provider for testing provider substitution."""

    def get_employee_id(self, user_context=None) -> str:
        return "CUSTOM_EMP_999"


def test_employee_id_provider_abstract_interface():
    """Verify EmployeeIdProvider cannot be instantiated directly."""
    with pytest.raises(TypeError):
        EmployeeIdProvider()  # type: ignore[abstract]


def test_provider_substitution():
    """Verify that a custom implementation satisfies the EmployeeIdProvider contract."""
    provider = CustomTestProvider()
    assert isinstance(provider, EmployeeIdProvider)
    assert provider.get_employee_id() == "CUSTOM_EMP_999"
    assert provider.get_employee_id({"user": "alice"}) == "CUSTOM_EMP_999"
