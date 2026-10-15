"""Exercise native discovery; alias only the resulting module for legacy unit tests."""
import importlib
import os
from pathlib import Path
import sys
import tempfile

import pytest

import tests.conftest  # capture the command-scoped home before our disposable install

pytest_plugins = ["tests.conftest"]
PLUGIN = Path(__file__).resolve().parents[1] / "hindsight"
BOOTSTRAP_HOME = Path(tempfile.mkdtemp(prefix="hindsight-test-home-"))
os.environ["HERMES_HOME"] = str(BOOTSTRAP_HOME)


def install_provider(home):
    target = Path(home) / "plugins" / "hindsight"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.symlink_to(PLUGIN, target_is_directory=True)
    return target


install_provider(BOOTSTRAP_HOME)
from plugins.memory import find_provider_dir, load_memory_provider

assert find_provider_dir("hindsight").resolve() == PLUGIN, "bundled provider shadows external implementation"
_provider = load_memory_provider("hindsight", register_skills=False)
assert _provider is not None
MODULE = sys.modules[type(_provider).__module__]
assert Path(MODULE.__file__).resolve().parent == PLUGIN
# No core override: this test-only alias points at the native loader's exact module.
sys.modules["hindsight_test_provider"] = MODULE
for suffix in ("settings", "setup", "embedded", "durability"):
    sys.modules[f"hindsight_test_provider.{suffix}"] = importlib.import_module(f"{MODULE.__name__}.{suffix}")


@pytest.fixture(autouse=True)
def native_provider(_isolate_hermes_home):
    from hermes_constants import get_hermes_home
    install_provider(get_hermes_home())


@pytest.fixture(autouse=True)
def offline_transport(monkeypatch):
    import socket
    def refuse(*args, **kwargs):
        raise OSError("offline provider test: network connections are forbidden")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
