from unittest.mock import MagicMock, patch
import pytest


def test_sidebar_renders_expected_links_for_standard_developer():
    profile_data = {
        "user": {
            "name": "Jane Dev",
            "username": "jane",
            "role": "Developer",
            "job_title": "Frontend Engineer",
            "employee_id": "EMP-0010",
        },
        "department": {"department_name": "Engineering"},
        "permissions": ["PROJECT_VIEW", "DOCUMENT_VIEW"],
    }

    mock_st = MagicMock()
    mock_st.sidebar.button.return_value = False
    mock_st.session_state = {"auth": {"access_token": "token123"}, "user_profile": profile_data}

    with patch("streamlit_app.sidebar.st", mock_st), \
         patch("streamlit_app.sidebar.ProfileAPI"):
        from streamlit_app.sidebar import render_sidebar
        render_sidebar()

    # Check page_link calls
    calls = [call[0] for call in mock_st.sidebar.page_link.call_args_list]
    paths = [c[0] for c in calls]

    assert "app.py" in paths
    assert "pages/profile.py" in paths
    assert "pages/projects.py" in paths
    assert "pages/documents.py" in paths

    # Admin pages should NOT be present for standard developer
    assert "pages/users.py" not in paths
    assert "pages/departments.py" not in paths
    assert "pages/roles.py" not in paths


def test_sidebar_renders_admin_links_for_admin():
    profile_data = {
        "user": {
            "name": "Super Admin",
            "username": "admin",
            "role": "Admin",
            "job_title": "System Administrator",
            "employee_id": "ADM-0001",
        },
        "department": {"department_name": "Executive"},
        "permissions": ["*"],
    }

    mock_st = MagicMock()
    mock_st.sidebar.button.return_value = False
    mock_st.session_state = {"auth": {"access_token": "admintoken"}, "user_profile": profile_data}

    with patch("streamlit_app.sidebar.st", mock_st), \
         patch("streamlit_app.sidebar.ProfileAPI"):
        from streamlit_app.sidebar import render_sidebar
        render_sidebar()

    calls = [call[0] for call in mock_st.sidebar.page_link.call_args_list]
    paths = [c[0] for c in calls]

    assert "app.py" in paths
    assert "pages/profile.py" in paths
    assert "pages/projects.py" in paths
    assert "pages/documents.py" in paths
    assert "pages/users.py" in paths
    assert "pages/departments.py" in paths
    assert "pages/roles.py" in paths


def test_sidebar_renders_user_management_when_granted_user_permission():
    profile_data = {
        "user": {
            "name": "HR Manager",
            "username": "hrmgr",
            "role": "HR Manager",
            "job_title": "HR Lead",
            "employee_id": "EMP-0002",
        },
        "department": {"department_name": "People"},
        "permissions": ["USER_VIEW", "USER_CREATE"],
    }

    mock_st = MagicMock()
    mock_st.sidebar.button.return_value = False
    mock_st.session_state = {"auth": {"access_token": "hrtoken"}, "user_profile": profile_data}

    with patch("streamlit_app.sidebar.st", mock_st), \
         patch("streamlit_app.sidebar.ProfileAPI"):
        from streamlit_app.sidebar import render_sidebar
        render_sidebar()

    calls = [call[0] for call in mock_st.sidebar.page_link.call_args_list]
    paths = [c[0] for c in calls]

    assert "pages/users.py" in paths
    assert "pages/departments.py" not in paths
    assert "pages/roles.py" not in paths
