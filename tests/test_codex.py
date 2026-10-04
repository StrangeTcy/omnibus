import asyncio
import os
import pytest
from par.workers.codex_sdk import health, CodexSdkWorker
from par.runtime import Runtime
from par.db import Store
from par.schemas import Submission

@pytest.mark.live
def test_live_codex(tmp_path):
    if os.environ.get('PAR_LIVE_CODEX') != '1':
        pytest.skip('Opt-in live test: set PAR_LIVE_CODEX=1 to check SDK/session and invoke Codex')
    status = asyncio.run(health())
    assert status['available'], status['diagnostic']
    runtime = Runtime(Store(tmp_path), CodexSdkWorker())
    obj = runtime.accept(Submission(text='Reply with the word ready. Do not use tools.'))
    asyncio.run(runtime.execute(obj['run_id']))
    run = runtime.store.get('runs', obj['run_id'])
    assert run['status'] == 'completed', run['error']
    assert 'ready' in run['response'].lower()
    assert run['thread_id']


def test_codex_rejects_inherited_external_tools(tmp_path, monkeypatch):
    from par.workers.codex_sdk import check_local_configuration
    monkeypatch.setenv('CODEX_HOME', str(tmp_path))
    (tmp_path/'config.toml').write_text('[mcp_servers.example]\ncommand="unsafe"\n')
    with pytest.raises(RuntimeError, match='refuses inherited'):
        check_local_configuration()


def test_sdk_contract_when_installed():
    import inspect
    sdk = pytest.importorskip('openai_codex', reason='Optional SDK not installed; core has no SDK dependency')
    assert 'cwd' in inspect.signature(sdk.AsyncCodex.thread_start).parameters
    assert 'sandbox' in inspect.signature(sdk.AsyncCodex.thread_resume).parameters
    assert 'tool_name' in inspect.signature(sdk.ExternalMessage).parameters
    assert sdk.Sandbox.read_only.value == 'read-only'
    assert sdk.ApprovalMode.deny_all.value == 'deny_all'
    assert 'input' in inspect.signature(sdk.AsyncThread.turn).parameters
    assert 'include_turns' in inspect.signature(sdk.AsyncThread.read).parameters
    assert list(inspect.signature(sdk.AsyncTurnHandle.interrupt).parameters) == ['self']
    assert 'cwd' in inspect.signature(sdk.CodexConfig).parameters
    from openai_codex.generated.v2_all import TurnStatus, AgentMessageThreadItem
    assert TurnStatus.in_progress.value == 'inProgress'
    assert {'text', 'phase', 'type'} <= AgentMessageThreadItem.model_fields.keys()


@pytest.mark.live
def test_live_writable_codex(tmp_path):
    if os.environ.get('PAR_LIVE_CODEX') != '1':
        pytest.skip('Explicit opt-in required: PAR_LIVE_CODEX=1; this authorizes the bounded workspace fixture')
    from par.smoke import smoke
    runtime = Runtime(Store(tmp_path), CodexSdkWorker())
    run = asyncio.run(smoke(runtime, writable=True, authorized=True))
    assert run['status'] == 'completed', run['error']
    assert run['verification'] == 'passed'
    assert run['workspace_output'] and run['thread_id'] and run['turn_id']
    restarted = Runtime(Store(tmp_path), CodexSdkWorker())
    restarted.store.recover()
    assert restarted.store.get('runs', run['id'])['verification'] == 'passed'
    next = restarted.continue_run(run['id'], 'What file did you produce in the previous turn? Do not use tools.')
    asyncio.run(restarted.execute(next['run_id']))
    result = restarted.store.get('runs', next['run_id'])
    assert result['status'] == 'completed', result['error']
    assert result['thread_id'] == run['thread_id']
    assert 'summary.json' in result['response']
