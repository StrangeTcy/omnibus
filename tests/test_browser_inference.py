"""Simulated DOM/CDP tests; not authenticated-provider acceptance evidence."""
import asyncio
import json
import pytest
from par.browser_inference import BrowserChat, json_reply, same_origin, websocket_endpoint
from par.local_inference import LocalModelConfig
from par.semantic import SemanticService, AnalysisRequest, TextMaterial
from par.db import Store
from par.knowledge import Knowledge
from par.workers.base import WorkerFailure


def config(**kw):
    return LocalModelConfig(backend='browser', dedicated_browser_profile=True, **kw)


def test_browser_config_only_loopback():
    for url in ['http://192.168.1.1:9222', 'http://user:secret@localhost:9222', 'https://public.example', 'http://localhost:9222/path']:
        with pytest.raises(ValueError):
            config(browser_endpoint=url)
    assert config(browser_endpoint='http://localhost:9222').browser_endpoint == 'http://127.0.0.1:9222'


@pytest.mark.parametrize('url', ['ws://remote.example:9222/devtools/browser/a', 'ws://127.0.0.1:1234/devtools/browser/a', 'ws://user:password@127.0.0.1:9222/devtools/browser/a', 'ws://127.0.0.1:9222/elsewhere'])
def test_cdp_discovery_cannot_redirect_to_remote_browser(url):
    with pytest.raises(WorkerFailure):
        websocket_endpoint({'webSocketDebuggerUrl':url}, 'http://127.0.0.1:9222')


def test_origin_and_strict_response():
    assert same_origin('https://chatgpt.com/c/123', 'https://chatgpt.com/')
    for url in ['https://chatgpt.com.attacker.test', 'https://accounts.google.com', 'https://chatgpt.com:8443', 'http://chatgpt.com', 'https://name@chatgpt.com']:
        assert not same_origin(url, 'https://chatgpt.com/')
    assert json_reply('```json\n{"concepts": []}\n```') == '{"concepts": []}'
    for text in ['{"a":1} {"b":2}', 'Some prose\n{"a":1}', '[]', 'x'*100001]:
        with pytest.raises(ValueError):
            json_reply(text)


def test_specific_provider_consent_before_any_job(tmp_path):
    service = SemanticService(Store(tmp_path/'data'))
    service.config(config(browser_provider='claude'))
    for request in [AnalysisRequest(source_ids=['nonexistent'], authorize_local_inference=True),
                    AnalysisRequest(source_ids=['nonexistent'], authorize_provider='chatgpt')]:
        with pytest.raises(ValueError, match='Explicit approval'):
            service.submit(request)
    assert not service.store.list('runs')
    assert not service.store.list('artifacts')


def test_manual_profile_confirmation_required():
    with pytest.raises(WorkerFailure, match='dedicated'):
        asyncio.run(BrowserChat(LocalModelConfig(backend='browser')).ready())


def test_uncertain_send_marker_survives_and_blocks_replay(tmp_path, monkeypatch):
    service = SemanticService(Store(tmp_path/'data'))
    service.config(config())
    resource = service.import_text(TextMaterial(title='Synthetic material', text='A function maps an input to an output. Functions can be composed together.'))
    unit = next(n for n in service.store.list('nodes') if n['parent_id'] == resource['id'])
    calls = []
    async def uncertain(self, messages, schema):
        calls.append(True)
        self.before_send({'provider':'chatgpt','state':'submission_attempted'})
        raise WorkerFailure('uncertain', 'Simulated browser disconnected after text entry')
    monkeypatch.setattr(BrowserChat, 'generate', uncertain)
    obj = service.submit(AnalysisRequest(source_ids=[unit['id']], authorize_provider='chatgpt'))
    asyncio.run(service.runtime.execute(obj['run_id']))
    run = service.store.get('runs', obj['run_id'])
    assert run['status'] == 'paused' and run['error_kind'] == 'uncertain'
    assert run['worker_metadata']['browser_delivery']['provider'] == 'chatgpt'
    assert not Knowledge(service.store).edges()
    retry = service.runtime.retry(run['id'], acknowledge_uncertainty=True)
    asyncio.run(service.runtime.execute(retry['id']))
    assert service.store.get('runs', retry['id'])['error_kind'] == 'uncertain'
    assert len(calls) == 1


class Locator:
    def __init__(self, page, kind):
        self.page, self.kind = page, kind
    @property
    def first(self): return self
    @property
    def last(self): return self
    async def wait_for(self, **kwargs): pass
    async def count(self):
        if self.kind == 'stop': return 0
        if self.kind == 'answer': return int(self.page.submitted)
        return 1
    async def is_editable(self): return True
    async def inner_text(self): return ''
    async def input_value(self): return ''
    async def evaluate(self, script):
        return False if self.kind == 'composer' else '{"concepts": [], "limitations": "Synthetic DOM test, not a live model."}'
    async def fill(self, text):
        assert self.page.journalled, 'Journal must precede even text entry (drafts may autosave)'
        self.page.prompt = text
    async def press(self, key):
        assert key == 'Enter' and self.page.prompt and self.page.journalled
        self.page.submitted += 1
        if self.page.fail_send:
            raise RuntimeError('Simulated connection loss containing private provider text')


class Page:
    def __init__(self, redirect=False, fail_send=False):
        self.redirect, self.fail_send = redirect, fail_send
        self.submitted, self.journalled, self.prompt = 0, False, None
    def set_default_timeout(self, value): pass
    async def goto(self, url, **kwargs):
        self.url = 'https://accounts.google.com/' if self.redirect else url
    def locator(self, selector):
        kind = 'stop' if selector.startswith('button') else 'answer' if any(marker in selector for marker in ['data-message-author-role', 'font-claude-response', 'ds-markdown']) else 'composer'
        return Locator(self, kind)


def install_fake_browser(monkeypatch, page):
    api = pytest.importorskip('playwright.async_api')
    class Fake:
        contexts = []
        async def new_page(self): return page
        async def connect_over_cdp(self, endpoint, timeout): return self
        async def __aenter__(self): return self
        async def __aexit__(self, *exc): return False
        @property
        def chromium(self): return self
    fake = Fake(); fake.contexts = [fake]
    monkeypatch.setattr(api, 'async_playwright', lambda: fake)
    async def ready(self):
        return {'websocket':'ws://127.0.0.1:9222/devtools/browser/test', 'browser_version':'Synthetic browser'}
    monkeypatch.setattr(BrowserChat, 'ready', ready)
    async def no_delay(seconds): pass
    monkeypatch.setattr('par.browser_inference.asyncio.sleep', no_delay)


@pytest.mark.parametrize('provider', ['chatgpt', 'claude', 'deepseek'])
def test_browser_adapter_fills_only_fresh_composer_after_journal(monkeypatch, provider):
    page = Page()
    install_fake_browser(monkeypatch, page)
    def journal(data): page.journalled = True
    reply, meta = asyncio.run(BrowserChat(config(browser_provider=provider), journal).generate([{'role':'user','content':'Test source'}], {'type':'object'}))
    assert json.loads(reply)['concepts'] == [] and page.submitted == 1
    assert 'Test source' in page.prompt and 'response_schema' in page.prompt
    assert meta['transport'] == 'playwright-cdp' and 'unverified' in meta['model']


def test_login_redirect_stops_without_typing_or_sending(monkeypatch):
    page = Page(redirect=True)
    install_fake_browser(monkeypatch, page)
    def never(data): raise AssertionError('Must not journal a send after redirect to login')
    with pytest.raises(WorkerFailure, match='sign-in'):
        asyncio.run(BrowserChat(config(), never).generate([], {}))
    assert not page.submitted and page.prompt is None


def test_after_send_error_is_safe_and_uncertain(monkeypatch):
    page = Page(fail_send=True)
    install_fake_browser(monkeypatch, page)
    def journal(data): page.journalled = True
    with pytest.raises(WorkerFailure) as failure:
        asyncio.run(BrowserChat(config(), journal).generate([], {}))
    assert failure.value.kind == 'uncertain'
    assert 'private provider text' not in str(failure.value)
    assert page.submitted == 1


def test_browser_to_graph_preserves_provider_and_delivery_evidence(tmp_path, monkeypatch):
    service = SemanticService(Store(tmp_path/'data'))
    service.config(config(browser_provider='deepseek'))
    resource = service.import_text(TextMaterial(title='Synthetic source', text='Functions compose in sequence. Composition is associative for these functions.'))
    unit = next(n for n in service.store.list('nodes') if n['parent_id'] == resource['id'])
    async def response(self, messages, schema):
        assert self.config.browser_provider == 'deepseek'
        self.before_send({'provider':'deepseek','state':'submission_attempted'})
        return json.dumps({'concepts':[{'label':'Composition','description':'Functions compose associatively in this passage.', 'confidence':.8,
                            'evidence':[{'source_id':unit['id'],'quote':'Functions compose in sequence.','relation':'covers'}]}],
                           'limitations':'Synthetic response for wiring tests, not evidence of live semantic quality.'}), {'model':'deepseek web UI (model identity unverified)', 'transport':'playwright-cdp'}
    monkeypatch.setattr(BrowserChat, 'generate', response)
    obj = service.submit(AnalysisRequest(source_ids=[unit['id']], authorize_provider='deepseek'))
    # Later settings changes must not redirect an already authorized source snapshot.
    service.config(config(browser_provider='claude'))
    asyncio.run(service.runtime.execute(obj['run_id']))
    run = service.store.get('runs', obj['run_id'])
    assert run['status'] == 'completed', run
    assert run['worker'] == 'semantic-analysis'
    assert run['worker_metadata']['browser_delivery']['provider'] == 'deepseek'
    edge = Knowledge(service.store).edges()[0]
    assert edge['status'] == 'proposed' and 'deepseek web UI' in edge['provenance'][0]['description']
