import requests
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import pytest
from playwright.sync_api import Page, expect

BACKEND_PORT = 8001
FRONTEND_PORT = 8502
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}"
FRONTEND_URL = f"http://127.0.0.1:{FRONTEND_PORT}"

TEST_DB_PATH = "test_e2e.db"
TEST_CHROMA_DIR = ".chroma_e2e"


def _clean_test_artifacts():
    for f in [TEST_DB_PATH, f"{TEST_DB_PATH}-wal", f"{TEST_DB_PATH}-shm"]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass
    if os.path.exists(TEST_CHROMA_DIR):
        try:
            shutil.rmtree(TEST_CHROMA_DIR, ignore_errors=True)
        except OSError:
            pass


@pytest.fixture(scope="session")
def e2e_servers():
    """Start isolated FastAPI (:8001) and Streamlit (:8502) servers."""
    _clean_test_artifacts()

    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH}"
    env["CHROMA_PERSIST_DIRECTORY"] = TEST_CHROMA_DIR
    env["COLLECTION_NAME"] = "e2e_collection"
    env["STREAMLIT_API_BASE_URL"] = BACKEND_URL
    env["DOC_INGESTION_REFRESH_INTERVAL"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTEST_CURRENT_TEST"] = "1"
    env["DOCLING_VISUAL_ENRICHMENT_ENABLED"] = "false"

    print("\n" + "=" * 60, flush=True)
    print("[E2E Servers] Starting isolated test environment:", flush=True)
    print(f"   - Database:  {TEST_DB_PATH}", flush=True)
    print(f"   - Backend:   {BACKEND_URL} (logs -> fastapi_e2e.log)", flush=True)
    print(f"   - Frontend:  {FRONTEND_URL} (logs -> streamlit_e2e.log)", flush=True)
    print("=" * 60, flush=True)

    backend_log = open("fastapi_e2e.log", "w", encoding="utf-8", buffering=1)
    frontend_log = open("streamlit_e2e.log", "w", encoding="utf-8", buffering=1)

    # 1. Start FastAPI backend
    backend_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--port",
            str(BACKEND_PORT),
            "--host",
            "127.0.0.1",
        ],
        env=env,
        stdout=backend_log,
        stderr=backend_log,
    )

    # 2. Start Streamlit frontend
    frontend_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "streamlit_app/app.py",
            "--server.port",
            str(FRONTEND_PORT),
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
        ],
        env=env,
        stdout=frontend_log,
        stderr=frontend_log,
    )

    # Wait for FastAPI backend
    print("[E2E Servers] Waiting for FastAPI backend on :8001...", flush=True)
    backend_ready = False
    start_time = time.time()
    while time.time() - start_time < 120:
        backend_log.flush()
        if backend_proc.poll() is not None:
            backend_log.close()
            with open("fastapi_e2e.log", "r", encoding="utf-8", errors="ignore") as f:
                err = f.read()
            raise RuntimeError(f"FastAPI backend died on startup:\n{err}")
        try:
            with urllib.request.urlopen(f"{BACKEND_URL}/api/documents/status", timeout=1) as resp:
                if resp.status == 200:
                    backend_ready = True
                    break
        except Exception:
            time.sleep(1)

    if not backend_ready:
        backend_proc.terminate()
        frontend_proc.terminate()
        backend_log.flush()
        frontend_log.flush()
        backend_log.close()
        frontend_log.close()
        with open("fastapi_e2e.log", "r", encoding="utf-8", errors="ignore") as f:
            err = f.read()
        print(f"\n[E2E Servers] [ERROR] FastAPI backend failed to start. Logs:\n{err}\n", flush=True)
        raise TimeoutError(f"FastAPI backend failed to become ready within 120 seconds:\n{err}")
    print(f"[E2E Servers] [OK] FastAPI backend is live and healthy! ({time.time() - start_time:.1f}s)", flush=True)

    # Wait for Streamlit frontend
    print("[E2E Servers] Waiting for Streamlit frontend on :8502...", flush=True)
    frontend_ready = False
    start_time = time.time()
    while time.time() - start_time < 60:
        frontend_log.flush()
        if frontend_proc.poll() is not None:
            frontend_log.close()
            with open("streamlit_e2e.log", "r", encoding="utf-8", errors="ignore") as f:
                err = f.read()
            raise RuntimeError(f"Streamlit frontend died on startup:\n{err}")
        try:
            with urllib.request.urlopen(f"{FRONTEND_URL}/_stcore/health", timeout=1) as resp:
                if resp.status == 200:
                    frontend_ready = True
                    break
        except Exception:
            time.sleep(1)

    if not frontend_ready:
        backend_proc.terminate()
        frontend_proc.terminate()
        backend_log.flush()
        frontend_log.flush()
        backend_log.close()
        frontend_log.close()
        with open("streamlit_e2e.log", "r", encoding="utf-8", errors="ignore") as f:
            err = f.read()
        print(f"\n[E2E Servers] [ERROR] Streamlit frontend failed to start. Logs:\n{err}\n", flush=True)
        raise TimeoutError(f"Streamlit frontend failed to become ready within 60 seconds:\n{err}")
    print(f"[E2E Servers] [OK] Streamlit frontend is live and healthy! ({time.time() - start_time:.1f}s)", flush=True)
    print("[E2E Servers] Test environment ready. Starting Playwright browser...\n", flush=True)

    yield {"api_url": BACKEND_URL, "ui_url": FRONTEND_URL}

    print("\n[E2E Servers] Shutting down isolated test servers...", flush=True)
    frontend_proc.terminate()
    backend_proc.terminate()
    try:
        frontend_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        frontend_proc.kill()
    try:
        backend_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        backend_proc.kill()

    if not backend_log.closed:
        backend_log.close()
    if not frontend_log.closed:
        frontend_log.close()
    print("[E2E Servers] [OK] Test servers stopped. Logs preserved in fastapi_e2e.log and streamlit_e2e.log.", flush=True)


class UIActions:
    """Helper abstractions for UI interaction with Streamlit pages."""

    def __init__(self, page: Page, base_url: str = FRONTEND_URL):
        self.page = page
        self.base_url = base_url

    def goto_home(self):
        self.page.goto(self.base_url)
        self.page.wait_for_load_state("domcontentloaded")

    def login(self, username: str, password: str):
        self.goto_home()
        # Check if already logged in as someone else
        logout_btn = self.page.locator('[data-testid="stSidebar"]').get_by_role("button", name="Log out")
        if logout_btn.is_visible():
            logout_btn.click()
            self.page.wait_for_timeout(1000)

        # Fill login form
        self.page.get_by_role("textbox", name="Username").fill(username)
        self.page.get_by_role("textbox", name="Password").fill(password)
        self.page.get_by_role("button", name="Log in").click()

        # Wait for sidebar to render logout button indicating authenticated session
        expect(self.page.locator('[data-testid="stSidebar"]').get_by_role("button", name="Log out")).to_be_visible(
            timeout=15000
        )

    def logout(self):
        sidebar = self.page.locator('[data-testid="stSidebar"]')
        logout_btn = sidebar.get_by_role("button", name="Log out")
        if logout_btn.is_visible():
            logout_btn.click()
            self.page.wait_for_timeout(1000)
        go_to_login_link = self.page.get_by_role("link", name="Go to log in")
        if go_to_login_link.is_visible():
            go_to_login_link.click()
        try:
            self.page.context.clear_cookies()
        except Exception:
            pass
        self.goto_home()
        expect(self.page.get_by_role("button", name="Log in")).to_be_visible(timeout=15000)

    def navigate_to(self, page_label: str):
        """Click sidebar navigation link."""
        sidebar = self.page.locator('[data-testid="stSidebar"]')
        sidebar.get_by_text(page_label, exact=False).click()
        self.page.wait_for_load_state("domcontentloaded")
        self.page.wait_for_timeout(1500)

    def _resolve_scope(self, container: str | None = None):
        """Resolve a container scope, supporting stExpander (with auto-open) or section headings."""
        if not container:
            return self.page

        # 1. Check if container matches an st.expander
        expander = self.page.locator('[data-testid="stExpander"]').filter(has_text=container).first
        if expander.count() > 0:
            details = expander.locator("details").first if expander.locator("details").count() > 0 else expander
            is_open = details.get_attribute("open") is not None
            if not is_open:
                expander.locator("summary").first.click()
                self.page.wait_for_timeout(400)
            return expander

        # 2. Check if container matches a section heading (h1, h2, h3, h4)
        heading = self.page.locator("h1, h2, h3, h4").filter(has_text=container).first
        if heading.count() > 0:
            return heading

        return self.page

    def fill_input(self, label: str, value: str, container: str | None = None):
        """Fill a Streamlit text input or textarea by role and name, optionally scoped to a container."""
        scope = self._resolve_scope(container)
        if container and scope != self.page and scope.locator("xpath=self::h1 | self::h2 | self::h3 | self::h4").count() > 0:
            target = scope.locator(
                f'xpath=following::input[@aria-label="{label}"][1] | following::textarea[@aria-label="{label}"][1]'
            )
            if target.count() > 0:
                target.first.fill(value)
                return
        scope.get_by_role("textbox", name=label).first.fill(value)

    def open_expander(self, label: str):
        """Expand a Streamlit st.expander if closed."""
        expander = self.page.locator('[data-testid="stExpander"]').filter(has_text=label).first
        if expander.count() > 0:
            details = expander.locator("details").first if expander.locator("details").count() > 0 else expander
            is_open = details.get_attribute("open") is not None
            if not is_open:
                expander.locator("summary").first.click()
                self.page.wait_for_timeout(400)

    def upload_file(self, file_path: str, container: str | None = None):
        """Upload a file using Streamlit st.file_uploader, optionally scoped to a container."""
        scope = self._resolve_scope(container)
        uploader = scope.locator('[data-testid="stFileUploader"]').first
        file_input = uploader.locator('input[type="file"]')
        file_input.set_input_files(file_path)
        self.page.wait_for_timeout(1000)

    def select_dropdown(self, label: str, option_text: str, container: str | None = None):
        """Select an option in a Streamlit st.selectbox by label, optionally scoped to a container."""
        scope = self._resolve_scope(container)

        if container and scope != self.page and scope.locator("xpath=self::h1 | self::h2 | self::h3 | self::h4").count() > 0:
            following = scope.locator(
                f'xpath=following::div[@data-testid="stSelectbox"][.//*[contains(text(), "{label}") or text()="{label}"]][1]'
            )
            selectbox = following.first if following.count() > 0 else scope.locator('xpath=following::div[@data-testid="stSelectbox"][1]')
        else:
            matching = scope.locator('[data-testid="stSelectbox"]').filter(has_text=label)
            selectbox = matching.first

        # 1. If option is already selected in this selectbox, skip immediately
        try:
            if option_text.lower() in selectbox.inner_text().lower():
                return
        except Exception:
            pass

        # 2. Click selectbox to open dropdown
        select_trigger = selectbox.locator('[data-baseweb="select"]')
        if select_trigger.count() > 0:
            select_trigger.click()
        else:
            selectbox.click()

        # 3. Wait for and click option in popover
        option_locator = self.page.locator('[role="option"]').filter(has_text=option_text).first
        try:
            option_locator.wait_for(state="visible", timeout=2000)
            option_locator.click()
        except Exception:
            inp = selectbox.locator("input")
            if inp.count() > 0:
                inp.fill(option_text)
                self.page.wait_for_timeout(200)
            option_locator.click(timeout=3000)

        self.page.wait_for_timeout(300)


@pytest.fixture
def ui(page: Page, e2e_servers) -> UIActions:
    """Provides high-level UI action helpers."""
    return UIActions(page, base_url=e2e_servers["ui_url"])


def _get_admin_token(backend_url: str = BACKEND_URL) -> str:
    """Helper to obtain an admin bearer token from the FastAPI backend."""
    resp = requests.post(
        f"{backend_url}/api/auth/login",
        json={"username": "admin", "password": "change-me-before-first-login"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


@pytest.fixture
def ensure_act1_state(e2e_servers):
    """Ensures Act 1 state: System Admin bootstrapped and Sarah Chen exists as an Admin."""
    backend_url = e2e_servers["api_url"]
    token = _get_admin_token(backend_url)
    headers = {"Authorization": f"Bearer {token}"}

    users_resp = requests.get(f"{backend_url}/api/users", headers=headers, timeout=10)
    users = users_resp.json() if users_resp.status_code == 200 else []
    sarah = next((u for u in users if u.get("username") == "sarah.admin"), None)

    if not sarah:
        depts_resp = requests.get(f"{backend_url}/api/departments", headers=headers, timeout=10)
        depts = depts_resp.json() if depts_resp.status_code == 200 else []
        admin_dept_id = next((d["department_id"] for d in depts if d.get("department_name") == "Administration"), None) or (depts[0]["department_id"] if depts else "admin")

        requests.post(
            f"{backend_url}/api/users",
            headers=headers,
            json={
                "username": "sarah.admin",
                "name": "Sarah Chen",
                "email": "sarah@nexora.com",
                "role": "Admin",
                "department_id": admin_dept_id,
                "initial_password": "Password123!",
            },
            timeout=10,
        ).raise_for_status()

    return {"sarah_username": "sarah.admin", "sarah_password": "Password123!"}


@pytest.fixture
def ensure_act2_state(ensure_act1_state, e2e_servers):
    """Ensures Act 2 state: Sarah Chen, Engineering & HR departments, and leads (Roy & Marcus) exist."""
    backend_url = e2e_servers["api_url"]
    token = _get_admin_token(backend_url)
    headers = {"Authorization": f"Bearer {token}"}

    # Ensure departments
    depts_resp = requests.get(f"{backend_url}/api/departments", headers=headers, timeout=10)
    depts = {d["department_name"]: d["department_id"] for d in (depts_resp.json() if depts_resp.status_code == 200 else [])}

    if "Engineering" not in depts:
        r = requests.post(
            f"{backend_url}/api/departments",
            headers=headers,
            json={"department_name": "Engineering", "default_billable_policy": "billable"},
            timeout=10,
        )
        r.raise_for_status()
        depts["Engineering"] = r.json()["department_id"]

    if "Human Resources" not in depts:
        r = requests.post(
            f"{backend_url}/api/departments",
            headers=headers,
            json={"department_name": "Human Resources", "default_billable_policy": "non-billable"},
            timeout=10,
        )
        r.raise_for_status()
        depts["Human Resources"] = r.json()["department_id"]

    # Ensure leads
    users_resp = requests.get(f"{backend_url}/api/users", headers=headers, timeout=10)
    users = {u.get("username"): u for u in (users_resp.json() if users_resp.status_code == 200 else [])}

    if "roy.hr" not in users:
        requests.post(
            f"{backend_url}/api/users",
            headers=headers,
            json={
                "username": "roy.hr",
                "name": "Roy Miller",
                "email": "roy@nexora.com",
                "role": "Manager",
                "department_id": depts["Human Resources"],
                "initial_password": "Password123!",
            },
            timeout=10,
        ).raise_for_status()

    if "marcus.eng" not in users:
        requests.post(
            f"{backend_url}/api/users",
            headers=headers,
            json={
                "username": "marcus.eng",
                "name": "Marcus Vance",
                "email": "marcus@nexora.com",
                "role": "Manager",
                "department_id": depts["Engineering"],
                "initial_password": "Password123!",
            },
            timeout=10,
        ).raise_for_status()

    return {
        "admin": ensure_act1_state,
        "departments": depts,
        "leads": {
            "roy": {"username": "roy.hr", "password": "Password123!"},
            "marcus": {"username": "marcus.eng", "password": "Password123!"},
        },
    }
