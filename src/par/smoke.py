"""Real-only reproducible commands. Account presence alone is not success."""
from .schemas import Submission, Budget
from .local_task import GOAL
from .workers.codex_sdk import health

async def readiness(worker):
    if worker != 'codex':
        return {'available': False, 'worker': worker, 'error_kind': 'configuration',
                'diagnostic': 'Real worker required; mock is explicitly configured, not a live fallback'}
    return await health()


async def smoke(runtime, *, writable=False, authorized=False):
    if runtime.worker.descriptor.id != 'codex':
        raise ValueError('Real smoke requires --worker codex or PAR_WORKER=codex; mock rejected')
    if writable and not authorized:
        raise ValueError('Writable smoke requires --authorize-workspace-write')
    submission = Submission(text=GOAL if writable else 'Reply exactly OMNIBUS_READY. Do not use tools.',
                            source='live-smoke', budget=Budget(seconds=180, retries=2),
                            execution_mode='workspace_write' if writable else 'read_only',
                            authorize_workspace_write=authorized if writable else False,
                            fixture='sales-summary' if writable else None)
    obj = runtime.accept(submission)
    # Deliberately invoke through the runtime even on missing auth, so failure is
    # a durable failed attempt, not just a readiness message or a skipped task.
    await runtime.execute(obj['run_id'])
    run = runtime.store.get('runs', obj['run_id'])
    if not writable and run['status'] == 'completed':
        import json
        passed = (run['response'] or '').strip() == 'OMNIBUS_READY'
        report = {'verification': 'passed' if passed else 'failed', 'check': 'Exact smoke response OMNIBUS_READY'}
        artifact = runtime.artifacts.write(json.dumps(report).encode(), kind='verification', mime='application/json', run_id=run['id'], provenance='smoke oracle v1')
        runtime.store.update('runs', run['id'], {'verification': report['verification'], 'result_artifacts': run['result_artifacts']+[artifact['id']]})
        runtime.store.update('tasks', run['task_id'], {'verification': report['verification']})
        runtime.store.event(run['id'], 'verification_result', report)
        run = runtime.store.get('runs', run['id'])
    return run
