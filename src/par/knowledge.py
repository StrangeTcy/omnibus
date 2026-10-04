import json
from datetime import datetime, timezone
from .db import uid, now
from .knowledge_models import Node, Edge, Activity, Preference, Settings


def payload(obj):
    return {k: v for k, v in obj.items() if k not in {'id', 'created', 'parent_id', 'node_id'}}


def user_evidence(description):
    return {'kind': 'user', 'description': description}


def union_length(intervals):
    merged = []
    for a, b in sorted(intervals):
        if not merged or a > merged[-1][1]:
            merged.append([a, b])
        else:
            merged[-1][1] = max(merged[-1][1], b)
    return sum(b-a for a, b in merged)


class Knowledge:
    def __init__(self, store):
        self.store = store

    def node(self, data: Node, parent_id=None):
        with self.store.connect() as db:
            if parent_id:
                self.store.get('nodes', parent_id, db)
            if data.node_type == 'unit' and not parent_id:
                raise ValueError('A content unit requires a parent resource')
            if data.merged_into or data.status != 'active':
                raise ValueError('Use the concept merge operation, not a forged redirect')
            for p in data.provenance:
                if p.node_id:
                    self.store.get('nodes', p.node_id, db)
            obj = self.store.add('nodes', data.model_dump(mode='json'), db, parent_id=parent_id)
            self.store.event(obj['id'], 'knowledge_node_created', {'node_type': data.node_type}, db)
            return obj

    def correct_node(self, id, data: Node):
        with self.store.connect() as db:
            old = self.store.get('nodes', id, db)
            if any(data.model_dump()[k] != old[k] for k in ['node_type', 'measure', 'total', 'status', 'merged_into', 'locations', 'sha256', 'locator', 'ordinal']):
                raise ValueError('Identity/progress units are immutable; create a new version to change them')
            values = data.model_dump(mode='json')
            values['provenance'] += [user_evidence('User metadata correction')]
            Node.model_validate(values)
            for p in values['provenance']:
                if p.get('node_id'):
                    self.store.get('nodes', p['node_id'], db)
            self.store.event(id, 'knowledge_node_corrected', {'before': old, 'after': values}, db)
            return self.store.update('nodes', id, values, db)

    def edges(self):
        with self.store.connect() as db:
            result = self.store.list('edges')
            for e in result:
                e['members'] = [dict(r) for r in db.execute('SELECT node_id,role FROM edge_members WHERE edge_id=? ORDER BY node_id,role', (e['id'],))]
            return result

    def edge(self, edge: Edge):
        with self.store.connect() as db:
            nodes = {m.node_id: self.store.get('nodes', m.node_id, db) for m in edge.members}
            for p in edge.provenance:
                if p.node_id:
                    self.store.get('nodes', p.node_id, db)
            if edge.type == 'covers':
                if not any(m.role == 'source' and nodes[m.node_id]['node_type'] in {'resource', 'unit'} for m in edge.members):
                    raise ValueError('covers requires a source resource/unit')
                if not any(m.role == 'concept' and nodes[m.node_id]['node_type'] == 'concept' for m in edge.members):
                    raise ValueError('covers requires concept membership')
            if edge.supersedes:
                previous = self.store.get('edges', edge.supersedes, db)
                if previous['status'] == 'superseded':
                    raise ValueError('Correct the current edge version')
                self.store.update('edges', edge.supersedes, {'status': 'superseded'}, db)
            obj = self.store.add('edges', edge.model_dump(mode='json', exclude={'members'}), db)
            for m in edge.members:
                db.execute('INSERT INTO edge_members VALUES (?,?,?)', (obj['id'], m.node_id, m.role))
            self.store.event(obj['id'], 'hyperedge_created', {'supersedes': edge.supersedes}, db)
            return {**obj, 'members': [m.model_dump() for m in edge.members]}

    def edge_status(self, id, status):
        if status not in {'confirmed', 'rejected'}:
            raise ValueError('Choose confirmed or rejected')
        with self.store.connect() as db:
            edge = self.store.get('edges', id, db)
            if edge['status'] == 'superseded':
                raise ValueError('Correct the current edge version, not a superseded edge')
            if len(edge['provenance']) >= 100:
                raise ValueError('Provenance limit reached; create an explicit corrected version')
            self.store.event(id, 'hyperedge_user_decision', {'from': edge['status'], 'to': status}, db)
            return self.store.update('edges', id, {'status': status, 'provenance': edge['provenance']+[user_evidence('User '+status+' relationship')]}, db)

    def merge_concepts(self, source, target):
        with self.store.lock:
            a, b = (self.store.get('nodes', id) for id in [source, target])
            if source == target or any(n['node_type'] != 'concept' or n['status'] != 'active' for n in [a, b]):
                raise ValueError('Merge requires two distinct active concepts')
            aliases = list(dict.fromkeys(b['aliases']+[a['title']]+a['aliases']))
            if len(aliases) > 100:
                raise ValueError('Merged aliases would exceed 100; simplify aliases first')
            # Preserve old edges; revised memberships receive new edge IDs.
            for edge in self.edges():
                if edge['status'] == 'confirmed' and any(m['node_id'] == source for m in edge['members']):
                    members = {(target if m['node_id'] == source else m['node_id'], m['role']) for m in edge['members']}
                    if len({m[0] for m in members}) < 2:
                        self.edge_status(edge['id'], 'rejected')
                        continue
                    values = payload(edge)
                    values.update(supersedes=edge['id'], members=[{'node_id': n, 'role': r} for n, r in members], provenance=edge['provenance']+[user_evidence('Concept merge')])
                    self.edge(Edge.model_validate(values))
            self.store.update('nodes', target, {'aliases': aliases})
            self.store.update('nodes', source, {'status': 'superseded', 'merged_into': target})
            self.store.event(source, 'concept_merged', {'target': target})
            return self.store.get('nodes', target)

    def activity(self, node_id, event: Activity):
        with self.store.connect() as db:
            node = self.store.get('nodes', node_id, db)
            if node['node_type'] == 'concept':
                raise ValueError('Progress requires a resource or content unit')
            if event.kind != 'reaction':
                if event.end is None:
                    raise ValueError('Position required')
                ceiling = node['total'] if node['total'] is not None else (100 if node['measure'] == 'percent' else None)
                if ceiling is None or event.end > ceiling or (event.start is not None and event.start > event.end):
                    raise ValueError('Progress outside known bounds')
                if node['measure'] in {'pages', 'chapters'} and any(v is not None and not v.is_integer() for v in [event.start, event.end]):
                    raise ValueError('Pages/chapters require whole-number boundaries')
                if event.kind in {'reading', 'revisit'} and event.start is None:
                    raise ValueError('Reading requires start and end boundaries')
            if event.kind == 'reaction' and event.reaction is None:
                raise ValueError('Reaction required')
            if event.kind == 'correction':
                if not event.corrects:
                    raise ValueError('A correction must name an earlier event')
                previous = self.store.get('activity', event.corrects, db)
                if previous['node_id'] != node_id or previous['kind'] not in {'reading', 'revisit', 'position'}:
                    raise ValueError('Correction must target this resource progress, not another correction')
                if any(e.get('corrects') == event.corrects for e in self.store.list('activity')):
                    raise ValueError('Event already corrected; record a new position/read event')
            elif event.corrects:
                raise ValueError('Only correction events may name corrects')
            obj = self.store.add('activity', event.model_dump(mode='json'), db, node_id=node_id)
            self.store.event(node_id, 'activity_recorded', {'activity_id': obj['id'], 'kind': event.kind}, db)
            return obj

    def progress(self, node_id):
        node = self.store.get('nodes', node_id)
        events = [e for e in self.store.list('activity') if e['node_id'] == node_id]
        corrections = {e['corrects']: e for e in events if e['kind'] == 'correction'}
        effective = []
        for e in events:
            if e['kind'] in {'correction', 'reaction'}:
                continue
            if c := corrections.get(e['id']):
                # Attribute replacement reading to original date, not correction day.
                e = {**e, 'start': c['start'], 'end': c['end']}
                if e['start'] is None:
                    e['kind'] = 'position'
            effective.append(e)
        ranges, daily, position = [], {}, 0
        for e in sorted(effective, key=lambda e: (e['at'], e['created'])):
            position = e['end']
            if e['kind'] in {'reading', 'revisit'} and e['source'] != 'estimate':
                before = union_length(ranges)
                ranges.append((e['start'], e['end']))
                added = union_length(ranges)-before if e['kind'] == 'reading' else 0
                day = e['at'][:10]
                daily[day] = daily.get(day, 0)+added
        total = node['total'] or (100 if node['measure'] == 'percent' else None)
        return {'position': position, 'total': total, 'fraction': position/total if total else None,
                'measure': node['measure'], 'newly_read': sum(daily.values()),
                'daily': [{'date': d, 'amount': v} for d, v in sorted(daily.items())],
                'history': sorted(events, key=lambda e: (e['at'], e['created']))}

    def settings(self, change=None):
        with self.store.connect() as db:
            row = db.execute("SELECT data FROM knowledge_settings WHERE name='recommendations'").fetchone()
            value = Settings.model_validate(json.loads(row[0]) if row else {})
            if change is not None:
                value = Settings.model_validate(change)
                db.execute("INSERT INTO knowledge_settings VALUES ('recommendations',?) ON CONFLICT(name) DO UPDATE SET data=excluded.data", (value.model_dump_json(),))
            return value.model_dump()

    def preference(self, data: Preference):
        if data.origin == 'inferred' and data.confirmed:
            raise ValueError('Inferences require a separate explicit confirmation')
        return self.store.add('preferences', data.model_dump(mode='json'))

    def neighborhood(self, focus=None, query='', edge_type=None):
        nodes = self.store.list('nodes')
        edges = [e for e in self.edges() if e['status'] != 'superseded' and (not edge_type or e['type'] == edge_type)]
        selected = {focus} if focus else {n['id'] for n in nodes if query.lower() in n['title'].lower()}
        edges = [e for e in edges if any(m['node_id'] in selected for m in e['members'])][:60]
        selected |= {m['node_id'] for e in edges for m in e['members']}
        visible = [n for n in nodes if n['id'] in selected][:200]
        visible_ids = {n['id'] for n in visible}
        return {'nodes': visible, 'edges': [e for e in edges if all(m['node_id'] in visible_ids for m in e['members'])], 'bounded': True}
