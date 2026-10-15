"""Interpreter adapter: private scratch and per-process origin evidence only."""
import json
import os
from pathlib import Path
import runpy
import sys

config = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
args = sys.argv[2:]
# The host shell runner deliberately drops extra variables. Restore only these
# test controls here, after its sanitization; never inherit credentials.
os.environ['UV_OFFLINE'] = '1'
os.environ.setdefault('HERMES_HOME', str(Path(config['run'], 'home', 'profile')))
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
if args and args[0].endswith('/scripts/run_tests_parallel.py'):
    sys.executable = str(Path(config['run'], 'python'))
    sys.argv = args
    namespace = runpy.run_path(args[0], run_name='isolated_runner')
    namespace['main'].__globals__['_runner_scratch_root'] = lambda: config['scratch']
    namespace['main'].__globals__['_sweep_killed_run_roots'] = lambda root: None
    raise SystemExit(namespace['main']())
if args[:2] == ['-m', 'pytest']:
    import pytest
    import agent.memory_provider
    import plugins.memory
    expected = Path(config['host'])
    assert Path(agent.memory_provider.__file__).resolve().is_relative_to(expected)
    assert Path(plugins.memory.__file__).resolve().is_relative_to(expected)

    class Origins:
        def pytest_sessionfinish(self, session, exitstatus):
            origins, foreign = {}, {}
            for name, module in list(sys.modules.items()):
                filename = getattr(module, '__file__', None)
                if not filename:
                    continue
                path = Path(filename).resolve()
                if name.split('.')[0] in {'agent', 'hermes_cli', 'gateway', 'tui_gateway', 'plugins', 'pm'} or name in {'run_agent', 'hermes_state'}:
                    origins[name] = str(path)
                    if not path.is_relative_to(expected):
                        foreign[name] = str(path)
                if name.startswith('_hermes_user_memory.hindsight'):
                    origins[name] = str(path)
            Path(config['run'], 'origins', f'{os.getpid()}.json').write_text(json.dumps({
                'pid': os.getpid(), 'exit': int(exitstatus), 'origins': origins,
                'foreign_host_modules': foreign,
                'tests': [str(item.fspath) for item in session.items],
            }, indent=2) + '\n', encoding='utf-8')
            if foreign:
                session.exitstatus = 1

    raise SystemExit(pytest.main(args[2:], plugins=[Origins()]))
os.execv(config['python'], [config['python'], *args])
