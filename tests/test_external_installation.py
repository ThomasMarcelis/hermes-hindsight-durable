"""A native directory installation works outside both source trees and across profiles."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def test_external_copies_discovered_outside_checkout_and_rebound_a_b_a(tmp_path):
    source = Path(__file__).resolve().parents[1] / "hindsight"
    for name in ("a", "b"):
        home = tmp_path / name
        installed = home / "plugins" / "hindsight"
        shutil.copytree(source, installed, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (home / "hindsight").mkdir()
        (home / "config.yaml").write_text("memory:\n  provider: hindsight\n")
        (home / "hindsight/config.json").write_text(json.dumps({
            "mode": "local_external", "api_url": f"http://{name}.invalid", "auto_retain": False,
            "auto_recall": False, "expose_retain_tool": False, "bank_id_template": "bank-{profile}-{session}",
        }))
    user_home = tmp_path / "user-home"
    user_home.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    env = {**os.environ, "HOME": str(user_home), "HERMES_HOME": str(tmp_path / "a")}
    result = subprocess.run([sys.executable, "-I", str(Path(__file__).with_name("external_probe.py")), str(tmp_path)],
                            cwd=outside, env=env, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads(result.stdout)
    assert [Path(p).parent for p in evidence["providers"]] == [tmp_path / n / "plugins/hindsight" for n in ("a", "b", "a")]
    print(json.dumps(evidence))
