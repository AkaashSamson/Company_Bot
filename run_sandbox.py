"""
KnowLayer Developer Sandbox Launcher
====================================
Runs the standalone Streamlit sandbox dashboard on port 8502.
Does not require Docker or the FastAPI backend to be running.

Usage:
    python run_sandbox.py
    python run_sandbox.py --port 8502
"""

import os
import socket
import subprocess
import sys
from pathlib import Path

# Safe stdout on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent

def get_python_exe() -> Path:
    if sys.platform == "win32":
        venv_py = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        venv_py = PROJECT_ROOT / ".venv" / "bin" / "python"
    
    if venv_py.exists():
        return venv_py
    return Path(sys.executable)


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def free_port(port: int):
    if sys.platform == "win32":
        try:
            output = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True, text=True, stderr=subprocess.DEVNULL)
            for line in output.splitlines():
                parts = line.strip().split()
                if len(parts) >= 5 and "LISTENING" in parts:
                    pid = parts[-1]
                    if pid.isdigit() and int(pid) > 0:
                        print(f"[CLEANUP] Freeing occupied port {port} (PID {pid})...")
                        subprocess.run(["taskkill", "/F", "/T", "/PID", pid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except Exception:
            pass


def main():
    port = 8502
    if "--port" in sys.argv:
        try:
            idx = sys.argv.index("--port")
            port = int(sys.argv[idx + 1])
        except (IndexError, ValueError):
            pass

    python_exe = get_python_exe()
    app_file = PROJECT_ROOT / "sandbox" / "sandbox_app.py"

    if is_port_in_use(port):
        free_port(port)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)

    cmd = [
        str(python_exe),
        "-m",
        "streamlit",
        "run",
        str(app_file),
        "--server.port",
        str(port),
        "--server.address",
        "127.0.0.1",
        "--server.headless=false",
    ]

    print("\n=======================================================")
    print("   KnowLayer Developer Sandbox & Observability Suite   ")
    print("=======================================================")
    print(f"  * Mode:     Standalone Local Dashboard")
    print(f"  * URL:      http://127.0.0.1:{port}")
    print(f"  * Python:   {python_exe}")
    print(f"  * Entry:    {app_file}")
    print("=======================================================\n")

    try:
        subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
    except KeyboardInterrupt:
        print("\n[STOP] Sandbox stopped cleanly.")


if __name__ == "__main__":
    main()
