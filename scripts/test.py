"""Isolated offline launcher for the paired host's canonical test runner."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', type=Path, required=True)
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--scratch', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('tests', nargs='*', type=Path)
    args = parser.parse_args()
    host, python = args.host.resolve(), args.python.absolute()
    source = Path(__file__).resolve().parents[1]
    args.output.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix='run-', dir=args.output.resolve()))
    scratch = Path(tempfile.mkdtemp(prefix='hindsight-tests-', dir=args.scratch.resolve()))
    (run / 'home').mkdir()
    (run / 'origins').mkdir()
    config = dict(host=str(host), python=str(python), scratch=str(scratch), run=str(run))
    (run / 'config.json').write_text(json.dumps(config))
    wrapper = run / 'python'
    wrapper.write_text('#!/bin/sh\nexec ' + shlex.join([
        str(python), str(source / 'scripts/test_entry.py'), str(run / 'config.json'),
    ]) + ' "$@"\n')
    wrapper.chmod(0o700)
    env = {'HOME': str(run / 'home'), 'HERMES_HOME': str(run / 'home/profile'),
           'TMPDIR': str(scratch), 'HERMES_PYTHON': str(wrapper),
           'PATH': str(python.parent) + os.pathsep + os.defpath,
           'PYTHONDONTWRITEBYTECODE': '1', 'UV_OFFLINE': '1',
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_TERMINAL_PROMPT': '0', 'LANG': 'C.UTF-8'}
    # uv is a tool, not an activated environment; only its containing directory is inherited.
    import shutil
    uv = shutil.which('uv')
    if uv:
        env['PATH'] = str(Path(uv).parent) + os.pathsep + env['PATH']
    cmd = ['/bin/bash', str(host / 'scripts/run_tests.sh'), '-j', '4', '--file-retries', '0',
           *map(str, args.tests or [source / 'tests'])]
    def identities():
        return {str(repo): {
            'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(),
            'tree': subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], cwd=repo, text=True).strip(),
            'status': subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo, text=True),
        } for repo in (host, source)}
    before = identities()
    with (run / 'test.log').open('w') as log:
        result = subprocess.run(cmd, cwd=host, env=env, stdout=log, stderr=subprocess.STDOUT)
    after = identities()
    receipt = dict(command=cmd, environment=env, exit=result.returncode,
                   before=before, after=after, sources_unchanged=before == after,
                   origins=[str(p) for p in sorted((run / 'origins').glob('*.json'))],
                   log=str(run / 'test.log'))
    (run / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'receipt': str(run / 'receipt.json'), 'exit': result.returncode}))
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
