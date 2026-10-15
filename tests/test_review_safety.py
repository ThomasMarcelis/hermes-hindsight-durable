"""Remote ownership is not established by a process-local append ledger."""
import asyncio
import json
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import hindsight_test_provider as hindsight


class RemoteDocuments:
    def __init__(self):
        self.documents = {}
        self.calls = []
        self.outcome = "confirmed"
        self.facts = {}
        self.started = threading.Event()
        self.hold = None

    async def retain(self, *, bank_id, items, **kwargs):
        for item in items:
            key = (bank_id, kwargs['document_id'])
            mode = item.get('update_mode')
            content = json.loads(item['content'])
            self.calls.append((mode, key, content))
            self.documents[key] = self.documents.get(key, []) + content if mode == 'append' else content
            self.facts[key] = {row['content'] for exchange in self.documents[key] for row in exchange}
        self.started.set()
        if self.hold is not None:
            await self.hold.wait()
        if self.outcome == 'timeout':
            raise TimeoutError('synthetic acknowledgement lost')
        if self.outcome == 'pending':
            return SimpleNamespace(operation_id='pending-write')
        return SimpleNamespace()

    async def delete(self, bank_id, document_id):
        self.calls.append(('delete', (bank_id, document_id), []))
        self.documents.pop((bank_id, document_id), None)
        self.facts.pop((bank_id, document_id), None)

    def client(self):
        return SimpleNamespace(aretain_batch=self.retain,
            documents=SimpleNamespace(delete_document=self.delete),
            operations=SimpleNamespace(get_operation_status=AsyncMock(return_value=SimpleNamespace(status='completed'))),
            aclose=AsyncMock())


@pytest.fixture
def factory(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    monkeypatch.setattr(hindsight, '_check_api_supports_update_mode_append', lambda *args: True)
    providers = []
    def create(remote, session='A'):
        p = hindsight.HindsightMemoryProvider()
        p.save_config({'mode':'local_external','api_url':'http://example.invalid','auto_recall':False,'retain_async':False},str(tmp_path))
        p.initialize(session)
        p._client = remote.client()
        providers.append(p)
        return p
    yield create
    for p in providers:
        p.shutdown(settlement_timeout=0.1)


def turn(provider, uid, text):
    provider.sync_turn('question', text, messages=[{'role':'assistant','message_uid':uid}])
    provider._retain_queue.join()


@pytest.mark.parametrize('revisit', [False, True], ids=['new-lifetime','a-b-a'])
@pytest.mark.parametrize('outcome', ['confirmed','pending','timeout'])
def test_rewind_cannot_destroy_prior_document_ownership(factory, revisit, outcome):
    remote = RemoteDocuments()
    first = factory(remote)
    turn(first, 'old-A', 'prior retained answer')
    assert first.drain_pending(timeout=2)
    if revisit:
        first.on_session_switch('B')
        first.on_session_switch('A')
        resumed = first
    else:
        first.shutdown()
        resumed = factory(remote)
    remote.outcome = outcome
    resumed._retain_async = outcome == 'pending'
    turn(resumed, 'new-A', 'answer to undo')
    remote.outcome = 'confirmed'
    resumed.on_session_switch('A', rewound=True, rewound_message_uids=('new-A',), rewound_turns=1)
    resumed.drain_pending(timeout=2)
    turn(resumed, 'retry-A', 'retry answer')
    resumed.drain_pending(timeout=2)
    assert not any(mode in ('replace','delete') for mode, _, _ in remote.calls)
    contents = [row['content'] for exchange in remote.documents[('hermes','A')] for row in exchange]
    assert contents.count('Assistant: prior retained answer') == 1
    assert 'Assistant: retry answer' in contents
    assert 'Assistant: prior retained answer' in remote.facts[('hermes', 'A')]


def test_message_ids_remain_local(factory):
    remote=RemoteDocuments(); p=factory(remote)
    turn(p, 'internal-row-identity', 'answer')
    assert 'message_uid' not in json.dumps(remote.documents[('hermes','A')])
    assert 'internal-row-identity' in ''.join(p._active_delivery_state.confirmed_turns)


def test_unavailable_embedded_mode_is_inert(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    monkeypatch.setattr(hindsight, '_check_local_runtime', lambda: (False, 'fixture absent runtime'))
    p=hindsight.HindsightMemoryProvider()
    p.save_config({'mode':'local_embedded'},str(tmp_path))
    p.initialize('disabled')
    assert p._mode == 'disabled'
    created=[]
    monkeypatch.setattr(p, '_new_cloud_client', lambda: created.append(True) or RemoteDocuments().client())
    try:
        p.sync_turn('question','answer')
        p.queue_prefetch('question')
        assert p.prefetch('question') == ''
        result=json.loads(p.handle_tool_call('hindsight_retain',{'content':'fact'}))
        assert 'error' in result
        assert p.get_tool_schemas() == []
        assert not created
        assert p._writer_thread is None
    finally:
        p.shutdown(settlement_timeout=0.1)


def test_sync_timeout_cancels_local_coroutine():
    cancelled=threading.Event()
    async def pending():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    with pytest.raises(TimeoutError):
        hindsight._run_sync(pending(), timeout=0.1)
    assert cancelled.wait(2), 'timed-out local task must receive cancellation'


def test_settled_shutdown_releases_ledger_and_exit_registration(factory):
    p=factory(RemoteDocuments())
    turn(p,'row','answer')
    assert p.drain_pending(timeout=2)
    p.shutdown()
    assert not p._atexit_registered
    assert not p._session_turns
    assert not p._delivery_states
    assert p._active_delivery_state is None


def test_missing_host_contract_fails_closed(monkeypatch):
    from agent import memory_provider
    from plugins.memory import load_memory_provider
    monkeypatch.delattr(memory_provider, 'MEMORY_LIFECYCLE_API_VERSION')
    provider = load_memory_provider('hindsight', register_skills=False)
    assert provider is not None
    assert not provider.is_available()
    with pytest.raises(RuntimeError, match='memory lifecycle API 1'):
        provider.initialize('unsupported')
    assert provider.get_tool_schemas() == []
    assert provider.system_prompt_block() == ''
    assert 'error' in json.loads(provider.handle_tool_call('hindsight_recall', {'query':'fixture'}))
    assert provider._client is None


def test_shared_document_rewind_preserves_pending_survivor_delivery(factory):
    remote=RemoteDocuments(); p=factory(remote)
    p._retain_every_n_turns=2; p._retain_async=True
    remote.outcome='pending'
    turn(p,'survivor','keep')
    turn(p,'removed','undo')
    old=p._active_delivery_state
    assert old.remote_pending
    p.on_session_switch('A',rewound=True,rewound_message_uids=('removed',))
    assert not old.invalidated
    assert 'pending-write' in p._pending_retain_ops
    assert p.drain_pending(timeout=2)
    assert not p._pending_retain_ops
    assert len(remote.calls)==1
    assert [row['content'] for exchange in remote.documents[('hermes','A')] for row in exchange].count('Assistant: keep')==1


def test_legacy_ambiguous_write_cannot_delete_previous_lifetime(factory, monkeypatch):
    monkeypatch.setattr(hindsight, '_check_api_supports_update_mode_append', lambda *args: False)
    remote=RemoteDocuments(); first=factory(remote)
    turn(first,'old','old retained'); first.shutdown()
    older=dict(remote.documents)
    second=factory(remote);remote.outcome='timeout'
    turn(second,'new','uncertain retained')
    remote.outcome='confirmed'
    second.on_session_switch('A',rewound=True,rewound_message_uids=('new',))
    second.drain_pending(timeout=2)
    turn(second,'retry','retry');second.drain_pending(timeout=2)
    for key,value in older.items():
        assert remote.documents[key]==value
    assert not any(mode=='delete' for mode,_,_ in remote.calls)


def test_queued_switch_without_ids_never_revokes_known_survivor(factory):
    remote=RemoteDocuments();p=factory(remote)
    turn(p,'survivor','keep')
    state=p._active_delivery_state
    p.on_session_switch('A',rewound=True,rewound_message_uids=(),rewound_turns=1)
    assert p._active_delivery_state is state
    assert len(remote.calls)==1


@pytest.mark.parametrize('outcome', ['confirmed', 'pending'])
def test_rewind_while_remote_request_is_unacknowledged(factory, outcome):
    remote = RemoteDocuments()
    first = factory(remote)
    turn(first, 'old', 'older lifetime')
    first.shutdown()
    resumed = factory(remote)
    remote.started.clear()
    remote.hold = asyncio.Event()
    remote.outcome = outcome
    resumed._retain_async = outcome == 'pending'
    resumed.sync_turn('question', 'unacknowledged', messages=[{'role': 'assistant', 'message_uid': 'removed'}])
    assert remote.started.wait(2)
    old = resumed._active_delivery_state
    resumed.on_session_switch('A', rewound=True, rewound_message_uids=('removed',))
    assert not old.invalidated
    async def release():
        remote.hold.set()
    hindsight._run_sync(release())
    resumed._retain_queue.join()
    assert resumed.drain_pending(timeout=2)
    assert not any(mode in ('replace', 'delete') for mode, _, _ in remote.calls)
    assert 'Assistant: older lifetime' in remote.facts[('hermes', 'A')]


def test_sdk_failures_do_not_echo_request_secrets_or_transcripts(factory, caplog):
    import logging
    remote = RemoteDocuments()
    provider = factory(remote)
    sensitive = 'fixture-secret-and-private-transcript'
    provider._client.aretain_batch = AsyncMock(side_effect=RuntimeError(sensitive))
    provider._client.arecall = AsyncMock(side_effect=RuntimeError(sensitive))
    with caplog.at_level(logging.DEBUG):
        result = provider.handle_tool_call('hindsight_retain', {'content': sensitive})
        assert 'error' in json.loads(result)
        assert sensitive not in result
        turn(provider, 'local-id', sensitive)
        provider._auto_recall = True
        provider._recall_sync = True
        assert provider.prefetch('question') == ''
    assert sensitive not in caplog.text


@pytest.mark.parametrize('storage', ['memory', 'sqlite', 'resumed'])
@pytest.mark.parametrize('surface', ['cli', 'tui'])
@pytest.mark.parametrize('outcome', ['completed', 'interrupted', 'empty'])
def test_real_finalizer_to_provider_retry_preserves_surviving_memory(factory, tmp_path, monkeypatch, storage, surface, outcome):
    from hermes_state import SessionDB
    from tests.agent.test_memory_live_rewind_identity import _LiveAgent, _finish, _rewind

    monkeypatch.setattr('hermes_cli.plugins.invoke_hook', lambda *args, **kwargs: [])
    remote = RemoteDocuments()
    provider = factory(remote, session='sess-test')
    db = SessionDB(db_path=tmp_path / 'state.db') if storage != 'memory' else None
    if db is not None:
        db.create_session('sess-test', source='cli')
    agent = _LiveAgent(db, provider)
    try:
        history = _finish(agent, [], 'first', 'completed')
        first_uid = history[-1]['message_uid']
        if storage == 'resumed':
            agent._memory_manager.shutdown_all()
            history = db.get_resume_conversations(agent.session_id)[0]
            provider = factory(remote, session='sess-test')
            agent = _LiveAgent(db, provider)
        history = _finish(agent, history, 'second', outcome)
        history = _rewind(agent, history, surface, 'retry')
        assert agent._memory_manager.flush_pending(timeout=5)
        assert history[-1]['message_uid'] == first_uid
        history = _finish(agent, history, 'second', 'completed')
        assert history[-1]['message_uid'] != first_uid
        _rewind(agent, history, surface, 'undo')
        assert agent._memory_manager.flush_pending(timeout=5)
        assert 'Assistant: answer to first' in remote.facts[('hermes', 'sess-test')]
        assert not any(mode in ('replace', 'delete') for mode, _, _ in remote.calls)
        assert 'message_uid' not in json.dumps(list(remote.documents.values()))
    finally:
        agent._memory_manager.shutdown_all()
        if db is not None:
            db.close()
