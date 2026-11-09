"""Load only the local demo's chat settings; never execute dotenv contents."""
from pathlib import Path
import os
import shlex

CHAT_SETTINGS = frozenset({
    "DO_MODEL_INFERENCE_KEY", "SANDBOX_CHAT_MODEL", "SANDBOX_VERIFY_MODEL",
    "SANDBOX_CHAT_MAX_ATTEMPTS", "SANDBOX_CHAT_TIMEOUT",
})


def load_chat_env(path=None, environ=None):
    """Fill unset chat variables from demo/.env, preserving process overrides.

    Supports plain or quoted single-line assignments, optional ``export``, and
    comments. No shell execution, interpolation, or parent-directory search.
    Unrelated credentials in the file are deliberately not loaded.
    """
    target = os.environ if environ is None else environ
    path = Path(path) if path is not None else Path(__file__).with_name(".env")
    if not path.is_file():
        return
    pending = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:].lstrip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name not in CHAT_SETTINGS or name in target:
            continue
        try:
            parts = shlex.split(value.strip(), comments=True, posix=True)
        except ValueError:
            raise ValueError(f"Invalid single-line value for {name} in demo/.env.") from None
        if len(parts) > 1:
            raise ValueError(f"Quote the single-line value for {name} in demo/.env.")
        pending[name] = parts[0] if parts else ""
    target.update(pending)
