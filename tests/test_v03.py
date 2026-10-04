"""V0.3 deterministic fixtures / synthetic provider responses, NEVER live evidence."""
import asyncio
import json
import socket
from pathlib import Path
import pytest
from par.db import Store
from par.knowledge import Knowledge, user_evidence, payload
from par.knowledge_models import Node, Edge, Activity, Feedback
from par.semantic import SemanticService, AnalysisRequest, TextMaterial
from par.local_inference import LocalModelConfig, Ollama
from par.discovery import Discovery, DiscoveryRequest, LinkProposal, link_evidence, verified_snapshot, extract, SearchLinks
from par.web_retrieval import Page, public_target, PublicFetcher
from par.recommendations import Recommender
from par.graph_io import export_graph, import_graph

HTML = '''<html><head><title>Crab canon performance</title><meta property="article:published_time" content="2026-09-01T12:00:00Z"></head>
<body><p>This recording illustrates the Crab Canon through a musical reversal.</p><p>This interview features Jane Example as its guest.</p></body></html>'''
URL = 'https://public.example/recording'

class FetchFixture:
    def __init__(self, fail=False): self.calls = []; self.fail = fail
    def fetch(self, url):
        self.calls.append(url)
        if self.fail: raise ValueError('Synthetic network failure; no page retrieved')
        if 'duckduckgo' in url:
            return Page(url, '<a class="result__a" href="'+URL+'">Candidate</a>', 'text/html')
        return Page(url, HTML, 'text/html')

@pytest.fixture
def graph(tmp_path): return Knowledge(Store(tmp_path/'data'))

def node(g, title, **kw): return g.node(Node(title=title, provenance=[user_evidence('Synthetic user assertion')], **kw))

def edge(g, type, members, **kw):
    return g.edge(Edge(type=type, members=[{'node_id':n['id'],'role':r} for n,r in members],
                      provenance=[user_evidence('Synthetic user relationship, not discovered')], explanation='Fixture relation', **kw))

def discovery(g, fetch=None, manual=False):
    focus = node(g, 'Crab Canon', node_type='concept', kind='motif')
    d = Discovery(g.store, fetcher=fetch or FetchFixture())
    report = d.discover(DiscoveryRequest(focus_id=focus['id'], url=URL if manual else None, authorize_network=True))
    return d, focus, report


def test_real_fetch_contract_search_snapshot_candidate_not_recommendation(graph):
    fetch = FetchFixture()
    d, focus, report = discovery(graph, fetch)
    assert len(fetch.calls) == 2 and report['search_performed']
    assert len(report['candidates']) == 1 and report['issues'] == []
    resource = graph.store.get('nodes', report['candidates'][0])
    proof = link_evidence(graph.store, resource)
    assert proof['status'] == 'retrieved' and proof['origin'] == 'public_search'
    assert resource['published'] == '2026-09-01'
    snap = verified_snapshot(graph.store, resource)
    assert snap['search_snapshot'] and snap['raw_artifact'] and snap['text']
    assert Recommender(graph.store).generate() == []  # Retrieval is not relevance.
    unit = next(n for n in graph.store.list('nodes') if n['parent_id'] == resource['id'])
    assert SemanticService(graph.store).source(unit['id'])['text']


def test_recording_path_requires_quoted_relation_and_review(graph):
    d, motif, report = discovery(graph)
    resource = graph.store.get('nodes', report['candidates'][0])
    book = node(graph, 'A read section', total=100)
    edge(graph, 'covers', [(book,'source'), (motif,'concept')])
    graph.activity(book['id'], Activity(kind='position', end=50))
    unquoted = edge(graph, 'illustrates', [(resource,'resource'), (motif,'concept')])
    recs = Recommender(graph.store)
    assert recs.generate() == []  # Even confirmed unquoted discovery claims are insufficient.
    graph.edge_status(unquoted['id'], 'rejected')
    proposal = d.propose_link(resource['id'], LinkProposal(target_id=motif['id'], relation='illustrates', quote='This recording illustrates the Crab Canon through a musical reversal.'))
    assert recs.generate() == []
    graph.edge_status(proposal['id'], 'confirmed')
    result = recs.generate()
    assert len(result) == 1 and result[0]['url'] == URL and result[0]['evidence']
    assert result[0]['why_now'] and result[0]['uncertainties']
    recs.feedback(result[0]['id'], Feedback(action='dismissed'))
    reopened = Store(graph.store.root)
    assert Recommender(reopened).generate() == []
    assert reopened.list('preferences')[0]['scope'] == resource['id']


def test_guest_identity_cannot_be_created_by_search_title(graph):
    d, _, report = discovery(graph)
    target = graph.store.get('nodes', report['candidates'][0])
    person = node(graph, 'Jane Example', kind='person')
    old = node(graph, 'Earlier interview', published='2024-01-01')
    edge(graph, 'features_person', [(old,'resource'), (person,'person')])
    graph.activity(old['id'], Activity(kind='reaction', reaction='like'))
    wrong = d.propose_link(target['id'], LinkProposal(target_id=person['id'], relation='features_person', quote='This recording illustrates the Crab Canon through a musical reversal.'))
    graph.edge_status(wrong['id'], 'confirmed')
    assert Recommender(graph.store).generate() == []
    right = d.propose_link(target['id'], LinkProposal(target_id=person['id'], relation='features_person', quote='This interview features Jane Example as its guest.'))
    graph.edge_status(right['id'], 'confirmed')
    result = Recommender(graph.store).generate()
    assert len(result) == 1 and result[0]['candidate_id'] == target['id']
    assert 'publication date' in result[0]['reason']


def test_failures_manual_url_and_unsupported_claims_are_not_discovery(graph):
    fetch = FetchFixture(fail=True)
    d, focus, report = discovery(graph, fetch)
    assert not report['candidates'] and not report['search_performed'] and report['issues']
    assert any(a['kind']=='discovery-report' for a in graph.store.list('artifacts'))
    with pytest.raises(ValueError, match='approval'):
        d.discover(DiscoveryRequest(focus_id=focus['id']))
    manual = node(graph, 'User supplied URL', url=URL)
    assert link_evidence(graph.store, manual)['status'] == 'manual_unverified'
    model = graph.node(Node(title='Model URL guess', url=URL, provenance=[{'kind':'model','description':'Model claimed search'}]))
    assert link_evidence(graph.store, model)['status'] == 'unverified_claim'
    d2, _, report2 = discovery(graph, manual=True)
    assert not report2['search_performed'] and report2['origin'] == 'manually_supplied_url'


def test_missing_or_changed_snapshot_disables_discovered_url(graph, tmp_path):
    d, focus, report = discovery(graph)
    resource = graph.store.get('nodes', report['candidates'][0])
    exported = export_graph(graph.store)
    portable = Store(tmp_path/'portable'); import_graph(portable, exported)
    assert link_evidence(portable, portable.get('nodes', resource['id']))['status'] == 'unverified_discovery'
    snap = verified_snapshot(graph.store, resource)
    raw = graph.store.get('artifacts', snap['raw_artifact'])
    (graph.store.root/raw['path']).write_bytes(b'altered')
    assert verified_snapshot(graph.store, resource) is None


def test_metadata_uncertainty_and_search_links():
    page = Page(URL, HTML.replace('</head>', '<meta name="date" content="2025-01-01"></head>'), 'text/html')
    assert extract(page)['published'] is None
    with pytest.raises(ValueError): extract(Page(URL, '<title>Just a moment</title><p>Checking your browser for access permission.</p>', 'text/html'))
    parser = SearchLinks(); parser.feed('<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fpublic.example%2Fa">a</a><a href="https://not-a-result.example">not a result</a>')
    assert parser.urls == ['https://public.example/a']


@pytest.mark.parametrize('ip', ['127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', '192.168.1.1', '224.0.0.1', '2002:7f00:1::'])
def test_private_and_nonpublic_network_blocked(monkeypatch, ip):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(2,1,6,'',(ip,443))])
    with pytest.raises(ValueError, match='destinations'):
        public_target('https://public.example/path')


def test_dns_pin_and_redirect_to_private_blocked(monkeypatch):
    import par.web_retrieval as web
    def dns(host, *args, **kwargs):
        return [(2,1,6,'',('93.184.215.14' if host == 'public.example' else '127.0.0.1',443))]
    monkeypatch.setattr(socket, 'getaddrinfo', dns)
    targets = []
    monkeypatch.setattr(socket, 'create_connection', lambda address, *args: targets.append(address))
    class Conn:
        sock = None
        def __init__(self, host, port, **kw): self.host=host
        def request(self, *args, **kw): self._create_connection((self.host,443), 1)
        def getresponse(self): return self
        status = 302
        def getheader(self, key, default=None): return 'http://internal.example/private' if key == 'Location' else default
        def close(self): pass
    monkeypatch.setattr(web.http.client, 'HTTPSConnection', Conn)
    with pytest.raises(ValueError, match='destinations'):
        PublicFetcher().fetch('https://public.example/')
    assert targets == [('93.184.215.14',443)]  # actual socket target is pinned, not re-resolved hostname


def test_mixed_dns_and_credentials_rejected(monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(2,1,6,'',(ip,443)) for ip in ['93.184.215.14','127.0.0.1']])
    with pytest.raises(ValueError): public_target('https://public.example/')
    for url in ['file:///etc/passwd','http://user:password@public.example','https://public.example:9222/', 'https://public.example/?access_token=secret']:
        with pytest.raises(ValueError): public_target(url)


def test_overlap_additional_review_correction_stages_and_feedback(graph, monkeypatch):
    service = SemanticService(graph.store)
    service.config(LocalModelConfig(backend='ollama',model='synthetic'))
    texts = ['Composition is associative. These functions can be composed in sequence.',
             'Composition is associative. Functors preserve identity and composition.']
    resources = [service.import_text(TextMaterial(title='Synthetic source '+str(i),text=t)) for i,t in enumerate(texts)]
    units = [next(n['id'] for n in graph.store.list('nodes') if n['parent_id']==r['id']) for r in resources]
    async def synthetic(self, messages, schema):
        findings = [{'label':'Composition','description':'Composition follows associativity in both passages.','confidence':.9,
                     'evidence':[{'source_id':u,'quote':'Composition is associative.','relation':'covers'} for u in units]},
                    {'label':'Functors','description':'Preservation of identities and composition in the second passage.','confidence':.9,
                     'evidence':[{'source_id':units[1],'quote':'Functors preserve identity and composition.','relation':'covers'}]}]
        return json.dumps({'concepts':findings,'limitations':'Synthetic protocol output; bounded passages only.'}), {'model':'SYNTHETIC TEST DOUBLE'}
    monkeypatch.setattr(Ollama,'generate',synthetic)
    run = service.submit(AnalysisRequest(source_ids=units,authorize_local_inference=True))
    asyncio.run(service.runtime.execute(run['run_id']))
    recs = Recommender(graph.store)
    assert recs.compare(*units)['shared'] == []
    stages = graph.store.get('runs',run['run_id'])['acceptance']
    assert stages['browser_reachable']['status']=='not_applicable'
    assert stages['response_captured']['status']=='observed' and stages['semantic_validated']['status']=='observed'
    assert 'proposals_reviewed' not in stages and 'recommendation_generated' not in stages
    service.review(run['run_id'],'confirmed')
    comparison = recs.compare(*units)
    assert [c['title'] for c in comparison['shared']] == ['Composition']
    assert [c['title'] for c in comparison['additional_in_candidate']] == ['Functors']
    assert comparison['candidate_represented_overlap'] == .5
    graph.activity(units[0],Activity(kind='reading',start=0,end=100))
    recommendation = recs.generate()[0]
    assert recommendation['encountered']==['Composition'] and recommendation['may_add']==['Functors']
    stages=graph.store.get('runs',run['run_id'])['acceptance']
    assert 'recommendation_generated' in stages and 'recommendation_rendered' not in stages
    recs.rendered(recommendation['id'])
    assert graph.store.get('runs',run['run_id'])['acceptance']['recommendation_rendered']['status']=='observed'
    recs.feedback(recommendation['id'],Feedback(action='ignored'))
    recs.feedback(recommendation['id'],Feedback(action='deferred'))
    reopened=Store(graph.store.root)
    assert Recommender(reopened).generate()==[]
    assert reopened.get('recommendations',recommendation['id'])['ignored']==1
    assert not reopened.list('preferences')  # ignore/defer are not broad taste assertions
    # A user correction supersedes old coverage and removes its additional concept.
    extra=next(e for e in graph.edges() if len(e['members'])==2)
    data=payload(extra);data.update(supersedes=extra['id'],status='rejected',provenance=extra['provenance']+[user_evidence('User correction')])
    graph.edge(Edge.model_validate(data))
    assert recs.compare(*units)['additional_in_candidate']==[]
    service.analyses()
    reviewed=graph.store.get('runs',run['run_id'])['acceptance']['proposals_reviewed']['detail']['edges']
    assert 'rejected' in reviewed.values() and extra['id'] not in reviewed


def test_api_network_consent_comparison_reports_and_csrf(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from par.api import create_app
    from par.config import Config
    import re
    fetch=FetchFixture()
    monkeypatch.setattr(PublicFetcher,'fetch',lambda self,url:fetch.fetch(url))
    app=create_app(Config(tmp_path/'api'))
    graph=Knowledge(app.state.runtime.store)
    a=node(graph,'Topic',node_type='concept')
    left=node(graph,'Left'); right=node(graph,'Right')
    with TestClient(app) as client:
        html=client.get('/life').text
        assert 'discovery-form' in html and 'comparison-form' in html
        csrf=re.search(r'const LIFE_CSRF="([^"]+)"',html).group(1)
        headers={'X-PAR-CSRF':csrf}
        body={'focus_id':a['id'],'authorize_network':True}
        assert client.post('/api/life/discovery',json=body).status_code==403
        assert not fetch.calls
        assert client.post('/api/life/discovery',headers=headers,json={**body,'authorize_network':False}).status_code==400
        assert not fetch.calls
        response=client.post('/api/life/discovery',headers=headers,json=body)
        assert response.status_code==200 and response.json()['search_performed']
        candidate=response.json()['candidates'][0]
        assert client.get('/api/life/discovery-reports').json()[0]['candidates']==[candidate]
        assert client.get('/api/life/discovery/'+candidate+'/evidence').json()['url']==URL
        compared=client.get('/api/life/comparison',params={'source':left['id'],'candidate':right['id']})
        assert compared.status_code==200 and compared.json()['candidate_represented_overlap'] is None
        state=client.get('/api/life/state').json()
        assert state['link_evidence'][candidate]['status']=='retrieved'


def test_synthetic_dom_renders_recommendation_and_acknowledges_only_after_insertion(tmp_path, monkeypatch):
    import shutil, subprocess, re
    from fastapi.testclient import TestClient
    from par.api import create_app
    from par.config import Config
    if not shutil.which('node') or not Path('.cache/life-dom/node_modules/jsdom').exists():
        pytest.skip('Optional synthetic DOM test: npm install --prefix .cache/life-dom --no-package-lock jsdom@26')
    app=create_app(Config(tmp_path/'dom'))
    graph=Knowledge(app.state.runtime.store)
    service=SemanticService(graph.store)
    service.config(LocalModelConfig(backend='ollama',model='synthetic'))
    resources=[service.import_text(TextMaterial(title=title,text=text,url='https://example.org/manual' if i else None)) for i,(title,text) in enumerate([
        ('Synthetic book','Composition is associative. It combines functions in sequence.'),
        ('Synthetic lecture','Composition is associative. Functors preserve identity and composition.')])]
    units=[next(n['id'] for n in graph.store.list('nodes') if n['parent_id']==r['id']) for r in resources]
    async def synthetic(self,messages,schema):
        return json.dumps({'concepts':[
            {'label':'Composition','description':'Composition is associative in both supplied texts.','confidence':.9,'evidence':[{'source_id':u,'quote':'Composition is associative.'} for u in units]},
            {'label':'Functors','description':'The second text describes functor preservation.','confidence':.9,'evidence':[{'source_id':units[1],'quote':'Functors preserve identity and composition.'}]}],
            'limitations':'Synthetic fixture, not real provider reasoning.'}),{'model':'SYNTHETIC'}
    monkeypatch.setattr(Ollama,'generate',synthetic)
    job=service.submit(AnalysisRequest(source_ids=units,authorize_local_inference=True))
    asyncio.run(service.runtime.execute(job['run_id']))
    service.review(job['run_id'],'confirmed')
    graph.activity(units[0],Activity(kind='reading',start=0,end=100))
    with TestClient(app) as client:
        html=client.get('/life').text
        headers={'X-PAR-CSRF':re.search(r'const LIFE_CSRF="([^"]+)"',html).group(1)}
        fixture={'html':html,'state':client.get('/api/life/state').json(),'graph':client.get('/api/life/graph').json(),
                 'comparison':Recommender(graph.store).compare(*units)}
        result=subprocess.run(['node','tests/v03_dom.cjs'],input=json.dumps(fixture),text=True,capture_output=True,timeout=10)
        assert result.returncode==0,result.stderr
        rendered=json.loads(result.stdout)
        assert rendered['errors']==[] and len(rendered['acknowledgements'])==1
        assert 'recommendation_rendered' not in graph.store.get('runs',job['run_id'])['acceptance']
        for id in rendered['acknowledgements']:
            assert client.post('/api/life/recommendations/'+id+'/rendered',headers=headers).status_code==200
        assert graph.store.get('runs',job['run_id'])['acceptance']['recommendation_rendered']['status']=='observed'
        assert client.post('/api/life/recommendations/'+rendered['acknowledgements'][0]+'/feedback',headers=headers,json={'action':'accepted'}).status_code==200
    with TestClient(create_app(Config(tmp_path/'dom'))) as restarted:
        after=restarted.get('/api/life/state').json()
        assert after['recommendations']==[]
        assert after['analyses'][0]['acceptance']['recommendation_rendered']['status']=='observed'
        assert after['preferences'][0]['scope']==resources[1]['id']


def test_guest_proposed_from_two_sources_then_newer_retrieved_interview(graph, monkeypatch):
    d, _, report=discovery(graph)
    candidate=graph.store.get('nodes',report['candidates'][0])
    service=SemanticService(graph.store)
    service.config(LocalModelConfig(backend='ollama',model='synthetic'))
    quote='This interview features Jane Example as its guest.'
    old=service.import_text(TextMaterial(title='Old supplied transcript',text=quote+' We discuss learning and language.'))
    values=payload(old); values['published']='2024-01-01'
    graph.correct_node(old['id'],Node.model_validate(values))
    units=[next(n['id'] for n in graph.store.list('nodes') if n['parent_id']==id) for id in [old['id'],candidate['id']]]
    async def synthetic(self,messages,schema):
        return json.dumps({'concepts':[{'kind':'person','label':'Jane Example','description':'Explicitly named guest in both selected passages.','confidence':.9,
                                        'evidence':[{'source_id':u,'quote':quote,'relation':'features_person'} for u in units]}],
                           'limitations':'Synthetic fixture: no claim of live identity resolution.'}),{'model':'SYNTHETIC'}
    monkeypatch.setattr(Ollama,'generate',synthetic)
    job=service.submit(AnalysisRequest(source_ids=units,authorize_local_inference=True))
    asyncio.run(service.runtime.execute(job['run_id']))
    assert graph.store.get('runs',job['run_id'])['status']=='completed'
    graph.activity(old['id'],Activity(kind='reaction',reaction='like'))
    assert not Recommender(graph.store).generate()
    service.review(job['run_id'],'confirmed')
    result=Recommender(graph.store).generate()
    assert len(result)==1 and result[0]['candidate_id']==candidate['id']
    assert result[0]['link_verification']['status']=='retrieved'
    assert result[0]['semantic_run_ids']==[job['run_id']]


def test_invalid_quote_stops_at_failed_validation_stage(graph,monkeypatch):
    service=SemanticService(graph.store);service.config(LocalModelConfig(backend='ollama',model='synthetic'))
    resource=service.import_text(TextMaterial(title='Source',text='This is a sufficiently long real input for a synthetic validation test.'))
    unit=next(n['id'] for n in graph.store.list('nodes') if n['parent_id']==resource['id'])
    async def synthetic(self,messages,schema):
        return json.dumps({'concepts':[{'label':'Invented','description':'A made-up interpretation of the supplied material.','confidence':.9,'evidence':[{'source_id':unit,'quote':'This quotation is not present.'}]}], 'limitations':'Synthetic invalid quotation fixture.'}),{'model':'SYNTHETIC'}
    monkeypatch.setattr(Ollama,'generate',synthetic)
    job=service.submit(AnalysisRequest(source_ids=[unit],authorize_local_inference=True))
    asyncio.run(service.runtime.execute(job['run_id']))
    run=graph.store.get('runs',job['run_id'])
    assert run['status']=='failed' and run['acceptance']['response_captured']['status']=='observed'
    assert run['acceptance']['semantic_validated']['status']=='failed'
    assert 'proposals_reviewed' not in run['acceptance'] and 'recommendation_generated' not in run['acceptance']
    assert not graph.edges()
