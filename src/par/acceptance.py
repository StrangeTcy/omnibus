"""Observed acceptance stages, not a single misleading 'available' flag."""
from .db import now

STAGES = ('browser_reachable', 'provider_session', 'submission_attempted',
          'response_captured', 'semantic_validated', 'proposals_reviewed',
          'recommendation_generated', 'recommendation_rendered')


def record(store, run_id, stage, detail, status='observed', db=None):
    if stage not in STAGES:
        raise ValueError('Unknown acceptance stage')
    if db is None:
        with store.connect() as conn:
            return record(store, run_id, stage, detail, status, conn)
    run = store.get('runs', run_id, db)
    stages = run.get('acceptance', {})
    old = stages.get(stage, {})
    if old.get('detail') == detail and old.get('status') == status:
        return
    entry = {'at': now(), 'status': status, 'detail': detail}
    store.update('runs', run_id, {'acceptance': {**stages, stage: entry}}, db)
    store.event(run_id, 'acceptance_'+stage, entry, db)


def sync_reviews(store, edges):
    by_id = {e['id']: e for e in edges}
    replacements = {e['supersedes']: e for e in edges if e.get('supersedes')}
    for run in store.list('runs'):
        review = run.get('worker_metadata', {}).get('semantic')
        if not review:
            continue
        resolved = []
        for id in review['edge_ids']:
            e, seen = by_id.get(id), set()
            while e and e['status'] == 'superseded' and e['id'] not in seen:
                seen.add(e['id'])
                e = replacements.get(e['id'])
            if e:
                resolved.append(e)
        if resolved and len(resolved) == len(review['edge_ids']) and all(e['status'] in {'confirmed', 'rejected'} for e in resolved):
            record(store, run['id'], 'proposals_reviewed', {'edges': {e['id']: e['status'] for e in resolved}})
        elif not review['edge_ids']:
            record(store, run['id'], 'proposals_reviewed', {'reason': 'No proposals returned'}, 'not_applicable')
        elif any(e['status'] in {'confirmed', 'rejected'} for e in resolved):
            record(store, run['id'], 'proposals_reviewed', {'edges': {e['id']: e['status'] for e in resolved}, 'reason': 'Only reviewed edges may support recommendations; finish remaining review in graph inspector'}, 'partial')
        elif run.get('acceptance', {}).get('proposals_reviewed', {}).get('status') in {'observed', 'partial'}:
            record(store, run['id'], 'proposals_reviewed', {'reason': 'Current corrected proposal still needs review'}, 'pending')
