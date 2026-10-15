"""Subprocess probe invoked outside either source checkout. No network client is created."""
import json
import sys
from pathlib import Path
from types import ModuleType

from agent.memory_manager import MemoryManager
from agent import secret_scope
from gateway.run import _profile_runtime_scope
from plugins.memory import find_provider_dir, load_memory_provider
from hermes_cli.memory_setup import memory_provider_dependency_inputs

base = Path(sys.argv[1])
modules, calls, providers = [], [], []
sdk = ModuleType("hindsight_client")
sdk.Hindsight = lambda **kwargs: calls.append(kwargs) or object()
sys.modules["hindsight_client"] = sdk
secret_scope.set_multiplex_active(True)
for name in ("a", "b", "a"):
    home = base / name
    with _profile_runtime_scope(home, {"HINDSIGHT_API_KEY": f"fixture-{name}"}):
        installed = home / "plugins" / "hindsight"
        assert find_provider_dir("hindsight") == installed
        meta, inputs = memory_provider_dependency_inputs("hindsight")
        assert list(inputs["plugins"].dirs) == [installed]
        assert meta["python_dependencies"] == ["hindsight-client==0.6.1"]
        provider = load_memory_provider("hindsight", register_skills=False)
        module = sys.modules[type(provider).__module__]
        assert Path(module.__file__).parent == installed
        manager = MemoryManager()
        provider.initialize(f"{name}-first", agent_identity=name, platform="cli")
        manager.add_provider(provider)
        assert provider._bank_id == f"bank-{name}-{name}-first"
        manager.queue_session_switch(f"{name}-second")
        assert manager.flush_pending(timeout=5)
        assert provider._bank_id == f"bank-{name}-{name}-second"
        provider._new_cloud_client()
        assert provider._client is None
        assert "hindsight_retain" not in manager.get_all_tool_names()
        # Built-in memory writes must not create a provider client or a queued mirror.
        manager.on_memory_write("add", "memory", "fixture native memory")
        assert manager.flush_pending(timeout=5)
        assert provider._client is None
        modules.append(module.__name__)
        providers.append(str(Path(module.__file__).resolve()))
        manager.shutdown_all()
assert modules[0] == modules[2] and modules[0] != modules[1]
assert [c["api_key"] for c in calls] == ["fixture-a", "fixture-b", "fixture-a"]
assert [c["base_url"] for c in calls] == ["http://a.invalid", "http://b.invalid", "http://a.invalid"]
print(json.dumps({"providers": providers, "manager": sys.modules["agent.memory_manager"].__file__, "sessions": ["a", "b", "a"]}))
