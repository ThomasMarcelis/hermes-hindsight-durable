"""Native provider settlement and foreground ownership boundaries, with an offline SDK."""
import json
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import hindsight_test_provider as hindsight
from agent.memory_manager import MemoryManager


@pytest.fixture
def provider(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(hindsight, "_check_api_supports_update_mode_append", lambda *args: True)
    provider = hindsight.HindsightMemoryProvider()
    provider.save_config({"mode": "local_external", "api_url": "http://example.invalid",
                          "bank_id_template": "bank-{session}", "recall_sync": True,
                          "retain_async": False}, str(tmp_path))
    provider.initialize("A")
    provider._client = SimpleNamespace(aretain_batch=AsyncMock(return_value=SimpleNamespace()),
        arecall=AsyncMock(return_value=SimpleNamespace(results=[SimpleNamespace(text="new memory")])),
        operations=SimpleNamespace(get_operation_status=AsyncMock(return_value=SimpleNamespace(status="completed"))),
        documents=SimpleNamespace(delete_document=AsyncMock()), aclose=AsyncMock())
    yield provider
    provider.shutdown()


def test_queued_switch_fences_actual_retain_and_recall(provider, monkeypatch):
    import agent.memory_manager as module
    monkeypatch.setattr(module, "_SESSION_SWITCH_TIMEOUT_S", 0.0)
    manager = MemoryManager()
    manager.add_provider(provider)
    entered, release = threading.Event(), threading.Event()
    def old_work():
        entered.set()
        assert release.wait(5)
    try:
        manager._submit_background(old_work)
        assert entered.wait(5)
        manager.queue_session_switch("B")
        assert "error" in json.loads(manager.handle_tool_call("hindsight_retain", {"content": "new fact"}))
        assert manager.prefetch_all("new question", session_id="B") == ""
        provider._client.aretain_batch.assert_not_called()
        provider._client.arecall.assert_not_called()
        release.set()
        assert manager.flush_pending(timeout=5)
        assert json.loads(manager.handle_tool_call("hindsight_retain", {"content": "new fact"}))["result"] == "Memory stored successfully."
        assert "new memory" in manager.prefetch_all("new question", session_id="B")
        assert provider._client.aretain_batch.call_args.kwargs["bank_id"] == "bank-B"
        assert provider._client.arecall.call_args.kwargs["bank_id"] == "bank-B"
        manager.queue_session_switch("A")
        assert manager.flush_pending(timeout=5)
        manager.handle_tool_call("hindsight_retain", {"content": "back in A"})
        assert provider._client.aretain_batch.call_args.kwargs["bank_id"] == "bank-A"
    finally:
        release.set()
        manager.shutdown_all()


def test_skipped_rewind_preserves_pending_operation_ownership(provider):
    provider._retain_async = True
    provider._client.aretain_batch.return_value = SimpleNamespace(operation_id="accepted-A")
    provider.sync_turn("question", "answer", messages=[{"role": "assistant", "message_uid": "answer-A"}])
    provider._retain_queue.join()
    state = provider._active_delivery_state
    assert state.remote_pending
    provider.on_session_switch("A", rewound=True, rewound_turns=1, rewound_message_uids=("skipped-B",))
    assert provider._active_delivery_state is state
    assert not state.invalidated
    assert "accepted-A" in provider._pending_retain_ops
    assert provider.drain_pending(timeout=5)
    assert not provider._pending_retain_ops
    assert len(state.confirmed_turns) == 1
    provider._client.documents.delete_document.assert_not_called()
    provider._client.aretain_batch.assert_awaited_once()


def test_equal_content_turns_use_identity_and_retry_does_not_revoke_survivor(provider):
    for uid in ("answer-A", "answer-B"):
        provider.sync_turn("same question", "same answer", messages=[{"role": "assistant", "message_uid": uid}])
        assert provider.drain_pending(timeout=5)
    provider.on_session_switch("A", rewound=True, rewound_turns=1, rewound_message_uids=("answer-B",))
    assert provider.drain_pending(timeout=5)
    content = json.loads(provider._client.aretain_batch.call_args.kwargs["items"][0]["content"])
    assert [turn[-1]["message_uid"] for turn in content] == ["answer-A"]
    provider.sync_turn("same question", "retry answer", messages=[{"role": "assistant", "message_uid": "answer-C"}])
    assert provider.drain_pending(timeout=5)
    state = provider._active_delivery_state
    turns = state.confirmed_turns + provider._session_turns
    assert [json.loads(turn)[-1]["message_uid"] for turn in turns] == ["answer-A", "answer-C"]
    provider._client.documents.delete_document.assert_not_called()
