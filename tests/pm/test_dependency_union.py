"""Offline native PM dependency admission for the external provider."""
from pathlib import Path

def test_external_hindsight_dependency_union_builds_without_embedded_server(tmp_path):
    """An external Hindsight server needs only its client in the Hermes process."""
    import json
    import os
    import shutil
    import subprocess
    import sys

    from pm.environment import PythonEnvironment
    from pm.workspace import lock_and_sync
    from tests.pm._fixtures import _wheel

    core, wheels = tmp_path / "core", tmp_path / "wheels"
    core.mkdir()
    wheels.mkdir()
    client_version = "0.6.1"
    _wheel(wheels, "hindsight_client", client_version)
    (core / "pyproject.toml").write_text(
        '[project]\nname="external-memory-host"\nversion="1"\nrequires-python=">=3.11"\n'
        '[tool.uv]\npackage=false\nno-index=true\n'
        f'find-links=[{json.dumps(wheels.as_posix())}]\n', encoding="utf-8",
    )
    uv = shutil.which("uv")
    assert uv, "dependency admission needs the real offline resolver"
    environment = PythonEnvironment(
        uv=Path(uv), python=Path(sys.executable), destination=tmp_path / "venv",
        cache=tmp_path / "cache", env=dict(os.environ), offline=True,
    )
    provider = Path(__file__).resolve().parents[2] / "hindsight"
    lock_and_sync([provider], [], root=tmp_path / "workspace", source=core,
                  seed_lock=None, environment=environment)
    result = subprocess.run(
        [str(environment.executable), "-I", "-c",
         "import importlib.util, hindsight_client; "
         "assert importlib.util.find_spec('hindsight') is None; "
         "assert importlib.util.find_spec('hindsight_embed') is None; "
         "assert importlib.util.find_spec('sentence_transformers') is None; "
         "print(hindsight_client.__version__)"],
        cwd=tmp_path, capture_output=True, text=True, check=True, timeout=30,
    )
    assert result.stdout.strip() == client_version


def test_selected_external_provider_is_admitted_by_setup_and_passive_pm(tmp_path, monkeypatch):
    from hermes_cli.memory_setup import memory_provider_dependency_inputs, prepare_memory_provider_dependencies
    from pm import plugins_state, workspace
    from hermes_constants import get_hermes_home
    import pm

    home = get_hermes_home()
    (home / "config.yaml").write_text("memory:\n  provider: hindsight\n")
    monkeypatch.setattr("pm.environments.dependency_home_root", lambda: home)
    installed = home / "plugins" / "hindsight"
    assert plugins_state.enabled_plugins_ordered()[home / "plugins"] == ["hindsight"]
    assert installed in workspace.enabled_member_dirs()
    meta, inputs = memory_provider_dependency_inputs("hindsight")
    assert meta["python_dependencies"] == ["hindsight-client==0.6.1"]
    assert list(inputs["plugins"].dirs) == [installed]
    admitted = []
    monkeypatch.setattr(pm, "sync_venv", lambda **kwargs: admitted.append(kwargs))
    prepare_memory_provider_dependencies("hindsight")
    assert admitted[0]["explicit"] is True
    assert list(admitted[0]["plugins"].dirs) == [installed]
