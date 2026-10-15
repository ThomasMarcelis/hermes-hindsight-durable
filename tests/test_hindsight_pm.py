"""Hindsight setup admits its PM candidate before committing any configuration."""
from pathlib import Path

import pytest


def test_dependency_admission_failure_keeps_configuration_unchanged(tmp_path, monkeypatch, capsys):
    from hermes_cli.memory_setup import cmd_setup_provider
    from pm.package import InstallError

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    config = {"memory": {"provider": "existing"}}
    env = tmp_path / ".env"
    env.write_text("HINDSIGHT_API_KEY=existing-fixture\n")
    before = env.read_bytes()
    installed = tmp_path / "plugins" / "hindsight"
    installed.parent.mkdir()
    installed.symlink_to(Path(__file__).resolve().parents[1] / "hindsight", target_is_directory=True)
    def refuse(name):
        assert name == "hindsight"
        raise InstallError(name, "fixture conflict", remedy="repair the declared candidate")
    monkeypatch.setattr("hermes_cli.memory_setup.prepare_memory_provider_dependencies", refuse)
    with pytest.raises(InstallError, match="fixture conflict"):
        cmd_setup_provider("hindsight")
    assert env.read_bytes() == before
    assert config == {"memory": {"provider": "existing"}}
    assert not (tmp_path / "hindsight").exists()
