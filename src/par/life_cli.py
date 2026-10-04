import json
from datetime import datetime, timezone
from pathlib import Path
from .knowledge import Knowledge, payload, user_evidence
from .knowledge_models import Node, Edge, Activity, Feedback
from .library import Library
from .recommendations import Recommender
from .graph_io import export_graph, import_graph
from .enrichment import UnavailableEnricher


def configure(commands):
    parser = commands.add_parser('life', help='Local library, reading progress, idea hypergraph and recommendations (no model)')
    subs = parser.add_subparsers(dest='life_command', required=True)
    root = subs.add_parser('root', help='Authorize a local read-only library directory')
    root.add_argument('path')
    scan = subs.add_parser('scan', help='Scan a configured root ID (never edits originals)')
    scan.add_argument('root_id')
    resources = subs.add_parser('resources', help='List/search resource or concept nodes')
    resources.add_argument('--search', default='')
    add = subs.add_parser('add', help='Add manual resource, URL, person, or concept')
    add.add_argument('title')
    add.add_argument('--node-type', choices=['resource', 'concept'], default='resource')
    add.add_argument('--kind', default='book')
    add.add_argument('--url')
    add.add_argument('--published')
    add.add_argument('--measure', choices=['pages', 'chapters', 'percent', 'seconds'], default='percent')
    add.add_argument('--total', type=float, default=100)
    add.add_argument('--evidence', required=True)
    inspect = subs.add_parser('inspect', help='Inspect node and progress/history')
    inspect.add_argument('id')
    edit = subs.add_parser('edit', help='Correct a node title; prior metadata is retained in events')
    edit.add_argument('id')
    edit.add_argument('--title', required=True)
    progress = subs.add_parser('progress', help='Append reading, position, revisit, or correction')
    progress.add_argument('id')
    progress.add_argument('--kind', choices=['reading', 'position', 'revisit', 'correction'], default='reading')
    progress.add_argument('--start', type=float)
    progress.add_argument('--end', type=float, required=True)
    progress.add_argument('--date', help='UTC date YYYY-MM-DD; defaults to now')
    progress.add_argument('--source', choices=['manual', 'reader_import', 'estimate'], default='manual')
    progress.add_argument('--corrects')
    reaction = subs.add_parser('react', help='Record an explicit reaction')
    reaction.add_argument('id')
    reaction.add_argument('reaction', choices=['like', 'dislike', 'neutral'])
    edge = subs.add_parser('connect', help='Add typed n-ary relationship with evidence')
    edge.add_argument('--type', required=True)
    edge.add_argument('--member', action='append', required=True, help='NODE_ID:role; repeat for every participant')
    edge.add_argument('--evidence', required=True)
    edge.add_argument('--explanation', required=True)
    edge.add_argument('--confidence', type=float, default=1)
    edge.add_argument('--status', choices=['proposed', 'confirmed'], default='confirmed')
    decision = subs.add_parser('relationship', help='Confirm or reject/disconnect an edge')
    decision.add_argument('id')
    decision.add_argument('status', choices=['confirmed', 'rejected'])
    edgefile = subs.add_parser('edge-json', help='Create/correct an edge from a validated JSON payload; use supersedes for correction')
    edgefile.add_argument('file', type=Path)
    merge = subs.add_parser('merge-concepts')
    merge.add_argument('source')
    merge.add_argument('target')
    graph = subs.add_parser('graph', help='Inspect an incidence neighborhood with all member roles')
    graph.add_argument('--focus')
    graph.add_argument('--search', default='')
    subs.add_parser('recommendations', help='Generate/explain sparse suggestions from confirmed evidence')
    feedback = subs.add_parser('feedback')
    feedback.add_argument('id')
    feedback.add_argument('action', choices=['accepted', 'dismissed', 'deferred', 'seen', 'ignored', 'completed'])
    feedback.add_argument('--note', default='')
    for command in ['export', 'import']:
        p = subs.add_parser(command, help='Versioned graph JSON; not live SQLite synchronization')
        p.add_argument('file', type=Path)
    settings = subs.add_parser('settings', help='Recommendation frequency and backend availability')
    settings.add_argument('--daily-limit', type=int)
    settings.add_argument('--disable', action='store_true')
    settings.add_argument('--enable', action='store_true')


def read_json(path):
    if path.stat().st_size > 20*1024*1024:
        raise ValueError('JSON input exceeds 20 MiB')
    return json.loads(path.read_text(encoding='utf-8'))


def run(store, args):
    graph, library = Knowledge(store), Library(store)
    command = args.life_command
    if command == 'root':
        return library.configure(args.path)
    if command == 'scan':
        return library.scan(args.root_id)
    if command == 'resources':
        return [n for n in store.list('nodes') if args.search.casefold() in n['title'].casefold()]
    if command == 'add':
        return graph.node(Node(title=args.title, node_type=args.node_type, kind=args.kind, url=args.url, published=args.published,
                               measure=args.measure, total=args.total, provenance=[user_evidence(args.evidence)]))
    if command == 'inspect':
        node = store.get('nodes', args.id)
        return {'node': node, 'progress': graph.progress(args.id) if node['node_type'] != 'concept' else None, 'graph': graph.neighborhood(args.id)}
    if command == 'edit':
        data = payload(store.get('nodes', args.id))
        data['title'] = args.title
        return graph.correct_node(args.id, Node.model_validate(data))
    if command == 'progress':
        at = datetime.strptime(args.date, '%Y-%m-%d').replace(tzinfo=timezone.utc) if args.date else datetime.now(timezone.utc)
        return graph.activity(args.id, Activity(kind=args.kind, start=args.start, end=args.end, at=at, source=args.source, corrects=args.corrects))
    if command == 'react':
        return graph.activity(args.id, Activity(kind='reaction', reaction=args.reaction))
    if command == 'connect':
        members = []
        for text in args.member:
            parts = text.rsplit(':', 1)
            if len(parts) != 2:
                raise ValueError('Use NODE_ID:role for each member')
            members.append({'node_id': parts[0], 'role': parts[1]})
        return graph.edge(Edge(type=args.type, members=members, explanation=args.explanation, confidence=args.confidence, status=args.status, provenance=[user_evidence(args.evidence)]))
    if command == 'relationship':
        return graph.edge_status(args.id, args.status)
    if command == 'edge-json':
        return graph.edge(Edge.model_validate(read_json(args.file)))
    if command == 'merge-concepts':
        return graph.merge_concepts(args.source, args.target)
    if command == 'graph':
        return graph.neighborhood(args.focus, args.search)
    if command == 'recommendations':
        return Recommender(store).generate()
    if command == 'feedback':
        return Recommender(store).feedback(args.id, Feedback(action=args.action, note=args.note))
    if command == 'export':
        temp = args.file.with_suffix(args.file.suffix+'.tmp')
        temp.write_text(json.dumps(export_graph(store), indent=2), encoding='utf-8')
        temp.replace(args.file)
        return {'exported': str(args.file), 'version': 1}
    if command == 'import':
        return import_graph(store, read_json(args.file))
    if command == 'settings':
        value = graph.settings()
        if args.daily_limit is not None:
            value['daily_limit'] = args.daily_limit
        if args.disable or args.enable:
            value['recommendations_enabled'] = args.enable
        return {'settings': graph.settings(value), 'semantic': UnavailableEnricher().health(), 'reader': 'No reader adapter configured; manual updates are supported'}
    raise ValueError('Unknown Intellectual Life command')
