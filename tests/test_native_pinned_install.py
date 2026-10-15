"""Real Git subdirectory install and PM publication against an offline fixture graph.

The source revision is HEAD, never an uncommitted working copy. The PM host graph
and wheel are synthetic; cloning, admission, publication and resolution are real.
"""
import importlib
import json
import os
from pathlib import Path
import subprocess

from tests.pm._fixtures import (
    _wheel,
    client as client,
    isolated_python as isolated_python,
    worker_toolchain,
)


def test_pinned_native_install_setup_and_profile_discovery(client, isolated_python, tmp_path, monkeypatch):
    from hermes_cli import plugins_cmd
    from hermes_cli.memory_setup import cmd_setup_provider
    from pm import paths
    from pm.environments import selected_venv
    from plugins.memory import find_provider_dir, load_memory_provider
    from agent.memory_provider import MEMORY_LIFECYCLE_API_VERSION

    source = Path(__file__).resolve().parents[1]
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    identifier = source.as_uri() + '#hindsight'
    core, wheels = tmp_path / 'core', tmp_path / 'wheels'
    core.mkdir(); wheels.mkdir()
    _wheel(wheels, 'hindsight_client', '0.6.1')
    (core / 'pyproject.toml').write_text(
        '[project]\nname="memory-install-fixture"\nversion="1"\nrequires-python=">=3.11"\n'
        '[project.optional-dependencies]\nall=[]\n[tool.uv]\npackage=false\nno-index=true\n'
        f'find-links=[{json.dumps(str(wheels))}]\n')
    monkeypatch.setattr(paths, 'repo_root', lambda: core)
    worker_toolchain(client, monkeypatch, isolated_python)
    monkeypatch.setattr(client, 'is_runtime', lambda: False)
    client.lock_project(core)
    assert MEMORY_LIFECYCLE_API_VERSION >= 1
    monkeypatch.chdir(tmp_path)
    seen = []
    for profile in ('alpha', 'beta'):
        home = tmp_path / 'home' / 'profiles' / profile
        home.mkdir(parents=True)
        monkeypatch.setenv('HERMES_HOME', str(home))
        (home / 'config.yaml').write_text('memory:\n  provider: hindsight\nplugins:\n  isolation: in_process\n')
        # This is the native command with the same source/ref as the documented CLI.
        plugins_cmd.cmd_install(identifier, ref=revision, yes_deps=True, enable=True)
        installed = home / 'plugins/hindsight'
        assert find_provider_dir('hindsight') == installed
        assert not installed.is_symlink()
        record = plugins_cmd._read_install_metadata()['hindsight']
        assert record['revision'] == revision and record['pinned']
        assert record['source'].endswith('#hindsight')
        provider = load_memory_provider('hindsight', register_skills=False)
        assert provider is not None
        module = importlib.import_module(type(provider).__module__)
        assert Path(module.__file__).parent == installed
        native_setup = importlib.import_module(module.__name__ + '.setup')
        monkeypatch.setattr(native_setup, '_select', lambda *args: 'local_external')
        monkeypatch.setattr(native_setup, '_secret_prompt', lambda prompt: '')
        monkeypatch.setattr('builtins.input', lambda prompt: '')
        monkeypatch.setattr(native_setup._hs_templates, 'supported_for_mode', lambda mode: False)
        cmd_setup_provider('hindsight')
        saved = json.loads((home / 'hindsight/config.json').read_text())
        assert saved['mode'] == 'local_external'
        provider.save_config({**saved, 'bank_id': profile, 'auto_recall': False}, str(home))
        monkeypatch.setattr(module, '_check_api_supports_update_mode_append', lambda *args: True)
        provider.initialize('session-A', agent_identity=profile)
        assert provider._bank_id == profile
        assert provider.get_tool_schemas()
        provider.on_session_switch('session-B')
        provider.on_session_switch('session-A')
        provider.shutdown()
        assert not (home / 'memories/MEMORY.md').exists()
        seen.append(str(module.__file__))
        environment = selected_venv(core)
        python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        check = subprocess.run([str(python), '-I', '-c',
            'import hindsight_client, importlib.util; print(hindsight_client.__version__); '
            'assert importlib.util.find_spec("hindsight_embed") is None'],
            cwd=tmp_path, capture_output=True, text=True, timeout=30, check=True)
        assert check.stdout.strip() == '0.6.1'
    assert seen[0] != seen[1]
    print(json.dumps({'native_source': identifier, 'revision': revision, 'origins': seen,
                      'dependency': 'synthetic hindsight-client==0.6.1 wheel',
                      'pm': str(environment)}))
