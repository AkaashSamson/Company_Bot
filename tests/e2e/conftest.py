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
    env["STREAMLIT_API_BASE_URL"] = f"{BACKEND_URL}/api"
    env["DOC_INGESTION_REFRESH_INTERVAL"] = "1"
    env["PYTHONUNBUFFERED"] = "1"

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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for FastAPI backend
    backend_ready = False
    start_time = time.time()
    while time.time() - start_time < 60:
        if backend_proc.poll() is not None:
            _, err = backend_proc.communicate()
            raise RuntimeError(f"FastAPI backend died on startup: {err.decode(errors='ignore')}")
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

    # Wait for Streamlit frontend
    frontend_ready = False
    start_time = time.time()
    while time.time() - start_time < 60:
        if frontend_proc.poll() is not None:
            _, err = frontend_proc.communicate()
            raise RuntimeError(f"Streamlit frontend died on startup: {err.decode(errors='ignore')}")
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

    yield {"api_url": BACKEND_URL, "ui_url": FRONTEND_URL}

    # Teardown processes
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

    _clean_test_artifacts()


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
        self.page.get_by_label("Username").fill(username)
        self.page.get_by_label("Password").fill(password)
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


@pytest.fixture
def ui(page: Page, e2e_servers) -> UIActions:
    """Provides high-level UI action helpers."""
    return UIActions(page, base_url=e2e_servers["ui_url"])
