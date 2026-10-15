"""Hindsight setup admits its PM candidate before committing any configuration."""
from types import SimpleNamespace


def test_dependency_admission_failure_keeps_configuration_unchanged(tmp_path, monkeypatch, capsys):
    from hindsight_test_provider import setup
    from pm.package import InstallError

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    config = {"memory": {"provider": "existing"}}
    env = tmp_path / ".env"
    env.write_text("HINDSIGHT_API_KEY=existing-fixture\n")
    before = env.read_bytes()
    monkeypatch.setattr(setup, "_select", lambda *args: "local_external")
    def refuse(name):
        assert name == "hindsight"
        raise InstallError(name, "fixture conflict", remedy="repair the declared candidate")
    monkeypatch.setattr("hermes_cli.memory_setup.prepare_memory_provider_dependencies", refuse)
    setup.run_setup(SimpleNamespace(_config={}), str(tmp_path), config)
    assert env.read_bytes() == before
    assert config == {"memory": {"provider": "existing"}}
    assert not (tmp_path / "hindsight").exists()
    assert "fixture conflict" in capsys.readouterr().out
