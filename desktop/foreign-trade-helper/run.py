"""一键启动后端 — python run.py"""
import subprocess, sys, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))
host = os.environ.get("COMPANYLEADS_BACKEND_HOST", "127.0.0.1")
port = os.environ.get("COMPANYLEADS_BACKEND_PORT", "8002")
subprocess.run([
    sys.executable, "-m", "uvicorn",
    "backend.main:app",
    "--reload",
    "--host", host,
    "--port", port,
], check=True)
