"""One scoped collection request -> durable serial batches -> provisional result.

No provider call in planning. A scope grant is frozen before model execution.
Completed runs and ambiguous submissions survive process restart independently.
"""
import asyncio
import hashlib
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from filelock import FileLock
from .artifacts import Artifacts
from .db import now
from .knowledge import Knowledge
from .knowledge_models import Node
from .library import Library, parse_file, MAX_FILE, MAX_TEXT
from .local_inference import LocalModelConfig
from .semantic import SemanticService, AnalysisRequest
from .security import redact

VERSION = 'collection-1'
RETRY_DELAYS = (60, 300, 900)


def intent(text):
    if not re.search(r'\b(read|analy[sz]e|process|scan|build|map|understand)\b', text, re.I) or not re.search(r'\b(books?|library|collection|graph|directory|folder)\b', text, re.I):
        raise ValueError('This assistant currently supports reading a local collection and building its idea graph. State that outcome and include the directory.')
    quoted = [m.group('path') for m in re.finditer(r'''(?P<quote>["`'])(?P<path>.*?)(?P=quote)''', text)]
    paths = [p for p in quoted if re.match(r'^(?:[A-Za-z]:[\\/]|/|~/)', p)]
    if not paths:
        found = re.search(r'(?<![\w:./\\])([A-Za-z]:[\\/]|~/|/)[^\r\n]*?(?=[.!?](?:\s|$)|[;\r\n]|$)', text)
        if found:
            paths = [re.split(r'\s+(?:and|then)\s+', found.group(0), maxsplit=1, flags=re.I)[0].strip()]
    if len(paths) != 1:
        raise ValueError('Include exactly one absolute directory, in quotes if it contains spaces or punctuation.')
    if os.name != 'nt' and re.match(r'^[A-Za-z]:[\\/]', paths[0]):
        raise ValueError('This server is not Windows and cannot access '+paths[0]+'. Run Omnibus on the Windows computer that owns that directory, or use a directory on this host.')
    return paths[0]


def passages(text):
    """Contiguous exact offsets; paragraph/sentence boundaries preferred, never lost tails."""
    start = 0
    while start < len(text):
        end = min(start+2000, len(text))
        if end < len(text):
            options = [text.rfind('\n\n', start+1000, end), text.rfind('. ', start+1000, end)]
            cut = max(options)
            if cut >= 0: end = cut+2
        yield start, end, text[start:end]
        start = end


class Collections:
    def __init__(self, store, owner=None):
        self.store, self.artifacts = store, Artifacts(store)
        self.graph, self.library = Knowledge(store), Library(store)
        self.semantic = SemanticService(store, owner)
        self.jobs = {}
        self.serial = asyncio.Lock()
        self.closing = False

    def prepare(self, command):
        # One local planner per data root, including concurrent browser requests.
        # A process crash releases the OS lock; stable passages remain reusable.
        with FileLock(str(self.store.root / 'collection-plan.lock')):
            return self._prepare(command)

    def _prepare(self, command):
        root = self.library.configure(intent(command))
        report = self.library.scan(root['id'])
        ids = sorted(set(report['discovered']+report['unchanged']+[r['id'] for r in report['duplicates']]))
        signature = hashlib.sha256(json.dumps([VERSION, root['path'], [(id,self.store.get('nodes',id)['sha256']) for id in ids], report['issues']], sort_keys=True).encode()).hexdigest()
        existing = next((j for j in self.store.list('collection_jobs') if j['signature'] == signature), None)
        if existing and existing['status'] != 'partial':
            return existing  # Repeated commands return their existing durable work, not duplicate graph writes.
        issues, manifest = list(report['issues']), []
        known = {n['metadata']['collection_passage']['key']: n for n in self.store.list('nodes') if n['metadata'].get('collection_passage')}
        for id in ids:
            resource = self.store.get('nodes', id)
            item = {'resource_id': id, 'title': resource['title'], 'sha256': resource['sha256'], 'passage_ids': [], 'characters': 0, 'whitespace_characters': 0}
            try:
                content, path = self.read_resource(resource, root['path'])
                parsed = parse_file(path, content, text_limit=MAX_TEXT, full_text=True)
                item['path'] = str(path)
                for section in parsed['units']:
                    text = section['analysis_text']
                    if section['truncated']:
                        raise ValueError('Full extraction unexpectedly truncated a section; refusing partial reading')
                    if not text.strip():
                        issues.append({'path': str(path), 'section': section['locator'], 'reason': 'No extractable text; images/OCR/empty section not analyzed'})
                        continue
                    for start, end, chunk in passages(text):
                        item['characters'] += len(chunk)
                        if not chunk.strip():
                            item['whitespace_characters'] += len(chunk)
                            continue
                        key = hashlib.sha256(json.dumps([VERSION, id, section['locator'], start, end, chunk]).encode()).hexdigest()
                        unit = known.get(key)
                        digest = hashlib.sha256(chunk.encode()).hexdigest()
                        if unit and (unit['sha256'] != digest or unit['parent_id'] != id):
                            raise ValueError('Stored passage identity does not match this source snapshot')
                        if not unit:
                            artifact = self.artifacts.write(chunk.encode(), kind='collection-passage', provenance=resource['sha256'])
                            data = Node(node_type='unit', kind='collection-passage', title=(section['title'][:400]+f' · passage {start+1}–{end}'),
                                locator=section['locator'][:350]+f' #text:{start}:{end}', total=100, ordinal=section['ordinal'], excerpt=chunk[:600],
                                sha256=digest,
                                provenance=[{'kind':'extracted','node_id':id,'locator':section['locator'][:500], 'sha256':resource['sha256'],
                                             'description':f'Full-text extraction, exact section character range {start}:{end}; not an assertion of understanding.'}],
                                metadata={'collection_passage': {'key':key,'artifact_id':artifact['id'],'section_locator':section['locator'], 'start':start,'end':end,'source_sha256':resource['sha256']}})
                            unit = self.graph.node(data, id); known[key] = unit
                        item['passage_ids'].append(unit['id'])
                if not item['passage_ids']:
                    raise ValueError('No available text passages could be extracted')
            except (ValueError, OSError, KeyError) as exc:
                issues.append({'resource_id':id, 'reason':str(exc)[:500]})
                item['extraction_error'] = str(exc)[:500]
            manifest.append(item)
        if existing and existing['manifest'] == manifest and existing['issues'] == issues:
            return existing
        # Interleave books: early batches offer actual cross-book evidence without
        # requiring users to select passages. Every remaining passage is still scheduled.
        ordered = []
        for index in range(max([len(m['passage_ids']) for m in manifest] or [0])):
            ordered.extend(m['passage_ids'][index] for m in manifest if index < len(m['passage_ids']))
        allowed = set(ordered)
        reused = {}
        for run in self.store.list('runs'):
            review = run.get('worker_metadata', {}).get('semantic')
            if not review: continue
            task = self.store.get('tasks', run['task_id'])
            spec = task.get('semantic', {})
            if not spec.get('collection_id'): continue
            prior = self.store.get('collection_jobs', spec['collection_id'])
            sources = spec.get('source_ids', [])
            if prior['version'] != VERSION or not sources or not set(sources) <= allowed: continue
            try:
                self.artifacts.read(review['raw_artifact'])
                self.artifacts.read(spec['input_artifact'])
                for source_id in sources: self.semantic.source(source_id)
            except (ValueError, OSError, KeyError): continue
            for source_id in sources: reused.setdefault(source_id, run['id'])
        groups = {}
        for source_id in ordered:
            if source_id in reused: groups.setdefault(reused[source_id], []).append(source_id)
        batches = [{'source_ids':ids, 'status':'completed', 'run_id':run_id, 'attempts':0, 'reused':True} for run_id,ids in groups.items()]
        pending = [id for id in ordered if id not in reused]
        batches += [{'source_ids':pending[i:i+6], 'status':'pending','run_id':None,'attempts':0} for i in range(0,len(pending),6)]
        value = {'command':command, 'root':root['path'], 'signature':signature, 'version':VERSION,
                 'status':('awaiting_approval' if pending else ('partial' if issues or not batches else 'completed')), 'manifest':manifest, 'issues':issues,
                 'batches':batches, 'approval':None, 'error':None, 'next_attempt_at':None,
                 'plan':['Read-only inventory and complete supported text extraction',
                         'Preserve exact passage snapshots and section/character citations',
                         'Analyze every passage in automatic serial batches of at most six',
                         'Reconcile evidence-backed identities against prior collection findings; retain uncertain matches',
                         'Build provisional n-ary coverage/co-discussion graph and executive result'],
                 'limitations':['Model findings are selective and provisional, not exhaustive proof of understanding.',
                                'Canonical reconciliation uses a bounded relevant context, not an exhaustive all-pairs ontology merge.',
                                'Best-effort secret redaction can alter text sent to the provider; inspect the saved semantic input snapshots when checking quotations.']}
        job = self.store.add('collection_jobs', value)
        self.store.event(job['id'], 'collection_planned', {'batch_count':len(batches), 'issues':len(issues), 'signature':signature})
        return job

    def read_resource(self, resource, root):
        for location in resource['locations']:
            p = Path(location)
            if p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(Path(root)):
                continue
            before = p.stat()
            if before.st_size > MAX_FILE: continue
            flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
            with os.fdopen(os.open(p, flags), 'rb') as f:
                opened = os.fstat(f.fileno())
                if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino) or p.is_symlink() or not p.resolve().is_relative_to(Path(root)):
                    continue
                content = f.read(MAX_FILE+1)
            if len(content) <= MAX_FILE and hashlib.sha256(content).hexdigest() == resource['sha256']:
                return content, p
        raise ValueError('Source changed/disappeared or left the approved root before extraction; rescan required')

    def approve(self, id, provider):
        job = self.store.get('collection_jobs', id)
        if job['status'] != 'awaiting_approval': return job
        config = self.semantic.config()
        if config.backend != 'browser' or not config.dedicated_browser_profile:
            raise ValueError('Set up your signed-in browser account once before starting. No Ollama or API subscription is required.')
        if provider != config.browser_provider:
            raise ValueError('Provider changed; review the disclosure before approving')
        approval = {'provider':provider, 'config':config.model_dump(), 'at':now(), 'signature':job['signature'],
                    'scope':'Snapshotted text of this directory collection and its derived graph evidence; analysis/reconciliation only. No purchases, publication, account changes, or other external actions.'}
        self.store.event(id, 'collection_disclosure_approved', approval)
        return self.store.update('collection_jobs', id, {'approval':approval,'status':'queued','error':None})

    def schedule(self, id):
        if id not in self.jobs:
            task = asyncio.create_task(self.execute(id))
            self.jobs[id] = task
            def finished(done):
                if self.jobs.get(id) is done: self.jobs.pop(id, None)
                if not self.closing and self.store.get('collection_jobs', id)['status'] == 'queued':
                    self.schedule(id)
            task.add_done_callback(finished)

    def recover(self):
        self.closing = False
        for job in self.store.list('collection_jobs'):
            if job['approval'] and job['status'] in {'queued','running','waiting'}:
                # execute inspects the actual durable child run BEFORE any retry.
                self.schedule(job['id'])

    async def shutdown(self):
        self.closing = True
        tasks = list(self.jobs.values())
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def pause(self, id):
        job = self.store.get('collection_jobs', id)
        if job['status'] in {'queued','running','waiting'}:
            self.store.update('collection_jobs', id, {'status':'paused','error':'Paused by you; completed work retained'})
            if task := self.jobs.get(id): task.cancel()
        return self.store.get('collection_jobs', id)

    def ambiguous(self, run):
        return bool(run.get('worker_metadata', {}).get('browser_delivery') and not run.get('acceptance', {}).get('response_captured') and not run.get('worker_metadata',{}).get('browser_response_cache'))

    def resume(self, id, verified_not_sent=False):
        job = self.store.get('collection_jobs', id)
        if not job['approval']: raise ValueError('Approve the collection disclosure first')
        if job['status'] in {'completed','running','queued'}: return job
        for batch in job['batches']:
            if batch['status'] == 'completed' or not batch['run_id']: continue
            run = self.store.get('runs', batch['run_id'])
            if run.get('worker_metadata', {}).get('semantic'):
                batch['status'] = 'completed'
                continue
            if run.get('worker_metadata', {}).get('browser_response_cache') and run.get('error_kind') != 'invalid_output':
                batch['status'] = 'running'
                continue
            if self.ambiguous(run):
                if not verified_not_sent:
                    raise ValueError('Submission outcome is ambiguous. Inspect the provider tab first; automatic replay is forbidden. Confirm not sent only if you actually verified that.')
                self.store.event(id, 'operator_verified_not_sent', {'run_id':run['id'], 'explicit_new_submission_authorized':True})
            # Resume is an explicit retry for malformed/invalid results, never an
            # automatic claim that they succeeded. Historical runs are retained.
            batch['status'], batch['run_id'], batch['attempts'] = 'pending', None, 0
        return self.store.update('collection_jobs', id, {'status':'queued','error':None,'batches':job['batches'], 'next_attempt_at':None})

    def context(self, job, source_ids):
        allowed = {id for m in job['manifest'] for id in m['passage_ids']}
        nodes = {n['id']:n for n in self.store.list('nodes')}
        quotes = {}
        for edge in self.graph.edges():
            if edge['status'] not in {'proposed','confirmed'} or edge['type'] not in {'covers','illustrates','features_person'}: continue
            if not any(m['node_id'] in allowed for m in edge['members']): continue
            for member in edge['members']:
                if member['role'] not in {'concept','person'}: continue
                for p in edge['provenance']:
                    if p.get('node_id') in allowed and 'verbatim quote: ' in p['description']:
                        quotes.setdefault(member['node_id'], set()).add(p['description'].split('verbatim quote: ',1)[1])
        text = ' '.join(self.semantic.source(id)['text'] for id in source_ids).casefold()
        words = set(re.findall(r'\w+', text))
        ranked = []
        for id, evidence in quotes.items():
            n = nodes[id]
            # Do not disclose a canonical description derived from a different,
            # out-of-scope collection just because one quoted passage overlaps.
            try:
                origin_run = self.store.get('runs', n['metadata']['semantic_run'])
                origin_spec = self.store.get('tasks', origin_run['task_id'])['semantic']
                if not set(origin_spec['source_ids']) <= allowed: continue
            except KeyError:
                continue
            if n['status'] != 'active': continue
            score = len(words & set(re.findall(r'\w+', (n['title']+' '+n['metadata'].get('description','')).casefold())))
            ranked.append((score,id,{'id':id,'label':n['title'],'kind':n['kind'],'description':n['metadata'].get('description',''), 'quotes':sorted(evidence)[:2]}))
        return [c for _,_,c in sorted(ranked, key=lambda x:(-x[0],x[1]))[:16]]

    async def execute(self, id):
        try:
            async with self.serial:
                job = self.store.get('collection_jobs', id)
                if not job['approval'] or job['status'] not in {'queued','running','waiting'}: return
                config = LocalModelConfig.model_validate(job['approval']['config'])
                if job['approval']['signature'] != job['signature']: raise ValueError('Scope signature changed; approval is invalid')
                while True:
                    job = self.store.get('collection_jobs', id)
                    if job['status'] == 'paused': return
                    if job['next_attempt_at']:
                        wait = (datetime.fromisoformat(job['next_attempt_at'])-datetime.now(timezone.utc)).total_seconds()
                        if wait > 0: await asyncio.sleep(wait)
                    index = next((i for i,b in enumerate(job['batches']) if b['status'] != 'completed'), None)
                    if index is None:
                        self.store.update('collection_jobs', id, {'status':'partial' if job['issues'] else 'completed', 'error':None,'next_attempt_at':None})
                        self.store.event(id, 'collection_finished', {'complete_text_processing':not job['issues']})
                        return
                    batches = job['batches']; batch = batches[index]
                    run = self.store.get('runs', batch['run_id']) if batch['run_id'] else None
                    if run and run.get('worker_metadata',{}).get('semantic'):
                        # Proposal transaction is authoritative, even if interruption
                        # happened before the runtime's final response checkpoint.
                        batch['status'] = 'completed'
                        self.store.update('collection_jobs',id,{'batches':batches,'status':'running','error':None,'next_attempt_at':None})
                        continue
                    if run and run.get('worker_metadata',{}).get('browser_response_cache') and run['status'] in {'paused','failed'} and run.get('error_kind') != 'invalid_output':
                        recovered = self.semantic.runtime.retry(run['id'], acknowledge_uncertainty=True)
                        batch['run_id'] = recovered['id']
                        self.store.update('collection_jobs',id,{'batches':batches})
                        run = recovered
                    if run and self.ambiguous(run):
                        self.store.update('collection_jobs',id,{'status':'needs_attention','error':'Ambiguous browser submission. No automatic replay; inspect the provider tab.', 'next_attempt_at':None})
                        return
                    if run and run['status'] not in {'queued'}:
                        kind = run.get('error_kind')
                        if kind in {'browser_unavailable','model_unavailable','rate_limit','interrupted'} and batch['attempts'] <= len(RETRY_DELAYS):
                            # All known browser submissions were ruled out above.
                            delay = RETRY_DELAYS[min(max(batch['attempts']-1,0),len(RETRY_DELAYS)-1)]
                            batch['run_id'] = None
                            self.store.update('collection_jobs',id,{'batches':batches,'status':'waiting','error':run.get('error'),
                                'next_attempt_at':(datetime.now(timezone.utc)+timedelta(seconds=delay)).isoformat()})
                            continue
                        self.store.update('collection_jobs',id,{'status':'needs_attention','error':run.get('error') or 'Batch did not produce a validated semantic result','next_attempt_at':None})
                        return
                    if not run:
                        context = self.context(job, batch['source_ids'])
                        accepted = self.semantic.submit(AnalysisRequest(source_ids=batch['source_ids'],authorize_provider=config.browser_provider),
                            scoped_config=config, collection_id=id, canonical_context=context)
                        batch.update(run_id=accepted['run_id'],status='running',attempts=batch['attempts']+1)
                        self.store.update('collection_jobs',id,{'batches':batches,'status':'running','error':None,'next_attempt_at':None})
                        run = self.store.get('runs',batch['run_id'])
                    await self.semantic.runtime.execute(run['id'])
        except asyncio.CancelledError:
            job = self.store.get('collection_jobs',id)
            if job['status'] != 'paused':
                self.store.update('collection_jobs',id,{'status':'queued','error':'Process stopped; resume will reconcile the last run before sending anything'})
            raise
        except Exception as exc:
            self.store.update('collection_jobs',id,{'status':'needs_attention','error':redact(str(exc))[:600]})
            self.store.event(id,'collection_failed',{'reason':redact(str(exc))[:600]})

    def result(self, id):
        job = self.store.get('collection_jobs',id)
        runs = [self.store.get('runs',b['run_id']) for b in job['batches'] if b['run_id']]
        reviews = [r['worker_metadata']['semantic'] for r in runs if r.get('worker_metadata',{}).get('semantic')]
        edge_ids = {id for r in reviews for id in r['edge_ids']}
        all_edges = self.graph.edges()
        while True:
            expanded = edge_ids | {e['id'] for e in all_edges if e.get('supersedes') in edge_ids}
            if expanded == edge_ids: break
            edge_ids = expanded
        edges = [e for e in all_edges if e['id'] in edge_ids]
        nodes = {n['id']:n for n in self.store.list('nodes')}
        memberships = {m['node_id'] for e in edges for m in e['members']}
        themes = []
        concept_ids = {m['node_id'] for e in edges if e['status'] in {'proposed','confirmed'} for m in e['members'] if m['role'] in {'concept','person'}}
        for id in concept_ids:
            n = nodes[id]
            sources = {m['node_id'] for e in edges if e['status'] in {'proposed','confirmed'} and any(x['node_id']==id for x in e['members']) for m in e['members'] if m['role'] in {'source','resource'}}
            books = {nodes[s]['parent_id'] or s for s in sources}
            themes.append({'id':id,'title':n['title'],'description':n['metadata'].get('description',''), 'books':sorted(books), 'passages':len(sources),
                           'status':'provisional identity/coverage unless its supporting edges are explicitly reviewed'})
        labels = {}
        for t in themes: labels.setdefault(t['title'].casefold(),[]).append(t['id'])
        done = [b for b in job['batches'] if b['status']=='completed' or (b['run_id'] and any(r['run_id']==b['run_id'] for r in reviews))]
        return {'job':job,'runs':runs,'summary':{'resources':len(job['manifest']), 'passages':sum(len(m['passage_ids']) for m in job['manifest']),
            'extracted_characters':sum(m['characters'] for m in job['manifest']), 'completed_batches':len(done),'total_batches':len(job['batches']),
            'completed_passages':sum(len(b['source_ids']) for b in done), 'reused_passages':sum(len(b['source_ids']) for b in job['batches'] if b.get('reused')), 'themes':sorted(themes,key=lambda t:(-len(t['books']),-t['passages'],t['title'])),
            'cross_book_connections':[t for t in themes if len(t['books'])>1], 'single_book_topics':[t for t in themes if len(t['books'])==1],
            'reused_identities':sum(len(r.get('reused_concept_ids',[])) for r in reviews),
            'unresolved_same_label_candidates':[v for v in labels.values() if len(v)>1],
            'uncovered_sources':[{**u, 'title':nodes[u['source_id']]['title'], 'locator':nodes[u['source_id']]['locator'], 'artifact_id':nodes[u['source_id']]['metadata'].get('collection_passage',{}).get('artifact_id')} for r in reviews for u in r.get('uncovered_sources',[])],
            'uncertainties':job['limitations']+[r['limitations'] for r in reviews]},
            'graph':{'nodes':[nodes[id] for id in memberships], 'edges':edges}}
