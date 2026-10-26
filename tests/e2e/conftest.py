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

    print("\n" + "=" * 60, flush=True)
    print("[E2E Servers] Starting isolated test environment:", flush=True)
    print(f"   - Database:  {TEST_DB_PATH}", flush=True)
    print(f"   - Backend:   {BACKEND_URL} (logs -> fastapi_e2e.log)", flush=True)
    print(f"   - Frontend:  {FRONTEND_URL} (logs -> streamlit_e2e.log)", flush=True)
    print("=" * 60, flush=True)

    backend_log = open("fastapi_e2e.log", "w", encoding="utf-8")
    frontend_log = open("streamlit_e2e.log", "w", encoding="utf-8")

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
    while time.time() - start_time < 60:
        if backend_proc.poll() is not None:
            backend_log.flush()
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
        raise TimeoutError("FastAPI backend failed to become ready within 60 seconds")
    print(f"[E2E Servers] [OK] FastAPI backend is live and healthy! ({time.time() - start_time:.1f}s)", flush=True)

    # Wait for Streamlit frontend
    print("[E2E Servers] Waiting for Streamlit frontend on :8502...", flush=True)
    frontend_ready = False
    start_time = time.time()
    while time.time() - start_time < 60:
        if frontend_proc.poll() is not None:
            frontend_log.flush()
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
        raise TimeoutError("Streamlit frontend failed to become ready within 60 seconds")
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

    backend_log.close()
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
            expect(self.page.get_by_role("button", name="Log in")).to_be_visible(timeout=10000)

    def navigate_to(self, page_label: str):
        """Click sidebar navigation link."""
        sidebar = self.page.locator('[data-testid="stSidebar"]')
        sidebar.get_by_text(page_label, exact=False).click()
        self.page.wait_for_load_state("domcontentloaded")
        self.page.wait_for_timeout(1500)

    def fill_input(self, label: str, value: str, container: str | None = None):
        """Fill a Streamlit text input or textarea by role and name, optionally scoped to a container."""
        if container:
            scope = self.page.locator('[data-testid="stExpander"]').filter(has_text=container)
        else:
            scope = self.page
        scope.get_by_role("textbox", name=label).first.fill(value)

    def open_expander(self, label: str):
        """Expand a Streamlit st.expander if closed."""
        expander = self.page.locator('[data-testid="stExpander"]').filter(has_text=label)
        summary = expander.locator("summary")
        if summary.count() > 0 and summary.get_attribute("aria-expanded") != "true":
            summary.click()
            self.page.wait_for_timeout(500)

    def select_dropdown(self, label: str, option_text: str, container: str | None = None):
        """Select an option in a Streamlit st.selectbox by label, optionally scoped to a container."""
        if container:
            scope = self.page.locator('[data-testid="stExpander"]').filter(has_text=container)
        else:
            scope = self.page
        selectbox = scope.locator('[data-testid="stSelectbox"]').filter(has_text=label).first
        select_trigger = selectbox.locator('[data-baseweb="select"]')
        if select_trigger.count() > 0:
            select_trigger.click()
        else:
            selectbox.click()
        self.page.wait_for_timeout(300)

        option = self.page.locator('[role="option"]').filter(has_text=option_text).first
        if option.is_visible():
            option.click()
        else:
            inp = selectbox.locator("input")
            if inp.count() > 0:
                inp.fill(option_text)
                inp.press("Enter")
        self.page.wait_for_timeout(500)


@pytest.fixture
def ui(page: Page, e2e_servers) -> UIActions:
    """Provides high-level UI action helpers."""
    return UIActions(page, base_url=e2e_servers["ui_url"])
