import pytest
from app.domain.services.employee_id_provider import EmployeeIdProvider
from app.infrastructure.logging.mock_employee_id_provider import MockEmployeeIdProvider


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


def test_mock_employee_id_provider_cycles_default_test_ids():
    """Verify MockEmployeeIdProvider cycles through MSS001, MSS002, MSS003."""
    provider = MockEmployeeIdProvider()
    assert isinstance(provider, EmployeeIdProvider)

    # First cycle
    assert provider.get_employee_id() == "MSS001"
    assert provider.get_employee_id() == "MSS002"
    assert provider.get_employee_id() == "MSS003"

    # Repeats cycle
    assert provider.get_employee_id() == "MSS001"
    assert provider.get_employee_id() == "MSS002"


def test_mock_employee_id_provider_rejects_untrusted_arbitrary_user_context():
    """Verify MockEmployeeIdProvider does not trust arbitrary employee IDs in user_context."""
    provider = MockEmployeeIdProvider()

    # Pass malicious or arbitrary employee IDs in dictionary user_context
    untrusted_dict_result = provider.get_employee_id({"employee_id": "HACKER_ATTACK_999"})
    assert untrusted_dict_result != "HACKER_ATTACK_999"
    assert untrusted_dict_result in ("MSS001", "MSS002", "MSS003")

    # Pass arbitrary string
    untrusted_str_result = provider.get_employee_id("RANDOM_STRING_ID")
    assert untrusted_str_result != "RANDOM_STRING_ID"
    assert untrusted_str_result in ("MSS001", "MSS002", "MSS003")


def test_mock_employee_id_provider_recognizes_valid_mock_ids_in_context():
    """Verify MockEmployeeIdProvider allows matching an encapsulated mock ID if specified."""
    provider = MockEmployeeIdProvider()
    assert provider.get_employee_id({"employee_id": "MSS002"}) == "MSS002"
    assert provider.get_employee_id("MSS003") == "MSS003"


def test_mock_employee_id_provider_custom_sequence():
    """Verify MockEmployeeIdProvider accepts custom mock sequences."""
    provider = MockEmployeeIdProvider(["TEST001", "TEST002"])
    assert provider.get_employee_id() == "TEST001"
    assert provider.get_employee_id() == "TEST002"
    assert provider.get_employee_id() == "TEST001"
