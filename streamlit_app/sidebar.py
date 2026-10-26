import uuid
import streamlit as st
from streamlit_app.services.profile_api import ProfileAPI


def get_current_profile():
    if not st.session_state.get("user_profile"):
        try:
            st.session_state["user_profile"] = ProfileAPI().profile()
        except Exception:
            st.session_state["user_profile"] = None
    return st.session_state.get("user_profile") or {}


def logout_user():
    st.session_state["auth"] = None
    st.session_state["user_profile"] = None
    st.session_state["messages"] = []
    st.session_state["last_response"] = None
    st.session_state["session_id"] = str(uuid.uuid4())
    try:
        from streamlit_app.session_auth import bootstrap_cookies
        cookies = bootstrap_cookies()
        cookies.remove("knowlayer_auth")
    except Exception:
        pass
    st.rerun()


def render_sidebar():
    auth = st.session_state.get("auth")
    if not auth:
        return

    # 1. User Identity Badge at top of sidebar
    profile = get_current_profile()
    user = profile.get("user") or {}
    department = profile.get("department") or {}
    permissions = set(profile.get("permissions") or [])
    user_role = user.get("role", "")
    auth_uid = auth.get("uid", "") if isinstance(auth, dict) else ""
    is_admin = (
        user_role.lower() == "admin"
        or auth_uid == "admin"
        or "*" in permissions
        or "ADMIN" in permissions
    )

    user_name = user.get("name") or user.get("username") or ("Administrator" if is_admin else "User")
    job_title = user.get("job_title") or user_role or ("Admin" if is_admin else "Employee")
    dept_name = department.get("department_name") or user.get("department") or ""
    emp_id = user.get("employee_id") or ""

    st.sidebar.markdown(f"### 👤 {user_name}")
    subtitle_items = [item for item in (job_title, dept_name) if item]
    if subtitle_items:
        st.sidebar.caption(" · ".join(subtitle_items))
    if emp_id:
        st.sidebar.caption(f"ID: `{emp_id}`")
    st.sidebar.divider()

    # 2. Role-Based Navigation Links (Clean, No Brackets)
    st.sidebar.page_link("app.py", label="Chat", icon="💬")
    st.sidebar.page_link("pages/profile.py", label="My Profile", icon="👤")
    st.sidebar.page_link("pages/projects.py", label="Projects", icon="📁")
    st.sidebar.page_link("pages/documents.py", label="Documents", icon="📄")

    # Administration tabs shown only if user has relevant permission or is Admin
    has_user_perm = is_admin or any(p in permissions for p in ("USER_VIEW", "USER_CREATE", "USER_UPDATE", "USER_DELETE"))
    if has_user_perm:
        st.sidebar.page_link("pages/users.py", label="Users", icon="👥")

    has_dept_perm = is_admin or any(p in permissions for p in ("DEPARTMENT_VIEW", "DEPARTMENT_CREATE", "DEPARTMENT_UPDATE", "DEPARTMENT_ASSIGN_USERS"))
    if has_dept_perm:
        st.sidebar.page_link("pages/departments.py", label="Departments", icon="🏢")

    has_role_perm = is_admin or any(p in permissions for p in ("ROLE_VIEW", "ROLE_CREATE", "ROLE_UPDATE", "ROLE_DELETE"))
    if has_role_perm:
        st.sidebar.page_link("pages/roles.py", label="Roles", icon="🔑")

    st.sidebar.divider()

    # 3. Log out action
    if st.sidebar.button("Log out", key="sidebar_logout_btn", use_container_width=True):
        logout_user()
