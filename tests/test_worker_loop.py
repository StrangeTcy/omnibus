"""Offline contract doubles: these tests do NOT prove authenticated execution."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from par.db import Store
from par.runtime import Runtime
from par.schemas import Submission, Budget
from par.workers.base import WorkerFailure
from par.workers.mock import MockWorker
from par.workers.codex_sdk import CodexSdkWorker
from par.smoke import smoke, readiness
from par.local_task import verify_summary, FIXTURE


class FakeSdk:
    __version__ = '0.160.0'
    Sandbox = NS(read_only='read-only', workspace_write='workspace-write')
    ApprovalMode = NS(deny_all='deny_all')
    CodexConfig = NS
    ExternalMessage = NS

    def __init__(self):
        self.auth = True
        self.error = None
        self.output = 'valid'
        self.wait = False
        self.completed_then_lost = False
        self.interrupt_error = False
        self.threads = {}
        self.calls = []
        self.turn_count = 0
        self.interrupts = 0
        self.entered = asyncio.Event()
        self.started = []
        self.resumed = []
        self.AsyncCodex = self.client

    def client(self, config=None):
        owner = self
        class Client:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def account(self):
                return NS(account=object() if owner.auth else None)
            async def thread_start(self, **options):
                id = 'thread-'+str(len(owner.threads)+1)
                owner.threads[id] = NS(id=id, session_id='session', model='test-model', model_provider='test-provider', turns=[])
                owner.started.append(options)
                return owner.thread(id, options)
            async def thread_resume(self, id, **options):
                owner.resumed.append((id, options))
                return owner.thread(id, options)
        return Client()

    def thread(self, id, options):
        owner = self
        class Thread:
            async def read(self, *, include_turns=False):
                assert include_turns
                return NS(thread=owner.threads[id])
            async def turn(self, prompt):
                owner.turn_count += 1
                record = NS(id='turn-'+str(owner.turn_count), status='inProgress', duration_ms=1, items=[])
                owner.threads[id].turns.append(record)
                owner.calls.append(prompt.content)
                class Handle:
                    async def run(self):
                        if owner.error:
                            record.status = 'failed'
                            raise owner.error
                        if options['sandbox'] == 'workspace-write':
                            path = Path(options['cwd'])/'summary.json'
                            if owner.output == 'valid':
                                path.write_text('{"total_units":5,"total_cents":1975}')
                            elif owner.output == 'invalid':
                                path.write_text('{"total_units":false,"total_cents":1}')
                        owner.entered.set()
                        if owner.wait:
                            await asyncio.Event().wait()
                        record.status = 'completed'
                        record.items = [NS(root=NS(type='agentMessage', text='OMNIBUS_READY', phase='final_answer'))]
                        if owner.completed_then_lost:
                            owner.completed_then_lost = False
                            raise asyncio.CancelledError()
                        return NS(id=record.id, status='completed', final_response='OMNIBUS_READY', usage=None,
                                  duration_ms=1, started_at=1, completed_at=2)
                    async def interrupt(self):
                        owner.interrupts += 1
                        if owner.interrupt_error:
                            raise RuntimeError('interrupt transport lost')
                        if record.status != 'completed':
                            record.status = 'interrupted'
                        return NS()
                handle = Handle()
                handle.id = record.id
                return handle
        thread = Thread()
        thread.id = id
        return thread


@pytest.fixture
def rig(tmp_path, monkeypatch):
    from par.workers import codex_sdk
    fake = FakeSdk()
    monkeypatch.setattr(codex_sdk, 'sdk', lambda: fake)
    monkeypatch.setattr(codex_sdk, 'check_local_configuration', lambda *args: None)
    return Runtime(Store(tmp_path/'data'), CodexSdkWorker()), fake


def task(rt, seconds=10):
    return rt.accept(Submission(text='Answer', budget=Budget(seconds=seconds, retries=2)))


def test_real_only_smoke_and_readiness(rig):
    rt, sdk = rig
    sdk.auth = False
    ready = asyncio.run(readiness('codex'))
    assert not ready['available'] and ready['error_kind'] == 'authentication'
    run = asyncio.run(smoke(rt))
    assert run['status'] == 'failed' and run['error_kind'] == 'authentication'
    assert not sdk.started
    with pytest.raises(ValueError, match='mock rejected'):
        asyncio.run(smoke(Runtime(rt.store, MockWorker())))
    assert not asyncio.run(readiness('mock'))['available']


def test_complete_restart_and_conversation(rig):
    rt, sdk = rig
    first = asyncio.run(smoke(rt))
    assert first['verification'] == 'passed'
    assert first['turn_id'] and first['worker_metadata']['session_id'] == 'session'
    assert first['worker_metadata']['configured_model'] == 'test-model'
    old_artifacts = {id: rt.artifacts.read(id) for id in first['result_artifacts']}
    restarted = Runtime(Store(rt.store.root), CodexSdkWorker())
    restarted.store.recover()
    assert restarted.store.get('runs', first['id'])['response'] == 'OMNIBUS_READY'
    next = restarted.continue_run(first['id'], 'Continue the conversation')
    asyncio.run(restarted.execute(next['run_id']))
    second = restarted.store.get('runs', next['run_id'])
    assert second['thread_id'] == first['thread_id'] and second['turn_id'] != first['turn_id']
    assert sdk.resumed[-1][0] == first['thread_id']
    assert second['workspace_id'] == first['workspace_id']
    assert all(rt.artifacts.read(id) == data for id, data in old_artifacts.items())
    with pytest.raises(ValueError, match='original'):
        Runtime(rt.store, MockWorker()).continue_run(first['id'], 'bad')


@pytest.mark.parametrize('interrupt_error', [False, True])
def test_cancel_calls_sdk_interrupt_and_preserves_partial_file(rig, interrupt_error):
    rt, sdk = rig
    sdk.wait = True
    sdk.interrupt_error = interrupt_error
    async def scenario():
        obj = rt.accept(Submission(text='fixture', execution_mode='workspace_write', authorize_workspace_write=True,
                                   fixture='sales-summary', budget=Budget(retries=2)))
        rt.schedule(obj['run_id'])
        await sdk.entered.wait()
        rt.cancel(obj['run_id'])
        await rt.shutdown()
        run = rt.store.get('runs', obj['run_id'])
        assert run['status'] == 'cancelled' and run['error_kind'] == 'cancelled'
        assert sdk.interrupts == 1
        assert run['worker_metadata']['interrupt'] == ('uncertain' if interrupt_error else 'acknowledged')
        assert run['workspace_output'] and run['verification'] == 'unverified'
        assert not run['worker_checkpoint']
    asyncio.run(scenario())


def test_timeout_and_failure_taxonomy(rig):
    rt, sdk = rig
    sdk.wait = True
    obj = task(rt, seconds=.02)
    asyncio.run(rt.execute(obj['run_id']))
    run = rt.store.get('runs', obj['run_id'])
    assert run['status'] == 'paused' and run['error_kind'] == 'timeout'
    assert sdk.interrupts == 1 and sdk.turn_count == 1
    sdk.wait = False
    for error, kind in [(RuntimeError('401 unauthorized'), 'authentication'), (RuntimeError('service unavailable'), 'provider'),
                        (RuntimeError('sandbox unavailable'), 'sandbox')]:
        sdk.error = error
        obj = task(rt)
        asyncio.run(rt.execute(obj['run_id']))
        run = rt.store.get('runs', obj['run_id'])
        assert run['status'] == 'failed' and run['error_kind'] == kind
        assert str(error) not in run['error']


def test_reconcile_completed_remote_turn_without_replay(rig):
    rt, sdk = rig
    sdk.completed_then_lost = True
    obj = task(rt)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(rt.execute(obj['run_id']))
    before = rt.store.get('runs', obj['run_id'])
    assert before['turn_id'] and before['status'] == 'paused' and not before['worker_checkpoint']
    restarted = Runtime(Store(rt.store.root), CodexSdkWorker())
    restarted.store.recover()
    run = restarted.retry(before['id'], True)
    asyncio.run(restarted.execute(run['id']))
    after = restarted.store.get('runs', run['id'])
    assert after['status'] == 'completed' and after['response'] == 'OMNIBUS_READY'
    assert sdk.turn_count == 1
    assert after['worker_metadata']['reconciled'] is True


def test_uncertain_remote_turn_not_replayed(rig):
    rt, sdk = rig
    sdk.completed_then_lost = True
    obj = task(rt)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(rt.execute(obj['run_id']))
    prior = rt.store.get('runs', obj['run_id'])
    sdk.threads[prior['thread_id']].turns[0].status = 'inProgress'
    run = rt.retry(prior['id'], True)
    asyncio.run(rt.execute(run['id']))
    after = rt.store.get('runs', run['id'])
    assert after['status'] == 'paused' and after['error_kind'] == 'uncertain'
    assert sdk.turn_count == 1


def test_checkpoint_recovery_preserves_workspace_and_artifacts(rig, monkeypatch):
    rt, sdk = rig
    original = rt.registry.execute
    def fail_after_result(name, payload, run_id):
        if payload['kind'] == 'response':
            raise OSError('simulated persistence failure')
        return original(name, payload, run_id)
    monkeypatch.setattr(rt.registry, 'execute', fail_after_result)
    obj = task(rt)
    asyncio.run(rt.execute(obj['run_id']))
    old = rt.store.get('runs', obj['run_id'])
    assert old['status'] == 'failed' and old['worker_checkpoint']
    workspace = rt.store.root/'workspaces'/old['workspace_id']
    (workspace/'completed-work.txt').write_text('keep')
    checkpoint = rt.artifacts.read(old['worker_checkpoint'])
    restarted = Runtime(Store(rt.store.root), CodexSdkWorker())
    new = restarted.retry(old['id'], True)
    asyncio.run(restarted.execute(new['id']))
    assert restarted.store.get('runs', new['id'])['status'] == 'completed'
    assert sdk.turn_count == 1
    assert (workspace/'completed-work.txt').read_text() == 'keep'
    assert rt.artifacts.read(old['worker_checkpoint']) == checkpoint
    with pytest.raises(ValueError, match='mismatch'):
        Runtime(rt.store, MockWorker()).retry(old['id'], True)


@pytest.mark.parametrize('output,expected', [('valid', 'passed'), ('invalid', 'failed'), ('missing', 'failed')])
def test_writable_task_oracle_and_boundary_configuration(rig, output, expected):
    rt, sdk = rig
    sdk.output = output
    with pytest.raises(ValueError, match='authorize'):
        asyncio.run(smoke(rt, writable=True))
    run = asyncio.run(smoke(rt, writable=True, authorized=True))
    assert run['verification'] == expected
    assert run['status'] == ('completed' if expected == 'passed' else 'failed')
    if expected == 'failed':
        assert run['error_kind'] == 'verification'
    opts = sdk.started[-1]
    assert opts['ephemeral'] is False
    assert opts['sandbox'] == 'workspace-write' and opts['approval_mode'] == 'deny_all'
    assert opts['config']['sandbox_workspace_write'] == dict(writable_roots=[], network_access=False,
                                                            exclude_slash_tmp=True, exclude_tmpdir_env_var=True)
    assert opts['config']['shell_environment_policy']['inherit'] == 'none'
    assert verify_summary(FIXTURE, b'{"total_units":true,"total_cents":1975}')['verification'] == 'failed'


def test_interrupted_writable_task_resume_reuses_partial_work(rig):
    rt, sdk = rig
    sdk.wait = True
    async def first_attempt():
        obj = rt.accept(Submission(text='fixture', execution_mode='workspace_write', authorize_workspace_write=True,
                                   fixture='sales-summary', budget=Budget(retries=2)))
        rt.schedule(obj['run_id'])
        await sdk.entered.wait()
        await rt.shutdown()
        return rt.store.get('runs', obj['run_id'])
    old = asyncio.run(first_attempt())
    assert old['status'] == 'paused' and old['workspace_output']
    old_bytes = rt.artifacts.read(old['workspace_output'])
    workspace = rt.store.root/'workspaces'/old['workspace_id']
    (workspace/'completed-work.txt').write_text('keep')
    sdk.wait = False
    sdk.output = 'missing'  # Writes nothing; the previously completed file survives.
    restarted = Runtime(Store(rt.store.root), CodexSdkWorker())
    new = restarted.retry(old['id'], True)
    asyncio.run(restarted.execute(new['id']))
    run = restarted.store.get('runs', new['id'])
    assert run['status'] == 'completed' and run['verification'] == 'passed'
    assert (workspace/'completed-work.txt').read_text() == 'keep'
    assert rt.artifacts.read(old['workspace_output']) == old_bytes
    assert run['workspace_output'] != old['workspace_output']


def test_writable_invalid_then_explicit_repair_creates_new_version(rig):
    rt, sdk = rig
    sdk.output = 'invalid'
    old = asyncio.run(smoke(rt, writable=True, authorized=True))
    prior = rt.artifacts.read(old['workspace_output'])
    sdk.output = 'valid'
    new = rt.retry(old['id'], True)
    asyncio.run(rt.execute(new['id']))
    run = rt.store.get('runs', new['id'])
    assert run['verification'] == 'passed' and sdk.turn_count == 2
    assert rt.artifacts.read(old['workspace_output']) == prior
    assert run['workspace_output'] != old['workspace_output']


def test_unknown_turn_start_gap_refuses_blind_replay(rig):
    rt, sdk = rig
    sdk.completed_then_lost = True
    obj = task(rt)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(rt.execute(obj['run_id']))
    # Simulate crash between remote turn/start success and SQLite turn-id write.
    rt.store.update('runs', obj['run_id'], {'turn_id': None})
    new = rt.retry(obj['run_id'], True)
    asyncio.run(rt.execute(new['id']))
    run = rt.store.get('runs', new['id'])
    assert run['error_kind'] == 'uncertain' and sdk.turn_count == 1


def test_missing_workspace_fails_closed(rig):
    rt, sdk = rig
    sdk.error = RuntimeError('provider unavailable')
    obj = task(rt)
    asyncio.run(rt.execute(obj['run_id']))
    old = rt.store.get('runs', obj['run_id'])
    (rt.store.root/'workspaces'/old['workspace_id']).rmdir()
    new = rt.retry(old['id'], True)
    asyncio.run(rt.execute(new['id']))
    assert rt.store.get('runs', new['id'])['error_kind'] == 'workspace_missing'
    assert sdk.turn_count == 1


def test_no_write_authorization_and_symlink_output(rig, tmp_path):
    rt, sdk = rig
    with pytest.raises(ValueError, match='authorization'):
        rt.accept(Submission(text='write', execution_mode='workspace_write', fixture='sales-summary'))
    from par.local_task import capture
    obj = task(rt)
    workspace = tmp_path/'links'
    workspace.mkdir()
    outside = tmp_path/'private.txt'
    outside.write_text('outside workspace')
    try:
        (workspace/'summary.json').symlink_to(outside)
    except OSError:
        pytest.skip('OS account cannot create symlinks')
    with pytest.raises(ValueError, match='symlink'):
        capture(rt, obj['run_id'], workspace)


def test_cli_mock_smoke_refused(tmp_path):
    import subprocess, sys
    result = subprocess.run([sys.executable, '-m', 'par', '--data-root', str(tmp_path), 'smoke', '--worker', 'mock'], capture_output=True, text=True, timeout=30)
    assert result.returncode == 2 and 'mock rejected' in result.stderr
    result = subprocess.run([sys.executable, '-m', 'par', 'worker-ready', '--worker', 'mock'], capture_output=True, text=True, timeout=30)
    assert result.returncode == 1 and not json.loads(result.stdout)['available']


def test_provider_raw_diagnostics_not_saved(rig):
    rt, sdk = rig
    sdk.error = RuntimeError('OPAQUE_PROVIDER_DIAGNOSTIC_MUST_NOT_BE_PERSISTED')
    obj = task(rt)
    asyncio.run(rt.execute(obj['run_id']))
    run = rt.store.get('runs', obj['run_id'])
    stored = json.dumps(run) + json.dumps(rt.store.events())
    stored += ''.join(rt.artifacts.read(a['id']).decode(errors='replace') for a in rt.store.list('artifacts'))
    assert 'OPAQUE_PROVIDER_DIAGNOSTIC_MUST_NOT_BE_PERSISTED' not in stored


def test_fixture_mutation_cannot_change_oracle(rig):
    rt, sdk = rig
    run = asyncio.run(smoke(rt, writable=True, authorized=True))
    from par.local_task import verify_run
    workspace = rt.store.root/'workspaces'/run['workspace_id']
    (workspace/'input.json').write_text('{"sales": []}')
    report, _ = verify_run(rt, run['id'])
    assert report['verification'] == 'failed' and 'modified' in report['reason']


def test_sdk_timeout_is_not_generic_provider_failure(rig):
    rt, sdk = rig
    sdk.error = TimeoutError('opaque transport deadline')
    obj = task(rt)
    asyncio.run(rt.execute(obj['run_id']))
    run = rt.store.get('runs', obj['run_id'])
    assert run['error_kind'] == 'timeout' and run['status'] == 'paused'
