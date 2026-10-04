"""One bounded task: turn an immutable sales fixture into a JSON summary.

The oracle reads registered fixture/artifact bytes, never worker-modifiable test
code. No generated code or shell is executed by this verifier.
"""
import json
from .security import inside, redact

FIXTURE = b'{"sales":[{"item":"tea","units":2,"unit_cents":350},{"item":"coffee","units":3,"unit_cents":425}]}\n'
GOAL = ('Read input.json in the designated workspace. Create summary.json containing '
        'exactly {"total_units": integer, "total_cents": integer}, summing units and '
        'units * unit_cents across sales. Do not modify input.json. Only create or '
        'replace summary.json. No installs, network, commits or other side effects. '
        'If summary.json already contains the correct result, leave it unchanged. '
        'Finish with a concise description; your prose is not verification.')


def prepare(runtime, task, run_id, workspace):
    if not task.get('fixture_artifact'):
        artifact = runtime.artifacts.write(FIXTURE, kind='fixture', mime='application/json', provenance=task['id'], run_id=run_id)
        runtime.store.update('tasks', task['id'], {'fixture_artifact': artifact['id']})
        data = FIXTURE
    else:
        data = runtime.artifacts.read(task['fixture_artifact'])
    path = inside(workspace, 'input.json')
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError('Fixture changed; refusing to overwrite completed work')
    else:
        path.write_bytes(data)


def verify_summary(fixture: bytes, output: bytes | None):
    expected_source = json.loads(fixture)
    expected = {'total_units': sum(r['units'] for r in expected_source['sales']),
                'total_cents': sum(r['units'] * r['unit_cents'] for r in expected_source['sales'])}
    if output is None:
        return {'verification': 'failed', 'reason': 'summary.json missing', 'expected': expected}
    try:
        value = json.loads(output)
        valid = isinstance(value, dict) and value.keys() == expected.keys() and all(type(value[k]) is int and value[k] == v for k, v in expected.items())
    except (ValueError, UnicodeError, KeyError, TypeError):
        valid = False
    return {'verification': 'passed' if valid else 'failed', 'reason': 'Independent exact integer totals/schema check' if valid else 'Invalid summary schema or totals', 'expected': expected}


def capture(runtime, run_id, workspace):
    """Capture even an interrupted output, but never follow symlinks or huge files."""
    if (workspace / 'summary.json').is_symlink():
        raise ValueError('summary.json must not be a symlink')
    path = inside(workspace, 'summary.json')
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
        raise ValueError('summary.json must be a regular file of at most 4096 bytes')
    artifact = runtime.artifacts.write(redact(path.read_bytes().decode('utf-8', errors='replace')).encode(), kind='workspace-output', mime='application/json', run_id=run_id, provenance=run_id)
    runtime.store.update('runs', run_id, {'workspace_output': artifact['id']})
    return artifact['id']


def verify_run(runtime, run_id):
    run = runtime.store.get('runs', run_id)
    task = runtime.store.get('tasks', run['task_id'])
    output_id = run.get('workspace_output')
    fixture = runtime.artifacts.read(task['fixture_artifact'])
    report = verify_summary(fixture, runtime.artifacts.read(output_id) if output_id else None)
    workspace = inside(runtime.store.root / 'workspaces', run.get('workspace_id', run_id))
    try:
        unchanged = inside(workspace, 'input.json').read_bytes() == fixture
    except (OSError, ValueError):
        unchanged = False
    if not unchanged:
        report.update(verification='failed', reason='Worker modified or removed the immutable fixture')
    artifact = runtime.artifacts.write(json.dumps(report).encode(), kind='verification', mime='application/json', run_id=run_id, provenance='sales-summary oracle v1')
    runtime.store.event(run_id, 'verification_result', {**report, 'report': artifact['id']})
    runtime.store.update('artifacts', artifact['id'], {'verification': report['verification']})
    if output_id:
        runtime.store.update('artifacts', output_id, {'verification': report['verification']})
    return report, artifact['id']
