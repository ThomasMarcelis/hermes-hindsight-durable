"""Retained provider buffer ownership across switches."""
import pytest
from unittest.mock import MagicMock

def _make_hindsight_provider():
    """Build a bare HindsightMemoryProvider that skips network setup.

    We instantiate without importing optional deps at class-level by
    bypassing __init__ and seeding the attributes on_session_switch
    reads/writes. This keeps the test hermetic.
    """
    import threading
    hindsight_mod = __import__("hindsight_test_provider")
    provider = object.__new__(hindsight_mod.HindsightMemoryProvider)
    provider._session_id = "old-sid"
    provider._parent_session_id = ""
    provider._document_id = "old-sid-20260101_000000_000000"
    provider._session_turns = ["turn-1", "turn-2"]
    provider._turn_counter = 2
    provider._turn_index = 2
    # Attrs read by _build_metadata / _build_retain_kwargs when the
    # buffer-flush path on session switch fires. Empty strings keep the
    # metadata minimal but well-formed.
    provider._retain_source = ""
    provider._platform = ""
    provider._user_id = ""
    provider._user_name = ""
    provider._chat_id = ""
    provider._chat_name = ""
    provider._chat_type = ""
    provider._thread_id = ""
    provider._agent_identity = ""
    provider._agent_workspace = ""
    provider._retain_tags = []
    provider._retain_context = "test-context"
    provider._retain_async = False
    provider._bank_id = "test-bank"
    provider._bank_id_template = ""
    provider._bank_id_fallback = "test-bank"
    provider._observation_scopes = None
    provider._observation_scope_exclude_tag_prefixes = []
    # Prefetch state the switch path drains/clears.
    provider._prefetch_thread = None
    provider._prefetch_lock = threading.Lock()
    provider._prefetch_result = ""
    provider._prefetch_count = 0
    provider._prefetch_generation = 0
    provider._prefetch_request_token = 0
    provider._prefetch_result_generation = -1
    provider._prefetch_result_session_id = ""
    provider._prefetch_result_request_token = -1
    # Sync thread tracking (legacy alias at the writer).
    provider._sync_thread = None
    # Writer queue infra the flush-on-switch path enqueues onto. We stub
    # _ensure_writer / _register_atexit so no real thread is spawned;
    # tests exercising flush delivery live in
    # test_hindsight_provider.py where the full
    # writer-queue wiring is in place.
    import queue as _queue
    provider._retain_queue = _queue.Queue()
    provider._shutting_down = threading.Event()
    provider._delivery_lock = threading.RLock()
    provider._active_delivery_state = None
    provider._delivery_states = []
    provider._last_retained_turn_count = 0
    provider._queued_retained_turn_count = 0
    provider._atexit_registered = True
    provider._ensure_writer = lambda: None
    provider._register_atexit = lambda: None
    # Mode + API state used by _resolve_retain_target; stub the resolver
    # so tests don't actually probe the API. Real probe behavior is
    # exercised by tests in test_hindsight_provider.py.
    provider._mode = "cloud"
    provider._api_url = ""
    provider._api_key = ""
    provider._client = None
    provider._resolve_retain_target = lambda fb: (fb, None)
    # Stub the network-touching helper so any enqueued flush closure is
    # a no-op if ever drained in a unit test.
    provider._run_hindsight_operation = lambda _op: None
    return provider


def test_hindsight_on_session_switch_updates_session_id_and_mints_fresh_doc():
    provider = _make_hindsight_provider()
    old_doc = provider._document_id

    provider.on_session_switch(
        "new-sid", parent_session_id="old-sid", reset=False, reason="resume"
    )

    assert provider._session_id == "new-sid"
    assert provider._parent_session_id == "old-sid"
    # Document id MUST be fresh — else next retain overwrites old session doc
    assert provider._document_id != old_doc
    assert provider._document_id.startswith("new-sid-")


def test_hindsight_on_session_switch_clears_turn_buffers():
    """Accumulated _session_turns must not leak into the next session.

    Hindsight batches turns under a single _document_id. If the buffer
    isn't cleared on switch, the next retain under the new _document_id
    flushes turns that belong to the previous session.
    """
    provider = _make_hindsight_provider()
    provider.on_session_switch("new-sid", parent_session_id="old-sid")
    assert provider._session_turns == []
    assert provider._turn_counter == 0
    assert provider._turn_index == 0
