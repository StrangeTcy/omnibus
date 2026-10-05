"""Synthetic model fixtures exercise REAL collection orchestration, not live account quality."""
import asyncio
import hashlib
import json
import zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from par.api import create_app
from par.config import Config
from par.db import Store
from par.collections import Collections, passages, intent
from par.local_inference import LocalModelConfig
from par.browser_inference import BrowserChat
from par.library import parse_file, MAX_TEXT
from par.workers.base import WorkerFailure

TEXT = 'Composition is associative. Functions combine in sequence, and grouping does not change the result.\n\n'

def epub(path, text):
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('META-INF/container.xml','<container><rootfiles><rootfile full-path="book.opf"/></rootfiles></container>')
        z.writestr('book.opf','<package xmlns="http://www.idpf.org/2007/opf"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Fixture EPUB</dc:title></metadata><manifest><item id="one" href="one.xhtml"/><item id="two" href="two.xhtml"/></manifest><spine><itemref idref="one"/><itemref idref="two"/></spine></package>')
        z.writestr('one.xhtml','<html><title>First chapter</title><body><p>'+text+'</p></body></html>')
        z.writestr('two.xhtml','<html><title>Last chapter</title><body><p>'+text+'</p></body></html>')

@pytest.fixture
def library(tmp_path):
    books=tmp_path/'Books with spaces';books.mkdir()
    (books/'one.md').write_text('# First book\n'+TEXT*140+'\n## Last section\n'+TEXT*3)
    (books/'two.md').write_text('# Second book\n'+TEXT*120)
    epub(books/'third.epub',TEXT*110)
    epub(books/'fourth.epub',TEXT*65)
    return books


def configure(service):
    service.semantic.config(LocalModelConfig(backend='browser',browser_provider='chatgpt',dedicated_browser_profile=True))


def response(messages):
    value=json.loads(messages[1]['content']);sources=value['sources'];known=value.get('canonical_context',[])
    evidence=[{'source_id':s['id'],'quote':'Composition is associative.' if 'Composition is associative.' in s['text'] else s['text'].strip()[:80], 'relation':'covers'} for s in sources]
    concept={'label':'Composition','description':'Function composition is associative: grouping does not change the result.','confidence':.95,'evidence':evidence}
    old=next((c for c in known if c['label']=='Composition'),None)
    if old:
        concept.update(existing_concept_id=old['id'],reuse_quote=old['quotes'][0],reuse_reason='Both supplied passages explicitly describe the same associativity of function composition, not merely a matching label.')
    return json.dumps({'concepts':[concept], 'limitations':'Synthetic provider fixture; proves orchestration, not real model interpretation.'}), {'model':'SYNTHETIC TEST DOUBLE','transport':'synthetic'}


def install_provider(monkeypatch, calls):
    async def generate(self,messages,schema):
        data=json.loads(messages[1]['content']);calls.append(data)
        self.before_send({'provider':'chatgpt','state':'submission_attempted'})
        return response(messages)
    monkeypatch.setattr(BrowserChat,'generate',generate)


def test_one_command_entire_markdown_epub_library_reconciliation_and_idempotence(tmp_path,library,monkeypatch):
    service=Collections(Store(tmp_path/'data'));configure(service);calls=[];install_provider(monkeypatch,calls)
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in library.iterdir()}
    command=f'Read all the books in "{library}". Build an idea graph, merge duplicate concepts where justified, and preserve citations.'
    job=service.prepare(command)
    assert not calls and job['status']=='awaiting_approval'
    assert len(job['batches'])>2 and len(job['manifest'])==4
    assert job['issues']==[]
    for item in job['manifest']:
        original=parse_file(Path(item['path']),Path(item['path']).read_bytes(),text_limit=MAX_TEXT,full_text=True)
        original_chars=sum(len(s['analysis_text']) for s in original['units'])
        assert item['characters']==original_chars
        combined=0
        for id in item['passage_ids']:
            source=service.semantic.source(id)
            assert 0<len(source['text'])<=2000
            n=service.store.get('nodes',id);p=n['metadata']['collection_passage']
            section=next(s for s in original['units'] if s['locator']==p['section_locator'])
            assert source['text']==section['analysis_text'][p['start']:p['end']]
            combined+=len(source['text'])
        assert combined+item['whitespace_characters']==original_chars
    service.approve(job['id'],'chatgpt')
    asyncio.run(service.execute(job['id']))
    result=service.result(job['id'])
    assert result['job']['status']=='completed', result['job']['error']
    sent=[s['id'] for c in calls for s in c['sources']]
    assert len(sent)==len(set(sent))==result['summary']['passages']
    assert result['summary']['completed_passages']==result['summary']['passages']
    assert len(result['summary']['themes'])==1 and result['summary']['reused_identities']>0
    assert len(result['summary']['cross_book_connections'])==1
    assert len(result['summary']['themes'][0]['books'])==4
    assert all(e['status']=='proposed' for e in result['graph']['edges'])
    assert all(p['node_id'] in sent for e in result['graph']['edges'] for p in e['provenance'])
    counts=(len(service.store.list('nodes')),len(service.store.list('edges')),len(calls))
    again=service.prepare(command);assert again['id']==job['id']
    asyncio.run(service.execute(job['id']))
    assert counts==(len(service.store.list('nodes')),len(service.store.list('edges')),len(calls))
    assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in library.iterdir()}
    # Provisional graph is useful before any user reviews; later corrections work.
    first=result['graph']['edges'][0];service.graph.edge_status(first['id'],'confirmed')
    assert any(e['status']=='confirmed' for e in service.result(job['id'])['graph']['edges'])


def test_passages_never_drop_tail_or_whitespace():
    for text in ['a'*4021, TEXT*30, '\n\n'+TEXT*22+'last', 'short']:
        chunks=list(passages(text));assert ''.join(c for _,_,c in chunks)==text
        assert chunks[0][0]==0 and chunks[-1][1]==len(text)
        assert all(0<len(c)<=2000 and end-start==len(c) for start,end,c in chunks)


def test_unsupported_omissions_not_claimed_understood(tmp_path,library,monkeypatch):
    (library/'unsupported.mobi').write_bytes(b'unsupported')
    service=Collections(Store(tmp_path/'data'));configure(service);install_provider(monkeypatch,[])
    job=service.prepare(f'Read all books in "{library}" and build a graph')
    service.approve(job['id'],'chatgpt');asyncio.run(service.execute(job['id']))
    result=service.result(job['id'])
    assert result['job']['status']=='partial' and result['job']['issues']
    assert result['summary']['completed_passages']==result['summary']['passages']


@pytest.mark.parametrize('kind',['unavailable','malformed','quote','omitted','false_identity'])
def test_provider_failure_states_are_explicit(tmp_path,library,monkeypatch,kind):
    import par.collections as module
    monkeypatch.setattr(module,'RETRY_DELAYS',())
    calls=[]
    async def fail(self,messages,schema):
        calls.append(1)
        if kind=='unavailable': raise WorkerFailure('browser_unavailable','Synthetic browser is unavailable')
        self.before_send({'provider':'chatgpt','state':'submission_attempted'})
        raw,meta=response(messages)
        if kind=='malformed': return 'not valid JSON',meta
        data=json.loads(raw)
        if kind=='quote': data['concepts'][0]['evidence'][0]['quote']='This quotation was invented.'
        if kind=='omitted': data['concepts'][0]['evidence']=data['concepts'][0]['evidence'][:1]
        if kind=='false_identity': data['concepts'][0].update(existing_concept_id='invented-id',reuse_quote='not supplied',reuse_reason='Title similarity alone should not be sufficient.')
        return json.dumps(data),meta
    monkeypatch.setattr(BrowserChat,'generate',fail)
    service=Collections(Store(tmp_path/'data'));configure(service)
    job=service.prepare(f'Read all books in "{library}"');service.approve(job['id'],'chatgpt')
    asyncio.run(service.execute(job['id']));result=service.result(job['id'])
    assert result['job']['status']=='needs_attention' and result['job']['error']
    assert result['summary']['completed_batches']==0 and not result['graph']['edges']
    assert len(calls)==1


def test_safe_recoverable_failure_automatically_continues(tmp_path,library,monkeypatch):
    import par.collections as module
    monkeypatch.setattr(module,'RETRY_DELAYS',(0,))
    count=[]
    async def generate(self,messages,schema):
        count.append(1)
        if len(count)==1: raise WorkerFailure('rate_limit','Synthetic pre-submission quota limit')
        self.before_send({'provider':'chatgpt','state':'submission_attempted'})
        return response(messages)
    monkeypatch.setattr(BrowserChat,'generate',generate)
    service=Collections(Store(tmp_path/'data'));configure(service)
    job=service.prepare(f'Read all books in "{library}"');service.approve(job['id'],'chatgpt')
    asyncio.run(service.execute(job['id']))
    assert service.result(job['id'])['job']['status']=='completed'
    assert len(count)==len(job['batches'])+1


def test_restart_retains_completed_batches_and_never_resubmits_ambiguous(tmp_path,library,monkeypatch):
    root=tmp_path/'data';calls=[]
    async def interrupted(self,messages,schema):
        calls.append(1);self.before_send({'provider':'chatgpt','state':'submission_attempted'})
        if len(calls)==2: await asyncio.Event().wait()
        return response(messages)
    monkeypatch.setattr(BrowserChat,'generate',interrupted)
    app=create_app(Config(root));configure(app.state.collections)
    with TestClient(app) as client:
        csrf=client.get('/api/session').json()['csrf'];h={'X-PAR-CSRF':csrf}
        assert client.post('/api/assistant/commands',json={'text':f'Read all books in "{library}"'}).status_code==403
        job=client.post('/api/assistant/commands',headers=h,json={'text':f'Read all books in "{library}"'}).json()
        assert not calls
        assert client.post('/api/assistant/operations/'+job['id']+'/approve',headers=h,json={'provider':'chatgpt'}).status_code==200
        async def entered():
            for _ in range(100):
                if len(calls)>=2:return
                await asyncio.sleep(.01)
            raise AssertionError('Second batch never started')
        client.portal.call(entered)
    assert len(calls)==2
    reopened=create_app(Config(root))
    with TestClient(reopened) as client:
        async def settle():
            tasks=list(reopened.state.collections.jobs.values())
            if tasks: await asyncio.gather(*tasks)
        client.portal.call(settle)
        result=client.get('/api/assistant/operations/'+job['id']).json()
        assert result['job']['status']=='needs_attention' and 'Ambiguous' in result['job']['error']
        assert result['summary']['completed_batches']==1 and len(calls)==2
        h={'X-PAR-CSRF':client.get('/api/session').json()['csrf']}
        assert client.post('/api/assistant/operations/'+job['id']+'/resume',headers=h,json={}).status_code==400
        assert len(calls)==2


def test_shutdown_before_submission_safely_resumes_on_restart(tmp_path,library,monkeypatch):
    import par.collections as module
    monkeypatch.setattr(module,'RETRY_DELAYS',(0,))
    entered=[]
    async def before_send(self,messages,schema):
        entered.append(True);await asyncio.Event().wait()
    monkeypatch.setattr(BrowserChat,'generate',before_send)
    root=tmp_path/'data';app=create_app(Config(root));configure(app.state.collections)
    job=app.state.collections.prepare(f'Read all books in "{library}"');app.state.collections.approve(job['id'],'chatgpt')
    with TestClient(app) as client:
        async def waiting():
            for _ in range(100):
                if entered:return
                await asyncio.sleep(.01)
            raise AssertionError('No invocation')
        client.portal.call(waiting)
    calls=[];install_provider(monkeypatch,calls)
    reopened=create_app(Config(root))
    with TestClient(reopened) as client:
        async def finished():
            await asyncio.gather(*reopened.state.collections.jobs.values())
        client.portal.call(finished)
        result=client.get('/api/assistant/operations/'+job['id']).json()
        assert result['job']['status']=='completed'
        assert len(calls)==result['summary']['total_batches']


def test_pdf_collection_extracts_beyond_scanner_page_100(tmp_path):
    PdfWriter=pytest.importorskip('pypdf').PdfWriter
    from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject
    books=tmp_path/'pdf';books.mkdir();path=books/'long.pdf'
    writer=PdfWriter()
    for _ in range(102):
        page=writer.add_blank_page(width=300,height=300)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
        stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 10 10 Td (Composition is associative. Functions compose.) Tj ET')
        page[NameObject('/Contents')]=writer._add_object(stream)
    with path.open('wb') as file:writer.write(file)
    service=Collections(Store(tmp_path/'data'));job=service.prepare(f'Read all books in "{books}"')
    assert job['issues']==[]
    assert len(job['manifest'][0]['passage_ids'])==102
    assert any(service.store.get('nodes',id)['metadata']['collection_passage']['section_locator']=='page:102' for id in job['manifest'][0]['passage_ids'])


def test_intent_scope_and_main_page(tmp_path,library):
    service=Collections(Store(tmp_path/'data'));configure(service)
    with pytest.raises(ValueError):service.prepare('Buy something online')
    job=service.prepare(f'Read all the books in "{library}". Build an idea graph.')
    with pytest.raises(ValueError,match='Provider changed'):service.approve(job['id'],'claude')
    assert not service.store.list('runs')
    with TestClient(create_app(Config(tmp_path/'ui'))) as client:
        page=client.get('/').text
        assert page.index('id="collection-command"')<page.index('id="advanced-controls"')
        assert '<details id="advanced-controls">' in page
        assert 'name="authorize_provider"' not in page.split('<details id="advanced-controls">')[0]
        assert client.get('/runtime').status_code==200


def test_incremental_new_book_reuses_old_passages_without_duplicate_edges(tmp_path,library,monkeypatch):
    service=Collections(Store(tmp_path/'data'));configure(service);calls=[];install_provider(monkeypatch,calls)
    command=f'Read all books in "{library}"'
    first=service.prepare(command);service.approve(first['id'],'chatgpt');asyncio.run(service.execute(first['id']))
    old_sources={s['id'] for c in calls for s in c['sources']};before=len(service.store.list('edges'));calls.clear()
    (library/'added.md').write_text('# Added book\n'+TEXT*80)
    second=service.prepare(command)
    assert second['id']!=first['id']
    assert sum(len(b['source_ids']) for b in second['batches'] if b.get('reused'))==len(old_sources)
    service.approve(second['id'],'chatgpt');asyncio.run(service.execute(second['id']))
    assert not old_sources & {s['id'] for c in calls for s in c['sources']}
    result=service.result(second['id'])
    assert result['job']['status']=='completed' and len(result['summary']['themes'])==1
    assert len(result['summary']['themes'][0]['books'])==5
    assert len(service.store.list('edges'))==before+len(calls)


def test_scope_is_frozen_after_approval(tmp_path,library,monkeypatch):
    service=Collections(Store(tmp_path/'data'));configure(service);calls=[];install_provider(monkeypatch,calls)
    job=service.prepare(f'Read all books in "{library}"');service.approve(job['id'],'chatgpt')
    service.semantic.config(LocalModelConfig(backend='browser',browser_provider='claude',dedicated_browser_profile=True))
    (library/'new-after-approval.md').write_text('# Secret new text\nDo not disclose this unapproved addition.')
    (library/'one.md').write_text('# Changed file\nThis new version was never approved.')
    asyncio.run(service.execute(job['id']))
    assert service.result(job['id'])['job']['status']=='completed'
    assert all('unapproved addition' not in s['text'] and 'never approved' not in s['text'] for c in calls for s in c['sources'])
    assert service.store.get('collection_jobs',job['id'])['approval']['provider']=='chatgpt'


def test_cached_response_recovers_locally_without_second_browser_send(tmp_path,library,monkeypatch):
    calls=[]
    async def capture_then_stop(self,messages,schema):
        calls.append(True);self.before_send({'provider':'chatgpt','state':'submission_attempted'})
        raw,meta=response(messages)
        assert self.capture_response
        self.capture_response(raw,meta)
        raise WorkerFailure('interrupted','Synthetic disconnect after durable response capture')
    monkeypatch.setattr(BrowserChat,'generate',capture_then_stop)
    service=Collections(Store(tmp_path/'data'));configure(service)
    job=service.prepare(f'Read all books in "{library}"');service.approve(job['id'],'chatgpt');asyncio.run(service.execute(job['id']))
    result=service.result(job['id'])
    assert result['job']['status']=='completed',result['job']['error']
    assert len(calls)==len(job['batches'])  # local retries consumed saved responses, not new model calls
    assert len(result['summary']['themes'])==1


def test_command_approval_results_evidence_dom(tmp_path,library,monkeypatch):
    import copy
    import shutil
    import subprocess
    if not shutil.which('node') or not Path('.cache/life-dom/node_modules/jsdom').is_dir():
        pytest.skip('Optional synthetic DOM runner needs local jsdom in .cache/life-dom')
    root=tmp_path/'data';service=Collections(Store(root));configure(service);install_provider(monkeypatch,[])
    job=service.prepare(f'Read all books in "{library}"');plan=copy.deepcopy(service.result(job['id']))
    service.approve(job['id'],'chatgpt');asyncio.run(service.execute(job['id']))
    result=service.result(job['id']);service.graph.edge_status(result['graph']['edges'][0]['id'],'confirmed')
    result=service.result(job['id'])
    result['summary']['themes'][0]['description']='<img data-injected src=x onerror=alert(1)>'
    with TestClient(create_app(Config(root))) as client:html=client.get('/').text
    proc=subprocess.run(['node','tests/collection_dom.cjs'],input=json.dumps({'html':html,'config':service.semantic.config().model_dump(),'plan':plan,'result':result}),text=True,capture_output=True,timeout=20)
    assert proc.returncode==0,proc.stderr+proc.stdout
    assert json.loads(proc.stdout)['posts']==2


def test_short_sources_explicitly_uncovered_still_accounted(tmp_path,monkeypatch):
    books=tmp_path/'books';books.mkdir();(books/'tiny.md').write_text('# A\nx')
    async def uncovered(self,messages,schema):
        sources=json.loads(messages[1]['content'])['sources']
        return json.dumps({'concepts':[], 'limitations':'This tiny source does not support thematic inference.', 'uncovered_sources':[{'source_id':s['id'],'reason':'Too little text to support a meaningful thematic assertion.'} for s in sources]}),{'model':'synthetic'}
    monkeypatch.setattr(BrowserChat,'generate',uncovered)
    service=Collections(Store(tmp_path/'data'));configure(service);job=service.prepare(f'Read books in "{books}"')
    service.approve(job['id'],'chatgpt');asyncio.run(service.execute(job['id']))
    result=service.result(job['id'])
    assert result['job']['status']=='completed' and result['summary']['completed_passages']==1
    assert len(result['summary']['uncovered_sources'])==1 and result['summary']['themes']==[]


def test_concurrent_same_command_has_one_operation(tmp_path,library):
    from concurrent.futures import ThreadPoolExecutor
    root=tmp_path/'data';Store(root)
    def plan():return Collections(Store(root)).prepare(f'Read all books in "{library}"')['id']
    with ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(lambda _:plan(),range(2)))
    assert ids[0]==ids[1] and len(Store(root).list('collection_jobs'))==1


def test_typed_nary_codiscussion_is_heuristic_and_provisional(tmp_path,monkeypatch):
    books=tmp_path/'books';books.mkdir();(books/'one.md').write_text('# Functions\n'+TEXT*4)
    async def ideas(self,messages,schema):
        raw,metadata=response(messages);value=json.loads(raw)
        second=dict(value['concepts'][0]);second.update(label='Functions',description='Functions combine in sequence in this supplied example.')
        value['concepts'].append(second)
        return json.dumps(value),metadata
    monkeypatch.setattr(BrowserChat,'generate',ideas)
    service=Collections(Store(tmp_path/'data'));configure(service);job=service.prepare(f'Read books in "{books}"')
    service.approve(job['id'],'chatgpt');asyncio.run(service.execute(job['id']))
    result=service.result(job['id']);assert result['job']['status']=='completed'
    related=next(e for e in result['graph']['edges'] if e['type']=='related_to')
    assert len(related['members'])==3 and related['status']=='proposed'
    assert related['provenance'][0]['kind']=='heuristic'
    assert 'not equivalence or causation' in related['explanation']


def test_extraction_limit_is_reported_not_silently_excerpted(tmp_path):
    books=tmp_path/'books';books.mkdir()
    (books/'too-many-sections.md').write_text('\n'.join(f'# Section {i}\n'+TEXT for i in range(501)))
    service=Collections(Store(tmp_path/'data'));job=service.prepare(f'Read books in "{books}"')
    assert job['status']=='partial' and not job['batches']
    assert any('500 Markdown sections' in str(issue) for issue in job['issues'])
    assert not service.store.list('runs')


def test_full_markdown_preserves_text_before_first_heading(tmp_path):
    text='Front matter without a heading.\n\n# First chapter\n'+TEXT+'\n## Last\nTail.'
    parsed=parse_file(tmp_path/'book.md',text.encode(),text_limit=MAX_TEXT,full_text=True)
    assert ''.join(s['analysis_text'] for s in parsed['units'])==text
    assert parsed['units'][0]['locator'].startswith('char:0:')


def test_partial_extraction_can_be_replanned_after_local_failure_is_fixed(tmp_path,library,monkeypatch):
    service=Collections(Store(tmp_path/'data'));configure(service);calls=[];install_provider(monkeypatch,calls)
    original=service.read_resource;failed=[]
    def transient(resource,root):
        if not failed:
            failed.append(True);raise OSError('Synthetic transient source read failure')
        return original(resource,root)
    monkeypatch.setattr(service,'read_resource',transient)
    command=f'Read all books in "{library}"'
    first=service.prepare(command);service.approve(first['id'],'chatgpt');asyncio.run(service.execute(first['id']))
    assert service.result(first['id'])['job']['status']=='partial'
    old={s['id'] for c in calls for s in c['sources']};calls.clear()
    second=service.prepare(command);assert second['id']!=first['id']
    service.approve(second['id'],'chatgpt');asyncio.run(service.execute(second['id']))
    assert service.result(second['id'])['job']['status']=='completed'
    assert not old & {s['id'] for c in calls for s in c['sources']}


def test_relative_path_is_not_misinterpreted_as_root_directory():
    with pytest.raises(ValueError,match='absolute directory'):
        intent('Read all books in ./Books')
