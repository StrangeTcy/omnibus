import copy
import hashlib
import json
import sqlite3
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from par.api import create_app
from par.config import Config
from par.db import Store
from par.knowledge import Knowledge, user_evidence
from par.knowledge_models import Node, Edge, Activity, Feedback, Preference
from par.library import Library
from par.recommendations import Recommender
from par.graph_io import export_graph, import_graph
from par.enrichment import UnavailableEnricher, validate_proposal

AT = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)

@pytest.fixture
def graph(tmp_path):
    return Knowledge(Store(tmp_path/'data'))


def node(g, title, **kwargs):
    return g.node(Node(title=title, provenance=[user_evidence('Synthetic test fixture, not a claim about real books')], **kwargs))


def edge(g, kind, members):
    return g.edge(Edge(type=kind, members=[{'node_id': n['id'], 'role': role} for n, role in members],
                       explanation='Synthetic relation established by test fixture', provenance=[user_evidence('Explicit fixture assertion')]))


def epub(path):
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('mimetype', 'application/epub+zip')
        z.writestr('META-INF/container.xml', '<container><rootfiles><rootfile full-path="OEBPS/book.opf"/></rootfiles></container>')
        z.writestr('OEBPS/book.opf', '<package xmlns="http://www.idpf.org/2007/opf"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Fixture Book</dc:title><dc:creator>Fixture Author</dc:creator></metadata><manifest><item id="c1" href="c1.xhtml"/><item id="c2" href="c2.xhtml"/></manifest><spine><itemref idref="c1"/><itemref idref="c2"/></spine></package>')
        z.writestr('OEBPS/c1.xhtml', '<html><title>First section</title><p>Synthetic X and Y</p></html>')
        z.writestr('OEBPS/c2.xhtml', '<html><title>Second section</title><p>Synthetic Z</p></html>')


def test_a_scanner_repeat_duplicates_changed_malformed_and_unchanged_sources(graph, tmp_path):
    root = tmp_path/'books'; root.mkdir()
    epub(root/'book.epub')
    (root/'notes.md').write_text('# Notes\nSynthetic concept X\n## Later\nConcept Y')
    (root/'page.html').write_text('<title>Fixture HTML</title><p>Visible.</p><script>not evidence</script>')
    (root/'text.txt').write_text('Plain text fixture')
    (root/'broken.epub').write_bytes(b'not a ZIP archive')
    (root/'unsupported.mobi').write_bytes(b'not supported')
    (root/'copy.epub').write_bytes((root/'book.epub').read_bytes())
    before = {p.name: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in root.iterdir()}
    library = Library(graph.store)
    configured = library.configure(str(root))
    first = library.scan(configured['id'])
    assert len(first['discovered']) == 4 and len(first['duplicates']) == 1
    assert len(first['issues']) == 2
    book = next(n for n in graph.store.list('nodes') if n['title'] == 'Fixture Book')
    assert book['creators'] == ['Fixture Author'] and book['measure'] == 'chapters' and book['total'] == 2
    assert len(book['locations']) == 2
    units = [n for n in graph.store.list('nodes') if n['parent_id'] == book['id']]
    assert [n['locator'] for n in units] == ['OEBPS/c1.xhtml', 'OEBPS/c2.xhtml']
    assert all('not evidence' not in n['excerpt'] for n in graph.store.list('nodes'))
    count = len(graph.store.list('nodes'))
    second = library.scan(configured['id'])
    assert not second['discovered'] and len(graph.store.list('nodes')) == count
    after = {p.name: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in root.iterdir()}
    assert after == before
    (root/'notes.md').write_text('# Notes updated\nNew fixture content')
    changed = library.scan(configured['id'])
    assert len(changed['changed']) == 1 and len(changed['discovered']) == 1
    newer = graph.store.get('nodes', changed['discovered'][0])
    assert newer['metadata']['previous_version'] == changed['changed'][0]
    assert graph.store.get('nodes', changed['changed'][0])['title'] == 'Notes'
    (root/'book.epub').rename(root/'moved.epub')
    moved = library.scan(configured['id'])
    assert not moved['discovered'] and moved['duplicates'] and moved['missing']


def test_pdf_parser_when_installed(graph, tmp_path):
    pypdf = pytest.importorskip('pypdf', reason='Optional books extra not installed')
    root = tmp_path/'books'; root.mkdir()
    pdf = root/'fixture.pdf'
    writer = pypdf.PdfWriter()
    for _ in range(200): writer.add_blank_page(width=100, height=100)
    writer.add_metadata({'/Title': '200-page fixture', '/Author': 'Test author'})
    with pdf.open('wb') as f: writer.write(f)
    before = pdf.read_bytes()
    lib = Library(graph.store)
    report = lib.scan(lib.configure(str(root))['id'])
    assert not report['issues']
    book = graph.store.get('nodes', report['discovered'][0])
    assert book['total'] == 200 and book['measure'] == 'pages' and book['creators'] == ['Test author']
    assert len([n for n in graph.store.list('nodes') if n['parent_id'] == book['id']]) == 200
    assert pdf.read_bytes() == before


def test_b_progress_chart_correction_revisit_and_restart(graph):
    book = node(graph, 'Fixed-page fixture', total=200, measure='pages')
    graph.activity(book['id'], Activity(kind='position', end=90, at=AT, source='reader_import'))
    first = graph.activity(book['id'], Activity(kind='reading', start=90, end=100, at=AT))
    graph.activity(book['id'], Activity(kind='reading', start=100, end=110, at=AT))
    p = graph.progress(book['id'])
    assert p['newly_read'] == 20 and p['fraction'] == .55
    assert p['daily'] == [{'date': '2026-10-04', 'amount': 20}]
    graph.activity(book['id'], Activity(kind='revisit', start=90, end=110, at=AT))
    assert graph.progress(book['id'])['newly_read'] == 20
    graph.activity(book['id'], Activity(kind='correction', corrects=first['id'], start=95, end=100, at=AT))
    assert graph.progress(book['id'])['newly_read'] == 15
    assert graph.store.get('activity', first['id'])['start'] == 90  # unchanged historical evidence
    with pytest.raises(sqlite3.IntegrityError):
        with graph.store.connect() as db: db.execute('DELETE FROM activity')
    reopened = Knowledge(Store(graph.store.root))
    assert reopened.progress(book['id']) == graph.progress(book['id'])
    with pytest.raises(ValueError):
        graph.activity(book['id'], Activity(kind='reading', start=200, end=201))
    with pytest.raises(ValueError):
        graph.activity(book['id'], Activity(kind='reading', start=0, end=1.5))


def test_c_true_hyperedge_export_import_and_conflicts(graph, tmp_path):
    a = node(graph, 'Resource A')
    x = node(graph, 'X', node_type='concept', kind='idea')
    y = node(graph, 'Y', node_type='concept', kind='idea')
    relation = edge(graph, 'covers', [(a, 'source'), (x, 'concept'), (y, 'context')])
    assert len(relation['members']) == 3
    assert len({m['role'] for m in relation['members']}) == 3
    other = Store(tmp_path/'other')
    doc = export_graph(graph.store)
    counts = import_graph(other, doc)
    assert counts['edges'] == 1
    assert export_graph(other) == doc
    assert all(v == 0 for v in import_graph(other, doc).values())
    conflict = copy.deepcopy(doc); conflict['nodes'][0]['title'] = 'conflict'
    with pytest.raises(ValueError, match='Conflicting'):
        import_graph(other, conflict)
    bad = copy.deepcopy(doc); bad['edges'][0]['members'][0]['node_id'] = 'unknown'
    with pytest.raises(ValueError): import_graph(other, bad)
    bad = copy.deepcopy(doc); bad['version'] = 99
    with pytest.raises(ValueError): import_graph(other, bad)
    assert export_graph(other) == doc


def test_d_evidenced_overlap_and_no_title_only_claim(graph):
    a, b, weak = [node(graph, title) for title in ['Synthetic A', 'Synthetic B', 'Synthetic A title copy']]
    x, y, z = [node(graph, title, node_type='concept', kind='idea') for title in ['X', 'Y', 'Z']]
    ae = edge(graph, 'covers', [(a, 'source'), (x, 'concept'), (y, 'concept')])
    be = edge(graph, 'covers', [(b, 'source'), (x, 'concept'), (y, 'concept'), (z, 'concept')])
    graph.activity(a['id'], Activity(kind='position', end=100))
    recommendations = Recommender(graph.store).generate()
    r = next(r for r in recommendations if r['candidate_id'] == b['id'])
    assert set(r['overlap_concepts']) == {x['id'], y['id']} and r['additional_concepts'] == [z['id']]
    assert set(r['edge_ids']) == {ae['id'], be['id']}
    assert weak['id'] not in [r['candidate_id'] for r in recommendations]
    graph.edge_status(be['id'], 'rejected')
    assert not Recommender(graph.store).generate()


def test_e_contextual_recording_and_dismissal(graph):
    section = node(graph, 'Synthetic counterpoint section', kind='section')
    motif = node(graph, 'Synthetic motif', node_type='concept', kind='motif')
    recording = node(graph, 'Fixture recording', kind='recording', url='https://example.org/fixture-recording')
    cover = edge(graph, 'covers', [(section, 'source'), (motif, 'concept')])
    illustration = edge(graph, 'illustrates', [(recording, 'resource'), (motif, 'concept')])
    event = graph.activity(section['id'], Activity(kind='position', end=50))
    rec = Recommender(graph.store)
    r = rec.generate()[0]
    assert r['candidate_id'] == recording['id'] and r['activity_ids'] == [event['id']]
    assert set(r['edge_ids']) == {cover['id'], illustration['id']}
    assert 'current reading' in r['reason']
    rec.feedback(r['id'], Feedback(action='dismissed', note='Not now'))
    assert not rec.generate()
    assert not Recommender(Store(graph.store.root)).generate()


def test_f_reactions_newer_guest_and_ignore_not_dislike(graph):
    old = node(graph, 'Interview one', kind='interview', published='2025-01-01', url='https://example.org/one')
    new = node(graph, 'Interview two', kind='interview', published='2026-01-01', url='https://example.org/two')
    person = node(graph, 'Fixture guest', kind='person')
    edge(graph, 'features_person', [(old, 'resource'), (person, 'person')])
    edge(graph, 'features_person', [(new, 'resource'), (person, 'person')])
    graph.activity(old['id'], Activity(kind='reaction', reaction='like'))
    rec = Recommender(graph.store)
    r = rec.generate()[0]
    assert r['candidate_id'] == new['id'] and 'not been established' in r['reason']
    rec.feedback(r['id'], Feedback(action='ignored'))
    again = rec.generate()[0]
    assert again['score'] < r['score'] and again['score'] > r['score']-.2
    assert not graph.store.list('preferences')
    graph.settings({'recommendations_enabled': False, 'daily_limit': 3})
    assert not rec.generate()


def test_correction_merge_provenance_and_proposals(graph):
    a = node(graph, 'Fixture book')
    x = node(graph, 'Old concept', node_type='concept')
    y = node(graph, 'Canonical concept', node_type='concept')
    old = edge(graph, 'covers', [(a, 'source'), (x, 'concept')])
    graph.merge_concepts(x['id'], y['id'])
    assert graph.store.get('nodes', x['id'])['merged_into'] == y['id']
    assert graph.store.get('edges', old['id'])['status'] == 'superseded'
    current = next(e for e in graph.edges() if e['status'] == 'confirmed')
    assert any(m['node_id'] == y['id'] for m in current['members'])
    assert 'Old concept' in graph.store.get('nodes', y['id'])['aliases']
    with pytest.raises(ValueError):
        Edge(type='related_to', members=[{'node_id': a['id'], 'role': 'source'}, {'node_id': y['id'], 'role': 'concept'}], explanation='title similarity only', provenance=[{'kind':'heuristic','description':'lexical match'}], confidence=.99, status='confirmed')
    assert not UnavailableEnricher().health()['available']
    with pytest.raises(ValueError):
        validate_proposal({'relationships':[{'type':'related_to','members':[{'node_id':a['id'],'role':'source'},{'node_id':y['id'],'role':'concept'}], 'explanation':'Unsupported', 'status':'proposed', 'provenance':[{'kind':'model','description':'no source locator'}]}]}, {a['id'],y['id']})


def test_migration_upgrade_down_preserves_runtime(tmp_path):
    from par import db as module
    root = tmp_path/'old'; root.mkdir()
    connection = sqlite3.connect(root/'state.sqlite3')
    migrations = Path(module.__file__).parent/'migrations'
    connection.executescript((migrations/'001_initial.sql').read_text())
    connection.close()
    store = Store(root)
    p = store.add('projects', {'goal':'Preserved project'})
    graph = Knowledge(store)
    book = node(graph, 'Disposable rollback fixture')
    idea = node(graph, 'Rollback concept', node_type='concept')
    edge(graph, 'covers', [(book, 'source'), (idea, 'concept')])
    graph.activity(book['id'], Activity(kind='position', end=50))
    with store.connect() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 2
        db.executescript('BEGIN;'+(migrations/'002_intellectual_life.down.sql').read_text()+'COMMIT;')
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1
    assert Store(root).get('projects', p['id'])['goal'] == 'Preserved project'


def test_g_api_ui_and_cli(graph, tmp_path):
    with TestClient(create_app(Config(graph.store.root))) as client:
        assert client.get('/life').status_code == 200
        assert client.get('/static/life.js').status_code == 200
        assert client.post('/api/life/nodes', json={}).status_code == 403
        client.headers['X-PAR-CSRF'] = client.get('/api/session').json()['csrf']
        response = client.post('/api/life/nodes', json={'data':{'title':'UI fixture','total':200,'measure':'pages','provenance':[user_evidence('User entry')]}})
        assert response.status_code == 200, response.text
        id = response.json()['id']
        for start,end in [(90,100),(100,110)]:
            result = client.post('/api/life/nodes/'+id+'/activity', json={'kind':'reading','start':start,'end':end,'at':AT.isoformat()})
            assert result.status_code == 200, result.text
        state = client.get('/api/life/state').json()
        assert state['progress'][id]['fraction'] == .55
        assert not state['semantic']['available'] and not state['reader']['available']
        doc = client.get('/api/life/export').json()
        assert client.post('/api/life/import', json=doc).status_code == 200
    command = [sys.executable, '-m', 'par', '--data-root', str(graph.store.root), 'life']
    result = subprocess.run([*command,'resources','--search','UI fixture'],capture_output=True,text=True,timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)[0]['id'] == id
    result = subprocess.run([*command,'inspect',id],capture_output=True,text=True,timeout=30)
    assert json.loads(result.stdout)['progress']['newly_read'] == 20
    output = tmp_path/'graph.json'
    assert subprocess.run([*command,'export',str(output)],capture_output=True,timeout=30).returncode == 0
    assert json.loads(output.read_text())['format'] == 'omnibus-idea-graph'


def test_scan_symlinks_xml_entities_and_epub_units(graph, tmp_path):
    root = tmp_path/'books'; root.mkdir()
    outside = tmp_path/'outside.txt'; outside.write_text('Do not ingest via link')
    try:
        (root/'linked.txt').symlink_to(outside)
    except OSError:
        pass  # Windows may lack symlink privilege; XML protection still tested.
    epub(root/'normal.epub')
    with zipfile.ZipFile(root/'evil.epub','w') as z:
        z.writestr('META-INF/container.xml', '<!DOCTYPE x [<!ENTITY xx SYSTEM "file:///not-permitted">]><container>&xx;</container>')
    lib = Library(graph.store)
    report = lib.scan(lib.configure(str(root))['id'])
    assert len(report['discovered']) == 1 and report['issues']
    n = graph.store.get('nodes',report['discovered'][0])
    assert n['measure'] == 'chapters' and n['total'] == 2
    graph.activity(n['id'], Activity(kind='reading',start=0,end=1))
    p = graph.progress(n['id'])
    assert p['fraction'] == .5 and p['measure'] == 'chapters'
    assert all('Do not ingest' not in n['excerpt'] for n in graph.store.list('nodes'))


def test_graph_export_feedback_history_and_parent_cycle(graph, tmp_path):
    a = node(graph, 'Section')
    c = node(graph, 'Motif', node_type='concept')
    b = node(graph, 'Recording', url='https://example.org/fixture')
    edge(graph,'covers',[(a,'source'),(c,'concept')])
    edge(graph,'illustrates',[(b,'resource'),(c,'motif')])
    graph.activity(a['id'],Activity(kind='position',end=50))
    rec = Recommender(graph.store)
    item = rec.generate()[0]
    rec.feedback(item['id'],Feedback(action='dismissed',note='Explicit test reaction'))
    doc = export_graph(graph.store)
    other = Store(tmp_path/'imported')
    import_graph(other,doc)
    assert export_graph(other) == doc
    assert not Recommender(other).generate()
    assert other.list('preferences')[0]['origin'] == 'explicit'
    bad=copy.deepcopy(doc);bad['nodes'][0]['parent_id']=bad['nodes'][0]['id']
    with pytest.raises(ValueError,match='cycle'): import_graph(other,bad)


def test_portable_graph_in_database_backup(graph, tmp_path):
    from par.artifacts import Artifacts, restore
    n = node(graph, 'Backed-up book', measure='pages', total=200)
    graph.activity(n['id'],Activity(kind='reading',start=90,end=110,at=AT))
    path = Artifacts(graph.store).backup(tmp_path/'backup.zip')
    restore(path,tmp_path/'restored')
    other=Store(tmp_path/'restored')
    assert export_graph(other)==export_graph(graph.store)
    assert Knowledge(other).progress(n['id'])['fraction']==.55


def test_unconfirmed_and_expired_relations_do_not_recommend(graph):
    a=node(graph,'A');b=node(graph,'B');c=node(graph,'X',node_type='concept')
    e=edge(graph,'covers',[(a,'source'),(c,'concept')])
    other=edge(graph,'covers',[(b,'source'),(c,'concept')])
    graph.activity(a['id'],Activity(kind='position',end=100))
    graph.store.update('edges',other['id'],{'status':'proposed'})
    assert not Recommender(graph.store).generate()
    graph.store.update('edges',other['id'],{'status':'confirmed','valid_until':'2000-01-01'})
    assert not Recommender(graph.store).generate()


def test_semantic_proposal_cannot_invent_evidence_locator(graph):
    a=node(graph,'A');c=node(graph,'X',node_type='concept')
    context={a['id']:{'locator':'page:1'},c['id']:{'locator':None}}
    raw={'relationships':[{'type':'covers','members':[{'node_id':a['id'],'role':'source'},{'node_id':c['id'],'role':'concept'}], 'explanation':'Synthetic model-shaped proposal, not a live analysis', 'status':'proposed', 'provenance':[{'kind':'model','description':'Synthetic schema test','node_id':a['id'],'locator':'page:1'}]}]}
    assert validate_proposal(raw,context).relationships[0].status=='proposed'
    raw['relationships'][0]['provenance'][0]['locator']='invented:999'
    with pytest.raises(ValueError,match='locator'):validate_proposal(raw,context)
