"""Sparse, deterministic policy over confirmed graph assertions, not title guesses."""
from datetime import datetime, timedelta, timezone
from .db import now
from .knowledge import Knowledge, user_evidence
from .knowledge_models import Feedback

class Recommender:
    def __init__(self, store):
        self.store, self.graph = store, Knowledge(store)

    def generate(self):
        settings = self.graph.settings()
        if not settings['recommendations_enabled'] or not settings['daily_limit']:
            return []
        nodes = {n['id']: n for n in self.store.list('nodes') if n['status'] == 'active'}
        edges = [e for e in self.graph.edges() if e['status'] == 'confirmed' and e['confidence'] >= .6 and (not e.get('valid_from') or e['valid_from'] <= now()[:10]) and (not e.get('valid_until') or e['valid_until'] >= now()[:10]) and all(m['node_id'] in nodes for m in e['members'])]
        activity = self.store.list('activity')
        resources = {id: n for id, n in nodes.items() if n['node_type'] == 'resource'}
        # Current content units are selected by actual progress, never file opening.
        current, consumed, triggers = set(), set(), {}
        for id, n in nodes.items():
            if n['node_type'] not in {'resource', 'unit'}:
                continue
            p = self.graph.progress(id)
            relevant = [e for e in p['history'] if e['kind'] in {'reading', 'position', 'correction'}]
            if relevant:
                current.add(id)
                triggers[id] = relevant[-1]['id']
                if p['fraction'] == 1:
                    consumed.add(id)
            if n['node_type'] == 'unit' and n['parent_id'] in resources:
                parent = resources[n['parent_id']]
                if parent['measure'] in {'pages', 'chapters'}:
                    pp = self.graph.progress(parent['id'])
                    if pp['history'] and n['ordinal'] and n['ordinal'] <= pp['position']:
                        consumed.add(id)
                    if pp['history'] and n['ordinal'] == pp['position']:
                        current.add(id)
                        triggers[id] = pp['history'][-1]['id']
        # Only confirmed covers edges count, and only already consumed source units
        # support the claim that the user has encountered those concepts.
        covered, coverage, concept_edges, resource_sources = set(), {}, {}, {}
        for e in edges:
            if e['type'] != 'covers':
                continue
            concepts = {m['node_id'] for m in e['members'] if m['role'] == 'concept' and nodes[m['node_id']]['node_type'] == 'concept'}
            for m in e['members']:
                if m['role'] == 'source':
                    source = m['node_id']
                    resource = nodes[source]['parent_id'] if nodes[source]['node_type'] == 'unit' else source
                    resource_sources.setdefault(resource, set()).add(source)
                    coverage.setdefault(resource, set()).update(concepts)
                    concept_edges.setdefault(resource, set()).add(e['id'])
                    if source in consumed:
                        covered.update(concepts)
        candidates = {}
        def add(id, reason, supporting, concept_ids=(), extra=(), trigger_ids=(), score=1):
            if id not in resources or id in consumed:
                return
            candidates[id] = {'candidate_id': id, 'reason': reason, 'edge_ids': sorted(set(supporting)),
                              'activity_ids': sorted(set(trigger_ids)), 'overlap_concepts': sorted(concept_ids),
                              'additional_concepts': sorted(extra), 'score': score,
                              'confidence': min([e['confidence'] for e in edges if e['id'] in supporting] or [.6]),
                              'effort': resources[id]['metadata'].get('attention_minutes'),
                              'basis': 'deterministic policy over confirmed assertions; not independently verified semantic equivalence'}
        consumed_edges = {e['id'] for e in edges if e['type'] == 'covers' and any(m['role'] == 'source' and m['node_id'] in consumed for m in e['members'])}
        for resource, concepts in coverage.items():
            if resource_sources[resource] <= consumed:
                continue
            overlap = covered & concepts
            novel = concepts-covered
            if overlap:
                add(resource, 'This resource covers concepts in material you marked completed. '+('Additional concepts are represented in the graph.' if novel else 'No additional concepts are represented in the analyzed evidence; this does not establish that the whole resource adds nothing.'), concept_edges[resource] | consumed_edges,
                    overlap, novel, [e['id'] for e in activity if e['node_id'] in consumed], score=2 if novel else .5)
        # Contextual cross-domain path: current section --covers--> motif
        # and recording --illustrates--> the same motif.
        for e in edges:
            if e['type'] != 'illustrates':
                continue
            recordings = {nodes[m['node_id']]['parent_id'] if nodes[m['node_id']]['node_type'] == 'unit' else m['node_id'] for m in e['members'] if m['role'] in {'resource', 'example'}}
            motifs = {m['node_id'] for m in e['members'] if m['role'] in {'concept', 'motif'}}
            for cover in edges:
                sources = {m['node_id'] for m in cover['members'] if m['role'] == 'source'}
                concepts = {m['node_id'] for m in cover['members'] if m['role'] == 'concept'}
                if cover['type'] == 'covers' and sources & current and concepts & motifs:
                    for recording in recordings:
                        if recording in resources and resources[recording]['url']:
                            add(recording, 'A concept at your current reading position is illustrated by this linked resource.', [e['id'], cover['id']], trigger_ids=[triggers[n] for n in sources & current], score=3)
        # Positive reaction is explicit; one ignore never becomes a dislike.
        latest_reactions = {}
        for a in sorted(activity, key=lambda a: (a['at'], a['created'])):
            if a['kind'] == 'reaction':
                latest_reactions[a['node_id']] = a
        guest_edges = [e for e in edges if e['type'] == 'features_person']
        for id, reaction in latest_reactions.items():
            if reaction['reaction'] != 'like' or id not in resources:
                continue
            for old in guest_edges:
                if not any(m['node_id'] == id and m['role'] == 'resource' for m in old['members']):
                    continue
                people = {m['node_id'] for m in old['members'] if m['role'] == 'person'}
                for new in guest_edges:
                    if people & {m['node_id'] for m in new['members'] if m['role'] == 'person'}:
                        for m in new['members']:
                            target = resources.get(m['node_id']) if m['role'] == 'resource' else None
                            if target and target['url'] and target['published'] and resources[id]['published'] and target['published'] > resources[id]['published']:
                                add(target['id'], 'You liked an interview with this guest. This linked interview has a newer supplied publication date; topic overlap has not been established.', [old['id'], new['id']], trigger_ids=[reaction['id']], score=2.5)
        existing = self.store.list('recommendations')
        today = now()[:10]
        visible = []
        for id, candidate in sorted(candidates.items(), key=lambda x: (-x[1]['score'], x[0])):
            if len(visible) >= settings['daily_limit']:
                break
            if latest_reactions.get(id, {}).get('reaction') == 'dislike':
                continue
            old = next((r for r in existing if r['candidate_id'] == id), None)
            if old:
                if old['status'] in {'dismissed', 'completed', 'accepted'}:
                    continue
                if old['status'] == 'deferred' and (old.get('defer_until') or '') > now():
                    continue
                candidate['score'] -= .1 * min(old.get('ignored', 0), 3)
                row = self.store.update('recommendations', old['id'], candidate)
            else:
                # Persisted daily cap, not a fresh feed every refresh/restart.
                if sum(r['created'][:10] == today for r in existing) >= settings['daily_limit']:
                    continue
                row = self.store.add('recommendations', {**candidate, 'status': 'proposed', 'feedback': [], 'ignored': 0, 'defer_until': None})
                existing.append(row)
            visible.append(row)
        return sorted(visible, key=lambda r: -r['score'])[:settings['daily_limit']]

    def feedback(self, id, feedback: Feedback):
        with self.store.connect() as db:
            old = self.store.get('recommendations', id, db)
            changes = {'feedback': old['feedback']+[{'at': now(), **feedback.model_dump()}]}
            if feedback.action == 'ignored':
                changes['ignored'] = old.get('ignored', 0)+1
            else:
                changes['status'] = feedback.action
            if feedback.action == 'deferred':
                changes['defer_until'] = (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
            if feedback.action in {'accepted', 'dismissed'}:
                self.store.add('preferences', {'scope': old['candidate_id'], 'statement': 'Recommendation '+feedback.action+'; not a general topic preference', 'origin': 'explicit', 'confirmed': True, 'confidence': 1, 'provenance': [user_evidence('Explicit recommendation feedback '+id)]}, db)
            self.store.event(id, 'recommendation_feedback', feedback.model_dump(), db)
            return self.store.update('recommendations', id, changes, db)
