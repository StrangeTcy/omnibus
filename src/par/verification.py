"""Explicit operator-selected verification, never commands from worker prose.

Commands run with host-user permissions. Approval is mandatory; this is not an
OS sandbox. Do not approve tests from untrusted generated code without review.
"""
import asyncio
import json
import os
import signal
import time
from .security import redact, inside

async def verify(runtime, run_id, argv, *, approved=False, seconds=30):
    if not approved or not argv or not 0 < seconds <= 120:
        raise ValueError('Explicit command approval and bounded timeout required')
    run = runtime.store.get('runs', run_id)
    if run['status'] != 'completed':
        raise ValueError('Only a completed worker result can be verified')
    workspace = inside(runtime.store.root / 'workspaces', run.get('workspace_id', run_id))
    if not workspace.is_dir():
        raise ValueError('Run workspace unavailable (workspaces are not restored from backup)')
    runtime.store.event(run_id, 'approval_requested', {'action': 'verification command', 'approved_by': 'local CLI operator', 'argv': argv})
    started = time.monotonic()
    kwargs = {'start_new_session': True} if os.name != 'nt' else {}
    # Output is drained concurrently and capped; no unbounded pipe/file growth.
    process = await asyncio.create_subprocess_exec(*argv, cwd=workspace, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, **kwargs)
    captured = bytearray()
    async def drain():
        while chunk := await process.stdout.read(4096):
            if len(captured) < 100000:
                captured.extend(chunk[:100000-len(captured)])
    reader = asyncio.create_task(drain())
    timed_out = False
    try:
        async with asyncio.timeout(seconds):
            await process.wait()
            await reader
    except (TimeoutError, asyncio.CancelledError) as exc:
        timed_out = True
        if os.name != 'nt':
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif process.returncode is None:
            process.kill()
        await process.wait()
        reader.cancel()
        await asyncio.gather(reader, return_exceptions=True)
        if isinstance(exc, asyncio.CancelledError):
            runtime.store.event(run_id, 'verification_result', {'state': 'unverified', 'reason': 'Cancelled; subprocess tree termination is best effort on Windows'})
            raise
    state = 'passed' if process.returncode == 0 and not timed_out else 'failed'
    report = {'argv': argv, 'exit_code': process.returncode, 'timeout': timed_out, 'elapsed_seconds': time.monotonic()-started,
              'verification': state, 'output': redact(captured.decode(errors='replace')),
              'scope': 'Only this operator-selected command; not proof of overall correctness'}
    artifact = runtime.artifacts.write(redact(json.dumps(report, indent=2)).encode(), kind='verification', run_id=run_id, provenance='operator-approved local test command')
    with runtime.store.connect() as db:
        runtime.store.update('runs', run_id, {'verification': state, 'result_artifacts': run['result_artifacts']+[artifact['id']]}, db)
        runtime.store.update('tasks', run['task_id'], {'verification': state}, db)
        runtime.store.update('artifacts', artifact['id'], {'verification': state}, db)
        runtime.store.event(run_id, 'verification_result', {'state': state, 'exit_code': process.returncode, 'report': artifact['id']}, db)
    return report
