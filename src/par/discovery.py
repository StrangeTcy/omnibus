"""Provider-independent, opt-in search/retrieval; model prose is never search proof."""
import hashlib
import json
from datetime import date
from html.parser import HTMLParser
from typing import Protocol, Literal
from urllib.parse import urlencode, urlsplit, parse_qs, urljoin
from pydantic import Field
from .schemas import Payload
from .db import now
from .artifacts import Artifacts
from .knowledge import Knowledge
from .knowledge_models import Node, Edge
from .library import html_text
from .web_retrieval import PublicFetcher


class SearchBackend(Protocol):
    def search(self, query: str) -> tuple[object, list[str]]: ...


class SearchLinks(HTMLParser):
    def __init__(self):
        super().__init__(); self.urls = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'a' and 'result__a' in a.get('class', '').split():
            url = urljoin('https://html.duckduckgo.com/', a.get('href', ''))
            p = urlsplit(url)
            if p.hostname in {'duckduckgo.com', 'html.duckduckgo.com'}:
                url = parse_qs(p.query).get('uddg', [''])[0]
            if url.startswith(('https://', 'http://')) and url not in self.urls:
                self.urls.append(url)


class PublicSearch:
    """Actual unauthenticated HTML request; no key, account or claimed LLM search."""
    def __init__(self, fetcher): self.fetcher = fetcher
    def search(self, query):
        page = self.fetcher.fetch('https://html.duckduckgo.com/html/?'+urlencode({'q': query}))
        parser = SearchLinks(); parser.feed(page.body)
        return page, parser.urls[:3]


class Metadata(HTMLParser):
    def __init__(self):
        super().__init__(); self.dates = []; self.jsonld = []; self.script = None
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'meta' and a.get('property', a.get('name', '')).lower() in {'article:published_time', 'datepublished', 'date'}:
            self.dates.append(a.get('content', ''))
        if tag == 'script' and a.get('type') == 'application/ld+json': self.script = ''
    def handle_data(self, text):
        if self.script is not None and len(self.script) < 100000: self.script += text
    def handle_endtag(self, tag):
        if tag == 'script' and self.script is not None:
            self.jsonld.append(self.script); self.script = None


def extract(page):
    title, text = html_text(page.body) if page.content_type != 'text/plain' else ('', page.body)
    if not title or len(text.strip()) < 40:
        raise ValueError('No usable page title/text; a JS-only/media page is not verified by this fetcher')
    if any(s in title.casefold() for s in ['just a moment', 'access denied', 'captcha', 'sign in', 'log in', 'page not found']):
        raise ValueError('Login/challenge/error page is not a verified resource; no bypass attempted')
    parser = Metadata(); parser.feed(page.body)
    def visit(value, depth=0):
        if depth > 10: return
        if isinstance(value, dict):
            # datePublished on the media/article itself, not arbitrary nested comments.
            if value.get('@type') in ['VideoObject', 'AudioObject', 'Article', 'NewsArticle', 'PodcastEpisode']:
                parser.dates.append(value.get('datePublished', ''))
            for key in ['@graph', 'mainEntity', 'subjectOf']:
                visit(value.get(key), depth+1)
        elif isinstance(value, list):
            for child in value[:100]: visit(child, depth+1)
    for raw in parser.jsonld[:20]:
        try: visit(json.loads(raw))
        except ValueError: pass
    dates = set()
    for raw in parser.dates:
        try: dates.add(date.fromisoformat(str(raw)[:10]).isoformat())
        except ValueError: pass
    return {'title': title[:500], 'text': text[:60000], 'published': next(iter(dates)) if len(dates) == 1 else None,
            'date_evidence': parser.dates[:20],
            'uncertainties': ['Title and date are page-reported metadata, not independently established truth.',
                              'Guest identity, semantic relevance and recording content are not verified by URL retrieval.']+
                             (['No unambiguous publication date found.'] if len(dates) != 1 else [])}


class DiscoveryRequest(Payload):
    focus_id: str
    query: str = Field(default='', max_length=400)
    url: str | None = Field(default=None, max_length=2000)
    authorize_network: bool = False

class LinkProposal(Payload):
    target_id: str
    relation: Literal['covers', 'illustrates', 'features_person']
    quote: str = Field(min_length=10, max_length=500)


def verified_snapshot(store, node):
    """Do not trust an editable metadata flag or imported graph without artifacts."""
    info = node.get('metadata', {}).get('discovery')
    if not info:
        return None
    try:
        artifact = store.get('artifacts', info['snapshot_id'])
        if artifact['kind'] != 'verified-public-page': return None
        artifacts = Artifacts(store)
        snap = json.loads(artifacts.read(artifact['id']))
        raw = json.loads(artifacts.read(snap['raw_artifact']))
        if raw['status'] != 200 or raw['url'] != snap['url']: return None
        if snap['origin'] == 'public_search':
            search = store.get('artifacts', snap['search_snapshot'])
            if search['kind'] != 'public-search-results': return None
            artifacts.read(search['id'])
        if any(node.get(k) != snap[k] for k in ['url', 'title', 'published']): return None
        return snap
    except (KeyError, ValueError, OSError, TypeError):
        return None


def link_evidence(store, node):
    if not node.get('url'):
        return {'status': 'local', 'url': None, 'uncertainties': []}
    if snap := verified_snapshot(store, node):
        return {'status': 'retrieved', 'url': snap['url'], 'checked_at': snap['retrieved_at'],
                'snapshot_id': node['metadata']['discovery']['snapshot_id'], 'origin': snap['origin'],
                'uncertainties': snap['uncertainties']+['URL was reachable at retrieval time; not continuously monitored.']}
    if node.get('metadata', {}).get('discovery'):
        return {'status': 'unverified_discovery', 'url': None, 'uncertainties': ['Missing/mismatched retrieval evidence; reverify before recommendation.']}
    if any(p['kind'] == 'user' for p in node.get('provenance', [])):
        return {'status': 'manual_unverified', 'url': node['url'], 'uncertainties': ['Manually supplied URL and metadata; not independently retrieved or verified.']}
    return {'status': 'unverified_claim', 'url': None, 'uncertainties': ['Model/extracted URL has no retrieval evidence.']}


class Discovery:
    def __init__(self, store, fetcher=None, search=None):
        self.store, self.graph, self.artifacts = store, Knowledge(store), Artifacts(store)
        self.fetcher = fetcher or PublicFetcher()
        self.search = search or PublicSearch(self.fetcher)

    def context(self, focus_id):
        focus = self.store.get('nodes', focus_id)
        nodes = {n['id']: n for n in self.store.list('nodes')}
        edges = [e for e in self.graph.edges() if e['status'] == 'confirmed']
        subjects, evidence = [], []
        for e in edges:
            if any(m['node_id'] == focus_id for m in e['members']) and e['type'] in {'covers', 'features_person'}:
                subjects.extend(nodes[m['node_id']]['title'] for m in e['members'] if m['role'] in {'concept', 'person'})
                evidence.append(e['id'])
        reactions = [a for a in self.store.list('activity') if a['node_id'] == focus_id and a['kind'] == 'reaction']
        liked = bool(reactions and sorted(reactions, key=lambda a: (a['at'], a['created']))[-1]['reaction'] == 'like')
        query = ' '.join(subjects[:3]) or focus['title']
        query += ' interview' if liked else ' lecture recording'
        return {'focus_id': focus_id, 'query': query[:400], 'edge_ids': evidence,
                'progress': self.graph.progress(focus_id) if focus['node_type'] != 'concept' else None,
                'reason': 'Positive reaction and supplied/confirmed subjects' if liked else 'Selected reading position or interest and confirmed concepts',
                'limitation': 'Query is a search lead, not proof of relevance. Review it before sending publicly.'}

    def snapshot(self, page, kind):
        return self.artifacts.write(json.dumps({'url': page.url, 'status': page.status, 'content_type': page.content_type,
                                               'body': page.body, 'retrieved_at': now()}, ensure_ascii=False).encode(),
                                    kind=kind, mime='application/json', provenance='actual public HTTP retrieval')

    def candidate(self, url, origin, report):
        page = self.fetcher.fetch(url)
        if page.status != 200: raise ValueError('Destination was not successfully retrieved')
        facts = extract(page)
        raw = self.snapshot(page, 'public-page-raw')
        snap = {**facts, 'url': page.url, 'origin': origin, 'retrieved_at': now(), 'raw_artifact': raw['id'], 'search_snapshot': report.get('search_snapshot')}
        artifact = self.artifacts.write(json.dumps(snap, ensure_ascii=False).encode(), kind='verified-public-page', mime='application/json', provenance='checked URL and page-reported metadata')
        provenance = [{'kind': 'observed', 'description': 'Retrieved HTTP 200 public page; title and reported publication metadata extracted. Relevance/guest identity not established.',
                       'locator': page.url[:500], 'sha256': raw['sha256']}]
        node = self.graph.node(Node(title=facts['title'], kind='web-resource', url=page.url, published=facts['published'], excerpt=facts['text'][:600],
                                   provenance=provenance, metadata={'discovery': {'snapshot_id': artifact['id'], 'origin': origin}}))
        # Text units can join the existing multi-source semantic analysis, not a new model path.
        for i, start in enumerate(range(0, min(len(facts['text']), 12000), 2000)):
            text = facts['text'][start:start+2000]
            self.graph.node(Node(node_type='unit', title=f'{facts["title"][:450]} — retrieved segment {i+1}', kind='web-excerpt',
                                 locator=f'char:{start}:{start+len(text)}', ordinal=i+1, total=100, excerpt=text[:600],
                                 sha256=hashlib.sha256(text.encode()).hexdigest(), provenance=provenance), node['id'])
        self.store.event(node['id'], 'public_resource_retrieved', {'snapshot_id': artifact['id'], 'origin': origin})
        return node['id']

    def discover(self, request: DiscoveryRequest):
        if not request.authorize_network:
            raise ValueError('Explicit public network retrieval approval is required')
        context = self.context(request.focus_id)
        report = {'at': now(), 'context': context, 'query': request.query or context['query'], 'candidates': [], 'issues': [],
                  'origin': 'manually_supplied_url' if request.url else 'public_search', 'search_performed': False}
        try:
            if request.url:
                urls = [request.url]
            else:
                page, urls = self.search.search(report['query'])
                if page.status != 200:
                    raise ValueError('Search endpoint did not return a successful page')
                artifact = self.snapshot(page, 'public-search-results')
                report.update(search_performed=True, search_snapshot=artifact['id'])
                if not urls:
                    report['issues'].append('Search returned no usable links or a challenge/layout change. Supply a URL manually; no model search claim substituted.')
            for url in urls[:3]:
                try: report['candidates'].append(self.candidate(url, report['origin'], report))
                except ValueError as exc: report['issues'].append(str(exc))
        except ValueError as exc:
            report['issues'].append(str(exc))
        artifact = self.artifacts.write(json.dumps(report, ensure_ascii=False).encode(), kind='discovery-report', mime='application/json', provenance='explicit network request; failures retained')
        return {**report, 'report_id': artifact['id']}

    def propose_link(self, resource_id, body: LinkProposal):
        node = self.store.get('nodes', resource_id)
        target = self.store.get('nodes', body.target_id)
        snap = verified_snapshot(self.store, node)
        if not snap or body.quote not in snap['text']:
            raise ValueError('Quote must occur verbatim in the verified page text')
        if body.relation in {'covers', 'illustrates'} and target['node_type'] != 'concept':
            raise ValueError('Choose an existing concept for coverage/illustration')
        if body.relation == 'features_person' and target['kind'] != 'person':
            raise ValueError('Choose an explicitly identified person; guest identity is not inferred from titles')
        return self.graph.edge(Edge(type=body.relation, status='proposed', confidence=.6,
            members=[{'node_id':resource_id, 'role':'source' if body.relation == 'covers' else 'resource'},
                     {'node_id':target['id'], 'role':'person' if body.relation == 'features_person' else 'concept'}],
            provenance=[{'kind':'heuristic', 'description':'User-selected candidate relationship, not automatic semantic verification. Retrieved quote: '+body.quote,
                         'node_id':resource_id, 'locator':snap['url'][:500], 'sha256':self.store.get('artifacts', node['metadata']['discovery']['snapshot_id'])['sha256']}],
            explanation='Proposed connection supported by a retrieved passage; review the relationship and identity before confirmation.'))


def checked_discovery_edge(store, edge, nodes):
    """Discovered resources need retrieved support for the relation, not just a URL."""
    if edge['type'] not in {'covers', 'illustrates', 'features_person'}:
        return True
    for member in edge['members']:
        if member['role'] not in {'source', 'resource', 'example'}:
            continue
        participant = nodes[member['node_id']]
        resource = nodes.get(participant.get('parent_id'), participant) if participant['node_type'] == 'unit' else participant
        if not resource.get('metadata', {}).get('discovery'):
            continue
        snap = verified_snapshot(store, resource)
        if not snap: return False
        quotes = []
        for p in edge['provenance']:
            if p.get('node_id') not in {resource['id'], participant['id']}:
                continue
            for marker in ['verbatim quote: ', 'Retrieved quote: ']:
                if marker in p['description']:
                    quote = p['description'].split(marker, 1)[1]
                    if quote and quote in snap['text']: quotes.append(quote)
        if not quotes: return False
        if edge['type'] == 'features_person':
            people = [nodes[m['node_id']] for m in edge['members'] if m['role'] == 'person']
            if not people or not all(any(name.casefold() in q.casefold() for name in [person['title'], *person.get('aliases', [])] for q in quotes) for person in people):
                return False
    return True
