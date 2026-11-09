"""Build the shared UI and manage private Workbench services with the main server."""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
PLAYGROUND = ROOT.parent / "pdp-datathon-starter/playground"
CLIENT = PLAYGROUND / "client_application"
BUILD = ".next/demo"
BASE_PATH = "/workbench-ui"


def commands():
    """Resolve the pinned sibling installations before starting either service."""
    python = PLAYGROUND / "server_application/.venv/bin/python"
    next_cli = CLIENT / "node_modules/next/dist/bin/next"
    node = shutil.which("node")
    if not python.exists() or not next_cli.exists() or not node:
        raise SystemExit("Install Playground dependencies first; see demo/README.md: Workbench.")
    return [str(python), str(ROOT / "workbench_api.py")], [node, str(next_cli)]


def client_environment():
    """Build browser URLs relative to the main app, never the visitor's localhost."""
    return {**os.environ, "NEXT_PUBLIC_BASE_PATH": BASE_PATH, "NEXT_BUILD_DIR": BUILD,
            "NEXT_PUBLIC_API_BASE_URL": "/api/workbench-proxy/api/v1",
            "NEXT_PUBLIC_SANDBOX_ENABLED": "true", "NEXT_PUBLIC_APP_ENV": "production"}


def ready():
    """Check both owned services rather than reporting a half-working Workbench."""
    try:
        with urlopen("http://127.0.0.1:8100/health", timeout=2) as response:
            health = json.load(response)
        with urlopen(f"http://127.0.0.1:3100{BASE_PATH}/workbench", timeout=2) as response:
            return response.status == 200 and health.get("service") == "demo-workbench"
    except (OSError, ValueError):
        return False


class WorkbenchServices:
    """Keep production Next and the restricted API alive for exactly one main-server lifetime."""
    def __init__(self):
        """Track only processes this server starts."""
        self.children = []

    def start(self):
        """Fail startup if dependencies, the build, ports, or either child are unavailable."""
        api, next_cli = commands()
        if not (CLIENT / BUILD / "BUILD_ID").is_file():
            raise SystemExit("Build Workbench first with npm run workbench:build; see README.md.")
        for port in (3100, 8100):
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    probe.bind(("127.0.0.1", port))
                except OSError:
                    raise SystemExit(f"Workbench port {port} is already occupied; refusing to share another instance.")
        self.children.append(subprocess.Popen(api, cwd=ROOT, start_new_session=True))
        self.children.append(subprocess.Popen([*next_cli, "start", "--hostname", "127.0.0.1", "--port", "3100"],
                                              cwd=CLIENT, env=client_environment(), start_new_session=True))
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            self.check()
            if ready():
                return
            time.sleep(.5)
        raise RuntimeError("Workbench did not become ready within 90 seconds.")

    def check(self):
        """Fail the main process so its service manager can restart the whole app."""
        if any(child.poll() is not None for child in self.children):
            raise RuntimeError("A Workbench service stopped; restart the main app. See service output.")

    def close(self):
        """Stop owned process groups, including descendants, on clean or failed startup."""
        for child in self.children:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for child in self.children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["build"])
    parser.parse_args()
    _, next_cli = commands()
    subprocess.run([*next_cli, "build"], cwd=CLIENT, env=client_environment(), check=True)
