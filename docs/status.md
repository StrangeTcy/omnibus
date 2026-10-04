# Omnibus V0.2 — worker-loop handoff (2026-10-04)

## Truthful outcome

The existing runtime was extended, not replaced. Readiness, real-only smokes,
persisted turn/session metadata, SDK interruption, explicit continuation,
checkpoint/remote-turn reconciliation, retained workspaces, and one authorized
file task with an independent verifier are implemented and tested offline.

**No successful real model task is claimed.** This host has no authenticated
Codex session. Both read-only and writable real smoke attempts returned exit 1
and persisted `status: failed`, `error_kind: authentication`. The adapter used the
actual installed SDK/account API and never substituted MockWorker. Both opted-in
live integration tests failed for the same authentication reason.

See `v02-audit.md` for the pre-change defect inventory and inspected SDK contracts;
`limitations.md` for unresolved boundaries. The baseline suite was 21 passed,
1 skipped. All original credential-free tests still pass.

## Changed/new files relative to the V0.1 implementation

- `src/par/workers/codex_sdk.py`: real account readiness, safe typed failures,
  inspected turn/interrupt/read APIs, reconciliation, metadata, bounded write policy.
- `src/par/workers/base.py`: failure type and invocation execution/resume fields.
- `src/par/runtime.py`: authorization gate, stable task workspace, checkpoints,
  worker identity enforcement, continuation, cancellation tracking, artifact oracle.
- `src/par/db.py`: interrupted recovery error classification, preserving legacy data.
- `src/par/schemas.py`: explicit writable mode/authorization and fixed fixture type.
- **New** `src/par/local_task.py`: immutable sales fixture, bounded output capture,
  deterministic integer/schema/input-integrity verifier (no generated-code execution).
- **New** `src/par/smoke.py`: real-only readiness and reproducible live task functions.
- `src/par/cli.py`: worker-ready, smoke, resume, continue, safe Ctrl+C handling;
  visibly labeled mock demo, no fallback.
- `src/par/api.py`: readiness and conversation-continuation endpoints.
- `src/par/verification.py`: existing approved-command verifier follows retained
  workspace IDs on resumed attempts rather than assuming a new empty directory.
- `src/par/__init__.py`, `pyproject.toml`: version 0.2.0; SDK remains pinned at 0.160.0.
- **New** `tests/test_worker_loop.py`: offline SDK contract doubles and failure tests.
- `tests/test_codex.py`: explicit live opt-in now fails on auth errors, plus writable
  task/restart/thread-continuation integration test.
- `README.md`, `docs/status.md`, `docs/limitations.md`, `docs/decisions.md`,
  `docs/checklist.md`, **new** `docs/v02-audit.md`: commands, audit and evidence.

No architecture rewrite, new memory system, scheduler, multimodal route or
parallel orchestration. No credentials copied, no commits/pushes performed.
Existing files were untracked from the preceding implementation; Git therefore
shows the cumulative additions, not a separate V0.2 diff.

## Actual test commands and results

Environment: Linux, Python 3.11.2, openai-codex 0.160.0.

```sh
.venv/bin/python -m pip install -e ".[test]"
.venv/bin/python -m pytest -q -rs
```

**41 passed, 2 skipped, 1 warning** (repeated full-suite runs). Both skips are live tests not opted in.
The existing Starlette/httpx deprecation warning remains; no test failed.

Clean core-only wheel (no SDK installed):

```sh
.venv/bin/python -m pip wheel --no-deps -w /tmp/par-v02-wheels .
/tmp/par-core-env/bin/python -m pip install --no-deps --force-reinstall /tmp/par-v02-wheels/personal_agent_runtime-0.2.0-py3-none-any.whl
/tmp/par-core-env/bin/python -m pytest -q -rs
```

**40 passed, 3 skipped, 1 warning** (core-only wheel). Additional skip is optional SDK
signature checking. This separate environment and core dependencies were created
in V0.1; the newly built V0.2 wheel was installed and tested. Compilation with
`.venv/bin/python -m compileall -q src` also succeeded.

Explicitly enabled real tests:

```sh
PAR_LIVE_CODEX=1 .venv/bin/python -m pytest tests/test_codex.py -m live -q -rs
```

**2 failed, 2 deselected.** Both failures: `No authenticated Codex session; run
codex login on this host`. This is not relabeled as a passing mock test or a skip.

Actual CLI attempts (each exit 1):

```sh
.venv/bin/par worker-ready --worker codex
.venv/bin/par --data-root /tmp/par-v02-final smoke --worker codex
.venv/bin/par --data-root /tmp/par-v02-final smoke --worker codex --writable --authorize-workspace-write
```

Read-only failed run: `7e999bf1-09b7-4760-9baa-ea71809577ef`.
Writable failed run: `ead6d729-12d7-4dfc-9fe7-4089c8bb49f7`.
Both have authentication failure metadata, context artifacts and no fabricated
response/verification. Test data lives outside tracked source; it is not a
portable evidence archive and may not survive sandbox recreation.

## Lifecycle evidence and exact guarantees

| Case | Implemented and tested without live credentials | Live evidence |
|---|---|---|
| Completed task survives restart | Existing subprocess CLI persistence plus reopened Store/API; new SDK-double result/checkpoint metadata | Blocked by auth |
| Running cancellation | Runtime cancels real execution coroutine, adapter calls handle.interrupt, records acknowledgement/uncertainty, captures partial output | SDK cancellation not exercised with a model |
| Interrupted resume | Keeps workspace/files, starts a new attempt, retains old artifacts; completed-turn/result checkpoint is collected without new model execution | Blocked by auth |
| Conversation continuation | New request on persisted thread, read-only authorization; verifies same thread and new turn | Live test implemented; not reached here |
| Auth/provider/sandbox/timeout failures | Distinct error_kind; none marked successful; raw provider messages withheld | Actual auth failure observed |
| Retry/no overwrite | Explicit latest-attempt retry, original-worker check, bounded attempts; old artifacts immutable; unknown/active turns refuse replay | Exactly-once external side effects are NOT claimed |
| Writable artifact verification | Valid/missing/invalid/boolean-type/changed-input cases, symlink refusal, bounded capture; zero generated test code | Writable smoke failed before model invocation |

Offline tests use explicitly named FakeSdk/MockWorker fixtures. They exercise
public SDK-shaped contracts, not real provider/network behavior. Signature/enum
checks also run against the actually installed SDK. SDK config keys were checked
against the tagged upstream config schema linked in the audit.

## Exact manual setup on the authenticated host

Linux/macOS (from the checkout):

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[codex,test]"
.venv/bin/python -c "from codex_cli_bin import bundled_codex_path; import subprocess; raise SystemExit(subprocess.call([str(bundled_codex_path()), 'login']))"
.venv/bin/par worker-ready --worker codex
.venv/bin/par smoke --worker codex
.venv/bin/par smoke --worker codex --writable --authorize-workspace-write
PAR_LIVE_CODEX=1 .venv/bin/python -m pytest tests/test_codex.py -m live -q -rs
```

Official `codex login` is equivalent if the CLI is already on PATH. Login runs
locally with the official client. Do not provide credentials in chat. Use the
same OS user and CODEX_HOME for all commands. If configuration guard rejects
external tools/permissions, use a dedicated official Codex home and log in there;
do not copy auth files. No API key is required if the official client supports
your existing authenticated subscription.

Windows PowerShell (read-only; write sandbox is intentionally not enabled):

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[codex,test]"
.venv\Scripts\python.exe -c "from codex_cli_bin import bundled_codex_path; import subprocess; raise SystemExit(subprocess.call([str(bundled_codex_path()), 'login']))"
.venv\Scripts\par.exe worker-ready --worker codex
.venv\Scripts\par.exe smoke --worker codex
$env:PAR_LIVE_CODEX = "1"
.venv\Scripts\python.exe -m pytest tests/test_codex.py -m live -k "not writable" -q -rs
Remove-Item Env:PAR_LIVE_CODEX
```

With an activated environment, exercise continuation/recovery:

```sh
par continue COMPLETED_RUN_ID "What file did you produce? Do not use tools." --worker codex
# Start a smoke, Ctrl+C while running; then obtain its ID from par status:
par status
par resume INTERRUPTED_RUN_ID --worker codex --acknowledge-uncertainty
```

Stop any server before offline writes. If using `--data-root PATH`, include it
before the subcommand on every command. Use a root outside configured project
ancestors. The read-only smoke requires exact `OMNIBUS_READY`; the writable smoke
requires `status=completed`, `verification=passed`, a real thread/turn ID, and a
saved summary artifact. Model prose alone is not acceptance.

## Remaining blockers / best next action

The objective of a **successfully executed real task remains unproven** until
legitimate host authentication is available. Live sandbox containment,
interruption and restart/resume also remain untested. Windows writable support
is disabled, not faked. Backup excludes working directories and the external
Codex session store; missing state fails closed. Regex redaction is not universal
secret detection; do not submit credentials as user data.

**Next action:** run the above commands on the user's authenticated host, inspect
the immutable verification artifacts, and validate live cancellation/resume and
outside-workspace write denial before granting any broader capability.
