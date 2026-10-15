"""Native setup validates provisioned dependencies before committing configuration."""

import importlib
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from hindsight_test_provider import HindsightMemoryProvider
from hindsight_test_provider import embedded, setup


@pytest.fixture
def setup_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    installed = tmp_path / "plugins" / "hindsight"
    installed.parent.mkdir()
    installed.symlink_to(Path(__file__).resolve().parents[1] / "hindsight", target_is_directory=True)
    monkeypatch.setattr(setup, "_secret_prompt", lambda label: "")
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    monkeypatch.setattr(setup._hs_templates, "supported_for_mode", lambda mode: False)
    return tmp_path


def test_embedded_setup_missing_runtime_preserves_existing_configuration(setup_home, monkeypatch, capsys):
    profile_config = setup_home / "hindsight" / "config.json"
    profile_config.parent.mkdir()
    profile_config.write_text('{"mode": "local_external", "bank_id": "existing"}')
    env = setup_home / ".env"
    env.write_text("HINDSIGHT_API_KEY=fixture-key\n")
    config = {"memory": {"provider": "builtin"}}
    before = (profile_config.read_bytes(), env.read_bytes())
    selections = iter(("local_embedded", "openai"))
    monkeypatch.setattr(setup, "_select", lambda *args: next(selections))
    monkeypatch.setattr("hermes_cli.memory_setup.prepare_memory_provider_dependencies", lambda name: ({}, "installed"))
    monkeypatch.setitem(sys.modules, "hindsight", None)

    HindsightMemoryProvider().post_setup(str(setup_home), config)

    assert (profile_config.read_bytes(), env.read_bytes()) == before
    assert config == {"memory": {"provider": "builtin"}}
    assert not (setup_home / ".hindsight").exists()
    output = capsys.readouterr().out
    assert "local_external" in output
    assert "configured (" not in output


def test_direct_setup_missing_client_preserves_existing_selection(setup_home, monkeypatch, capsys):
    monkeypatch.setattr(setup, "_select", lambda *args: "local_external")
    monkeypatch.setitem(sys.modules, "hindsight_client", None)
    monkeypatch.setattr("hermes_cli.memory_setup.prepare_memory_provider_dependencies", lambda name: ({}, "installed"))
    config = {"memory": {"provider": "builtin"}}

    HindsightMemoryProvider().post_setup(str(setup_home), config)

    assert config == {"memory": {"provider": "builtin"}}
    assert not (setup_home / "hindsight").exists()
    assert not (setup_home / ".env").exists()
    assert "restart Hermes" in capsys.readouterr().out


def test_native_setup_prepares_dependencies_once(setup_home, monkeypatch):
    from hermes_cli.memory_setup import cmd_setup_provider
    from plugins.memory import find_provider_dir, load_memory_provider

    assert find_provider_dir("hindsight").resolve() == Path(__file__).resolve().parents[1] / "hindsight"
    provider = load_memory_provider("hindsight", register_skills=False)
    native_setup = importlib.import_module(type(provider).__module__ + ".setup")
    monkeypatch.setattr(native_setup, "_select", lambda *args: "local_external")
    monkeypatch.setattr(native_setup, "_secret_prompt", lambda label: "")
    monkeypatch.setattr(native_setup._hs_templates, "supported_for_mode", lambda mode: False)
    monkeypatch.setitem(sys.modules, "hindsight_client", ModuleType("hindsight_client"))
    prepare = Mock(return_value=({}, "installed"))
    monkeypatch.setattr("hermes_cli.memory_setup.prepare_memory_provider_dependencies", prepare)

    cmd_setup_provider("hindsight")

    prepare.assert_called_once_with("hindsight")
    saved = json.loads((setup_home / "hindsight" / "config.json").read_text())
    assert saved["mode"] == "local_external"


def test_embedded_probe_rejects_namespace_without_embedded_client(monkeypatch):
    modules = {
        "hindsight": ModuleType("hindsight"),
        "hindsight_embed.daemon_embed_manager": ModuleType("daemon_embed_manager"),
        "sentence_transformers": ModuleType("sentence_transformers"),
    }
    monkeypatch.setattr(embedded.importlib, "import_module", modules.__getitem__)

    available, reason = embedded._check_local_runtime()

    assert available is False
    assert "HindsightEmbedded" in reason


@pytest.mark.parametrize("missing", ["hindsight_client", "hindsight_embed.daemon_embed_manager", "sentence_transformers", None])
def test_embedded_probe_checks_stack_without_starting_runtime(monkeypatch, missing):
    modules = {
        "hindsight": SimpleNamespace(HindsightEmbedded=lambda **kwargs: pytest.fail("client construction")),
        "hindsight_client": ModuleType("hindsight_client"),
        "hindsight_embed.daemon_embed_manager": ModuleType("daemon_embed_manager"),
        "sentence_transformers": ModuleType("sentence_transformers"),
    }
    def provisioned(name):
        if name == missing:
            raise ImportError(f"{name} missing")
        return modules[name]
    monkeypatch.setattr(embedded.importlib, "import_module", provisioned)

    available, reason = embedded._check_local_runtime()

    assert available is (missing is None)
    if missing is not None:
        assert missing in reason
    else:
        assert reason is None
