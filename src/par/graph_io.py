"""Validated version-1 JSON interchange. No filesystem paths are activated."""
import json
from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import Field
from .schemas import Payload
from .knowledge import Knowledge, payload
from .knowledge_models import Node, Edge, Activity, Preference, Settings

class Identity(Payload):
    id: UUID
    created: datetime

class NodeRecord(Node, Identity):
    parent_id: UUID | None = None
class EdgeRecord(Edge, Identity):
    pass
class ActivityRecord(Activity, Identity):
    node_id: UUID
class PreferenceRecord(Preference, Identity):
    pass
class RecommendationRecord(Identity):
    candidate_id: UUID
    reason: str = Field(max_length=5000)
    edge_ids: list[UUID]
    activity_ids: list[UUID]
    overlap_concepts: list[UUID]
    additional_concepts: list[UUID]
    score: float = Field(allow_inf_nan=False)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    effort: float | None = None
    basis: str
    status: Literal['proposed', 'seen', 'accepted', 'dismissed', 'deferred', 'completed', 'expired']
    feedback: list[dict] = Field(max_length=1000)
    ignored: int = Field(ge=0)
    defer_until: str | None = None

class GraphDocument(Payload):
    format: Literal['omnibus-idea-graph'] = 'omnibus-idea-graph'
    version: Literal[1] = 1
    nodes: list[NodeRecord] = Field(max_length=10000)
    edges: list[EdgeRecord] = Field(max_length=10000)
    activity: list[ActivityRecord] = Field(max_length=50000)
    preferences: list[PreferenceRecord] = Field(max_length=10000)
    recommendations: list[RecommendationRecord] = Field(max_length=10000)
    settings: Settings

MODELS = {'nodes': NodeRecord, 'edges': EdgeRecord, 'activity': ActivityRecord,
          'preferences': PreferenceRecord, 'recommendations': RecommendationRecord}


def export_graph(store):
    with store.lock:
        graph = Knowledge(store)
        doc = {table: graph.edges() if table == 'edges' else store.list(table) for table in MODELS}
        return GraphDocument(**doc, settings=graph.settings()).model_dump(mode='json')


def import_graph(store, raw):
    if len(json.dumps(raw).encode()) > 20*1024*1024:
        raise ValueError('Graph import exceeds 20 MiB')
    doc = GraphDocument.model_validate(raw).model_dump(mode='json')
    # All validation/conflict detection before any durable change.
    maps = {}
    for table in MODELS:
        ids = [r['id'] for r in doc[table]]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate IDs in '+table)
        maps[table] = {r['id']: r for r in doc[table]}
    nodes = maps['nodes']
    for n in nodes.values():
        if n['parent_id'] and n['parent_id'] not in nodes:
            raise ValueError('Missing parent node')
        seen, parent = {n['id']}, n['parent_id']
        while parent:
            if parent in seen:
                raise ValueError('Parent cycle')
            seen.add(parent)
            parent = nodes[parent]['parent_id']
        if n['node_type'] == 'unit' and not n['parent_id']:
            raise ValueError('Content unit requires parent')
        if n['merged_into'] and n['merged_into'] not in nodes:
            raise ValueError('Missing merged concept')
    for records in (doc['nodes'], doc['edges'], doc['preferences']):
        for r in records:
            for p in r['provenance']:
                if p['node_id'] and p['node_id'] not in nodes:
                    raise ValueError('Unknown evidence node')
    for e in doc['edges']:
        if any(m['node_id'] not in nodes for m in e['members']):
            raise ValueError('Unknown hyperedge member')
        if e['supersedes'] and e['supersedes'] not in maps['edges']:
            raise ValueError('Missing superseded edge')
        if e['type'] == 'covers' and not (any(m['role'] == 'source' and nodes[m['node_id']]['node_type'] in {'resource', 'unit'} for m in e['members']) and any(m['role'] == 'concept' and nodes[m['node_id']]['node_type'] == 'concept' for m in e['members'])):
            raise ValueError('Invalid covers roles')
    corrected = set()
    for a in doc['activity']:
        if a['node_id'] not in nodes:
            raise ValueError('Unknown activity node')
        node = nodes[a['node_id']]
        if a['kind'] != 'reaction':
            total = node['total'] or (100 if node['measure'] == 'percent' else None)
            if a['end'] is None or total is None or a['end'] > total or (a['start'] is not None and a['start'] > a['end']):
                raise ValueError('Invalid activity bounds')
            if node['node_type'] == 'concept' or (node['measure'] in {'pages', 'chapters'} and any(v is not None and not float(v).is_integer() for v in [a['start'], a['end']])):
                raise ValueError('Invalid progress measurement')
            if a['kind'] in {'reading', 'revisit'} and a['start'] is None:
                raise ValueError('Missing interval start')
        if a['kind'] == 'reaction' and a['reaction'] is None:
            raise ValueError('Missing reaction')
        if a['corrects']:
            old = maps['activity'].get(a['corrects'])
            if not old or old['node_id'] != a['node_id'] or old['kind'] not in {'reading', 'position', 'revisit'} or a['kind'] != 'correction' or a['corrects'] in corrected:
                raise ValueError('Invalid/duplicate activity correction')
            corrected.add(a['corrects'])
        elif a['kind'] == 'correction':
            raise ValueError('Correction without target')
    for p in doc['preferences']:
        if p['origin'] == 'inferred' and p['confirmed']:
            raise ValueError('Inferred preference cannot claim confirmation')
    for r in doc['recommendations']:
        if r['candidate_id'] not in nodes or any(id not in maps['edges'] for id in r['edge_ids']) or any(id not in maps['activity'] for id in r['activity_ids']) or any(id not in nodes for id in r['overlap_concepts']+r['additional_concepts']):
            raise ValueError('Recommendation has invalid evidence references')
    with store.connect() as db:
        conflicts, inserts = [], {}
        existing = export_graph(store)
        for table, model in MODELS.items():
            present = {r['id']: r for r in existing[table]}
            inserts[table] = []
            for r in doc[table]:
                if r['id'] in present:
                    if r != present[r['id']]:
                        conflicts.append(f'{table}:{r["id"]}')
                else:
                    inserts[table].append(r)
        if conflicts:
            raise ValueError('Conflicting IDs; no changes imported: '+', '.join(conflicts[:20]))
        # Parent references are deferred only during this checked transaction.
        db.execute('PRAGMA defer_foreign_keys=ON')
        for table in MODELS:
            for r in inserts[table]:
                data = dict(r)
                members = data.pop('members', []) if table == 'edges' else []
                cols = ['id', 'created', 'data']
                values = [r['id'], r['created'], json.dumps(data)]
                if table in {'nodes', 'activity'}:
                    ref = 'parent_id' if table == 'nodes' else 'node_id'
                    cols.append(ref)
                    values.append(r[ref])
                db.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})", values)
                for m in members:
                    db.execute('INSERT INTO edge_members VALUES (?,?,?)', (r['id'], m['node_id'], m['role']))
        # Settings are portable but cannot activate scanning or a backend.
        db.execute("INSERT INTO knowledge_settings VALUES ('recommendations',?) ON CONFLICT(name) DO UPDATE SET data=excluded.data", (json.dumps(doc['settings']),))
        store.event('intellectual-life', 'graph_imported', {t: len(v) for t, v in inserts.items()}, db)
    return {t: len(v) for t, v in inserts.items()}
