"""Skipped transcript turns cannot revoke an earlier durable retained exchange."""
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.memory_manager import MemoryManager
from hermes_state import SessionDB
from hindsight_test_provider import HindsightMemoryProvider


@pytest.mark.parametrize("retry", [False, True])
@pytest.mark.parametrize("skipped", ["interrupted", "empty"])
def test_skipped_turn_rewind_preserves_retained_exchange(tmp_path, monkeypatch, retry, skipped):
    from run_agent import AIAgent
    from tui_gateway import session_workdir
    import hindsight_test_provider as hindsight

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(hindsight, "_check_api_supports_update_mode_append", lambda *a: True)
    provider = HindsightMemoryProvider()
    provider.save_config({"mode": "local_external", "api_url": "http://example.invalid",
                          "auto_recall": False, "retain_async": False}, str(tmp_path))
    provider.initialize("session-A")
    writes, deletes = [], []
    async def retain(**kwargs):
        writes.append(kwargs)
        return SimpleNamespace()
    async def delete(*args, **kwargs):
        deletes.append((args, kwargs))
    provider._client = SimpleNamespace(aretain_batch=retain, documents=SimpleNamespace(delete_document=delete), aclose=AsyncMock())
    manager = MemoryManager()
    manager.add_provider(provider)
    agent = SimpleNamespace(_memory_manager=manager, session_id="session-A", _last_flushed_db_idx=0,
                            _db_flush_scan_prefix=[], _invalidate_system_prompt=lambda: None)
    db = SessionDB(db_path=tmp_path / "state.db")
    db.create_session("session-A", source="tui")
    @contextmanager
    def session_db(_session):
        yield db
    monkeypatch.setattr(session_workdir, "_session_db", session_db)
    try:
        db.append_message("session-A", "user", "completed question")
        db.append_message("session-A", "assistant", "surviving answer")
        history = db.get_messages_as_conversation("session-A")
        AIAgent._sync_external_memory_for_turn(agent, original_user_message="completed question",
                                              final_response="surviving answer", interrupted=False, messages=history)
        assert manager.flush_pending(timeout=5)
        assert len(writes) == 1
        db.append_message("session-A", "user", "skipped question")
        db.append_message("session-A", "assistant", "partial" if skipped == "interrupted" else "")
        history = db.get_messages_as_conversation("session-A")
        AIAgent._sync_external_memory_for_turn(agent, original_user_message="skipped question",
                                              final_response="partial" if skipped == "interrupted" else "",
                                              interrupted=skipped == "interrupted", messages=history)
        session = {"session_key": "session-A", "history": history, "agent": agent}
        installed, _, _ = session_workdir._rewind_active_session_history(session, 1, require_retryable=retry)
        assert manager.flush_pending(timeout=5)
        assert [m["content"] for m in installed] == ["completed question", "surviving answer"]
        assert deletes == [], "undo/retry of a non-retained turn must not delete the surviving document"
        assert len(writes) == 1
        state = provider._active_delivery_state
        assert len(state.confirmed_turns) + len(provider._session_turns) == 1
    finally:
        manager.shutdown_all()
        db.close()
