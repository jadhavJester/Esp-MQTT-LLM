"""Tests for curious_robot.main's startup guard.

Running the simulation without OLLAMA_API_KEY must fail fast with a
clear error instead of starting the agent. This spawns the real entry
point as a subprocess, so it only runs where the runtime dependencies
(anyio, ollama) are installed -- see requirements.txt. Under plain
system python the test is skipped; the stubbed unit suite covers the
offline modules instead.
"""
import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _runtime_deps_installed():
    """True only when the real runtime packages are importable.

    conftest.py installs lightweight stand-ins for anyio/ollama/mcp so
    the offline unit tests can run without them; those stubs have no
    __file__, which is how they are told apart from real installs.
    """
    for name in ("anyio", "ollama", "mcp"):
        mod = sys.modules.get(name)
        if mod is None:
            try:
                mod = importlib.import_module(name)
            except ImportError:
                return False
        if not getattr(mod, "__file__", None):
            return False
    return True


pytestmark = pytest.mark.skipif(
    not _runtime_deps_installed(),
    reason="runtime deps (anyio/ollama/mcp) not installed; see requirements.txt",
)

ROOT = Path(__file__).resolve().parents[1]

# httpx (used by the ollama client at import time) chokes on some
# proxy/no-proxy spellings, e.g. bare IPv6 entries in NO_PROXY; the
# child process gets a sanitized environment, like gitdude-clean does.
_PROXY_VARS = (
    "http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
    "no_proxy", "NO_PROXY", "all_proxy", "ALL_PROXY",
)


def _run_main_without_key():
    env = {k: v for k, v in os.environ.items()
           if k not in _PROXY_VARS and k != "OLLAMA_API_KEY"}
    return subprocess.run(
        [sys.executable, "-m", "curious_robot.main"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=60,
    )


def test_main_exits_1_without_api_key():
    proc = _run_main_without_key()
    assert proc.returncode == 1
    assert "OLLAMA_API_KEY" in proc.stdout
    assert "not set" in proc.stdout
