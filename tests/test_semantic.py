"""Protocol/validation tests use explicitly synthetic responses, NOT model evidence."""
import asyncio
import json
import pytest
import httpx
from par.db import Store
from par.semantic import SemanticService, AnalysisRequest, TextMaterial, validate_answer
from par.local_inference import LocalModelConfig, Ollama
from par.knowledge import Knowledge
from par.knowledge_models import Activity
from par.library import Library
from par.recommendations import Recommender
from par.workers.base import WorkerFailure

TEXT = 'Functions compose by passing the output of one function as the input of another. Composition is associative.'
OTHER = 'A composition combines two mappings in sequence. Composition is associative, so parentheses can be moved.'

@pytest.fixture
def service(tmp_path):
    s = SemanticService(Store(tmp_path/'data'))
    s.config(LocalModelConfig(backend='ollama', model='fixture:local'))
    return s


def materials(s):
    ids = []
    for i, text in enumerate([TEXT, OTHER]):
        resource = s.import_text(TextMaterial(title=f'Synthetic material {i}', text=text))
        ids.append(next(n['id'] for n in s.store.list('nodes') if n['parent_id'] == resource['id']))
    return ids


def answer(ids):
    return {'concepts': [{'label': 'Composition', 'description': 'Combining functions in sequence is associative.',
             'confidence': .8, 'evidence': [{'source_id': id, 'quote': quote, 'relation': 'covers'} for id, quote in zip(ids, ['Composition is associative.', 'Composition is associative, so parentheses can be moved.'])]}],
            'limitations': 'Synthetic protocol fixture; quotes do not establish whole-book equivalence.'}


def stub(monkeypatch, ids, invalid=False):
    async def generate(self, messages, schema):
        sources = json.loads(messages[1]['content'])['sources']
        assert {s['id'] for s in sources} == set(ids)
        assert schema['properties']['concepts']
        value = answer(ids)
        if invalid:
            value['concepts'][0]['evidence'][0]['quote'] = 'This sentence is fabricated.'
        return json.dumps(value), {'model': 'SYNTHETIC TEST DOUBLE', 'prompt_eval_count': 42, 'eval_count': 12}
    monkeypatch.setattr(Ollama, 'generate', generate)


def test_material_graph_review_recommendation_restart(service, monkeypatch):
    ids = materials(service)
    stub(monkeypatch, ids)
    obj = service.submit(AnalysisRequest(source_ids=ids, authorize_local_inference=True))
    asyncio.run(service.runtime.execute(obj['run_id']))
    run = service.store.get('runs', obj['run_id'])
    assert run['status'] == 'completed', run
    graph = Knowledge(service.store)
    edges = graph.edges()
    assert len(edges) == 1 and len(edges[0]['members']) == 3
    assert edges[0]['status'] == 'proposed'
    graph.activity(ids[0], Activity(kind='reading', start=0, end=100))
    assert Recommender(service.store).generate() == []
    service.review(run['id'], 'confirmed')
    assert graph.edges()[0]['status'] == 'confirmed'
    recs = Recommender(service.store).generate()
    other = service.store.get('nodes', ids[1])['parent_id']
    assert len(recs) == 1 and recs[0]['candidate_id'] == other and recs[0]['overlap_concepts']
    reopened = SemanticService(Store(service.store.root))
    assert reopened.config().model == 'fixture:local'
    assert reopened.analyses()[0]['worker_metadata']['semantic']['review'] == 'confirmed'
    assert len(Knowledge(reopened.store).edges()) == 1


def test_invented_quote_is_quarantined_no_graph(service, monkeypatch):
    ids = materials(service)
    stub(monkeypatch, ids, invalid=True)
    obj = service.submit(AnalysisRequest(source_ids=ids, authorize_local_inference=True))
    asyncio.run(service.runtime.execute(obj['run_id']))
    run = service.store.get('runs', obj['run_id'])
    assert run['status'] == 'failed' and run['error_kind'] == 'invalid_output'
    assert not Knowledge(service.store).edges()
    assert not [n for n in service.store.list('nodes') if n['node_type'] == 'concept']
    assert any(a['kind'] == 'semantic-model-output' for a in service.store.list('artifacts'))


def test_requires_authorization_and_actual_text(service):
    ids = materials(service)
    with pytest.raises(ValueError, match='authorization'):
        service.submit(AnalysisRequest(source_ids=ids))
    assert not service.store.list('runs')
    with pytest.raises(ValueError, match='distinct'):
        service.submit(AnalysisRequest(source_ids=[ids[0], ids[0]], authorize_local_inference=True))


def test_source_file_hash_and_scope(service, tmp_path):
    books = tmp_path/'books'; books.mkdir()
    path = books/'section.md'; path.write_text('# A heading\n'+TEXT*50)
    library = Library(service.store)
    root = library.configure(str(books))
    library.scan(root['id'])
    unit = next(n for n in service.store.list('nodes') if n['node_type'] == 'unit')
    source = service.source(unit['id'])
    assert len(source['text']) == 2000 and 'first 2000' in source['scope']
    path.write_text('Source replaced')
    with pytest.raises(ValueError, match='Source changed'):
        service.source(unit['id'])


@pytest.mark.parametrize('endpoint', ['https://example.com', 'http://192.168.1.1:11434', 'http://user:password@localhost', 'http://localhost/path', 'http://localhost?key=secret'])
def test_remote_and_credential_endpoints_refused(endpoint):
    with pytest.raises(ValueError):
        LocalModelConfig(endpoint=endpoint)


def test_disabled_backend_never_mock(service):
    ids = materials(service)
    service.config(LocalModelConfig())
    obj = service.submit(AnalysisRequest(source_ids=ids, authorize_local_inference=True))
    asyncio.run(service.runtime.execute(obj['run_id']))
    run = service.store.get('runs', obj['run_id'])
    assert run['status'] == 'failed' and run['error_kind'] == 'configuration'
    assert not Knowledge(service.store).edges()


def test_ollama_wire_contract(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path == '/api/tags':
            return httpx.Response(200, json={'models': [{'name': 'fixture:local', 'digest': 'test-digest'}]})
        if request.url.path == '/api/show':
            return httpx.Response(200, json={'model_info': {'architecture': 'test-only'}})
        data = json.loads(request.content)
        assert data['stream'] is False and isinstance(data['format'], dict)
        assert 'tools' not in data and data['model'] == 'fixture:local'
        return httpx.Response(200, json={'done': True, 'done_reason': 'stop', 'model': 'fixture:local', 'message': {'content': '{}'}})
    original = httpx.AsyncClient
    def client(**kwargs):
        assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
        return original(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(httpx, 'AsyncClient', client)
    result, meta = asyncio.run(Ollama(LocalModelConfig(backend='ollama', model='fixture:local')).generate([], {'type': 'object'}))
    assert result == '{}' and meta['installed_digest'] == 'test-digest'
    assert calls == ['/api/tags', '/api/show', '/api/chat']


def test_cloud_alias_refused(monkeypatch):
    async def request(self, method, path, body=None):
        return {'models': [{'name': 'alias:local'}]} if path == '/api/tags' else {'remote_host': 'https://remote.invalid', 'model_info': {'architecture': 'x'}}
    monkeypatch.setattr(Ollama, 'request', request)
    with pytest.raises(WorkerFailure, match='cloud'):
        asyncio.run(Ollama(LocalModelConfig(backend='ollama', model='alias:local')).ready())


def test_cancellation_does_not_install_proposals(service, monkeypatch):
    ids = materials(service)
    async def flow():
        entered = asyncio.Event()
        async def generate(self, messages, schema):
            entered.set()
            await asyncio.Event().wait()
        monkeypatch.setattr(Ollama, 'generate', generate)
        obj = service.submit(AnalysisRequest(source_ids=ids, authorize_local_inference=True))
        service.runtime.schedule(obj['run_id'])
        await asyncio.wait_for(entered.wait(), 2)
        service.runtime.cancel(obj['run_id'])
        await service.runtime.shutdown()
        assert service.store.get('runs', obj['run_id'])['status'] == 'cancelled'
    asyncio.run(flow())
    assert not Knowledge(service.store).edges()


def test_api_and_csrf(tmp_path):
    from fastapi.testclient import TestClient
    from par.api import create_app
    from par.config import Config
    app = create_app(Config(tmp_path/'api'))
    with TestClient(app) as client:
        page = client.get('/life')
        assert 'Analyze material with your browser accounts' in page.text
        import re
        csrf = re.search(r'const LIFE_CSRF="([^"]+)"', page.text).group(1)
        assert client.post('/api/life/semantic/text', json={'title':'Fixture','text':TEXT}).status_code == 403
        headers = {'X-PAR-CSRF': csrf}
        response = client.post('/api/life/semantic/text', headers=headers, json={'title':'Fixture','text':TEXT})
        assert response.status_code == 200
        state = client.get('/api/life/state').json()
        assert state['analyses'] == [] and not state['semantic']['configured']
        response = client.post('/api/life/semantic/health', headers=headers)
        assert response.status_code == 200 and response.json()['error_kind'] == 'configuration'
        response = client.put('/api/life/semantic/config', headers=headers, json={'endpoint':'http://remote.example','model':'x','backend':'ollama'})
        assert response.status_code == 422


def test_retry_after_installed_proposal_does_not_regenerate(service, monkeypatch):
    ids = materials(service)
    stub(monkeypatch, ids)
    obj = service.submit(AnalysisRequest(source_ids=ids, authorize_local_inference=True))
    asyncio.run(service.runtime.execute(obj['run_id']))
    # Simulate persistence interruption AFTER graph commit but BEFORE the normal
    # worker checkpoint exists. Recovery must reuse the durable raw output.
    with service.store.connect() as db:
        db.execute("UPDATE runs SET data=json_set(data,'$.status','paused','$.worker_checkpoint',NULL) WHERE id=?", (obj['run_id'],))
        db.execute("UPDATE tasks SET data=json_set(data,'$.status','paused') WHERE id=?", (obj['task_id'],))
    async def never_call(*args):
        raise AssertionError('Must not call a model again after persisted proposal')
    monkeypatch.setattr(Ollama, 'generate', never_call)
    retry = service.runtime.retry(obj['run_id'], acknowledge_uncertainty=True)
    asyncio.run(service.runtime.execute(retry['id']))
    assert service.store.get('runs', retry['id'])['status'] == 'completed'
    assert len(Knowledge(service.store).edges()) == 1
