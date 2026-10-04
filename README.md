# Personal Agent Runtime · PAR

A runnable, local-first **serial** personal-agent runtime. Own your requests,
projects, memory, artifacts and event history; swap the worker independently.
Python 3.11–3.13. No Docker, WSL, paid API key or model account is needed for the
mock-backed core.

**v0.2 status:** resumable worker-loop implementation, not an autonomous general-purpose agent.
The deterministic mock is clearly labeled. The optional Codex SDK adapter is
implemented against the installed 0.160.0 API, but read-only and writable live tasks both failed
here because no authenticated Codex session is available. No successful live
execution or sandbox validation is claimed. See [tested status](docs/status.md)
and [limitations](docs/limitations.md).

## Install and run

### Linux / macOS

From this repository:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[test]"
.venv/bin/par doctor
.venv/bin/par serve
```

### Windows 11 (PowerShell or cmd; no activation required)

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[test]"
.venv\Scripts\par.exe doctor
.venv\Scripts\par.exe serve
```

Open **http://127.0.0.1:8000**. The default worker is `MockWorker`.
Submit a request, inspect its run, and download its artifacts. Choose **Project**
to create a persistent project; add inventory items/notes, complete items
idempotently, pause/archive it, or attach follow-up tasks. Memory entries are
explicit, searchable, inspectable, correctable and forgettable.

The same commands below use `par` after activating the virtual environment,
or replace it with the executable path shown above. `python -m par` also works.

```sh
par --data-root .par-data run "How do I separate the white from the yolk?"
par --data-root .par-data run "Consume a music discography and commentary" --route project
par --data-root .par-data status
par --data-root .par-data serve --port 8000
```

Stop with Ctrl+C. Stop the server before using offline `run`, `verify`, backup
or import. A cross-platform lock prevents two authoritative runtime processes
on the same root. `status` and `doctor` may read while the server runs.

## Configuration

`--data-root PATH` overrides `PAR_DATA_ROOT`. Otherwise `platformdirs` chooses
the current user's OS-standard application data directory. `par doctor` prints
the resolved path, dependency versions, integrity/writability checks and Codex
availability without printing credentials.

Environment variables (see [config.example.env](config.example.env)):

| Name | Default | Meaning |
|---|---|---|
| `PAR_DATA_ROOT` | OS user-data directory | SQLite, artifacts, workspaces |
| `PAR_WORKER` | `mock` | `mock` or `codex`; no silent fallback |
| `PAR_ACCESS_TOKEN` | unset | At least 32 characters; required for non-loopback bind |
| `PAR_LIVE_CODEX` | unset | `1` enables the separate live integration test |

PowerShell uses `$env:PAR_WORKER = "codex"`; cmd uses `set PAR_WORKER=codex`;
POSIX shells use `export PAR_WORKER=codex`. No TOML configuration loader is
advertised; configuration is deliberately CLI/environment-only in v0.2.

## What the runtime actually does

1. Stores original request, task, attempt and attachments before worker invocation.
2. Auto uses the lightest answer route; explicit Task/Investigation/Project modes
   record the user's intent. Only an explicit Project selection creates a project.
3. Retrieves relevant, nonsensitive explicit memories and associated project
   state/text inventory. Records a redacted, provenance-bearing context artifact.
4. Executes one bounded worker turn serially. A disposable task workspace is
   retained across explicit retries; the initial run ID remains its directory name.
5. Records worker results, immutable artifacts, events and a checkpoint.
6. Marks subjective answers **unverified**, even when the run is **completed**.
   The authorized sales-summary task passes/fails a runtime-owned JSON oracle.
7. On restart pauses interrupted **and queued** attempts; does not replay them.
   Explicit retries create new runs and require an uncertainty acknowledgement
   plus a remaining retry budget (zero by default).

The Store dependency API rejects cycles and execution blocks on incomplete
prerequisites. There is no automatic DAG builder or dependency scheduling UI.
Resuming first reuses a durable result checkpoint or reconciles the saved Codex
turn. A remotely completed turn is collected without running it again; unknown
or still-running turns fail closed. No prose is interpreted as a capability invocation. The executable registry
currently contains `artifact.write`, which the runtime really uses for context
and response artifacts. SDK internal operations are not routed through it.

## V0.2: real-worker readiness, smoke, resume and bounded file task

Install the pinned SDK **on the host that will actually run Omnibus**:

```sh
python -m pip install -e ".[codex,test]"
```

Authenticate with the official Codex CLI on that same host:

```sh
codex login
```

If `codex` is not on PATH, the installed SDK includes its official CLI binary.
This portable command uses the package's inspected `bundled_codex_path()` helper:

```sh
python -c "from codex_cli_bin import bundled_codex_path; import subprocess; raise SystemExit(subprocess.call([str(bundled_codex_path()), 'login']))"
```

Use the same OS user and `CODEX_HOME` for login, readiness, execution and resume.
Do not paste credentials into Omnibus or copy your local authentication into Arena.
No auth files are read/copied by PAR. The default demo configuration is still
**explicitly labeled mock**; the commands below explicitly select Codex. A real
worker never falls back, and retries reject a worker identity change.

Stop the server before these offline commands. Use the same `--data-root PATH`
(if you specify one) on **every** command, otherwise OS-standard storage is used.
A writable data root must be outside any ancestor project `.codex/config.toml`.

```sh
par worker-ready --worker codex
par smoke --worker codex
par status
```

Readiness checks the installed SDK/configuration and official account API; it
exits **1** if unavailable. Account presence is **not** proof of model access.
The smoke actually calls the model, persists response/thread/turn/session,
configured model/provider, timing and usage when supplied, and verifies the exact
response `OMNIBUS_READY`. It exits nonzero on auth/provider/verification failure.
Provider errors use fixed safe diagnostics, not raw SDK messages. There is no
mock fallback. `PAR_WORKER=codex` can replace the explicit `--worker` flags.

### A useful writable task (Linux/macOS only)

```sh
par smoke --worker codex --writable --authorize-workspace-write
```

This explicitly authorizes a **single sales-summary fixture**. Omnibus stores an
immutable `input.json` fixture and puts a copy in a disposable task workspace.
The model must create `summary.json`; Omnibus captures the file and independently
checks exact integer totals/schema against the immutable original. Expected:

```json
{"total_units": 5, "total_cents": 1975}
```

A missing file, invalid JSON, wrong totals/types, or altered input fails the task
with `verification: failed`; model prose cannot pass this check. No generated
code or shell command is executed by the verifier. Prior artifact versions remain.

**Boundary:** read-only remains the default. Only this explicitly authorized
fixture can request SDK `workspace_write`; `full_access`/auto-review are never
used. We configure no additional roots, exclude `/tmp`/`TMPDIR`, disable tool
network access/web search, deny approval escalation and strip inherited tool-shell
environment. External MCP/apps/hooks/plugins/permission overrides are refused.
The SDK, not PAR, enforces the OS write sandbox. It is **not filesystem read
isolation, a VM, or a disk quota**; official SDK runtime state/authentication is
outside the task workspace. Successful live sandbox enforcement has **not** been
observed here. Windows writable mode fails closed pending platform validation;
Windows can use the read-only real smoke. No unrestricted fallback exists.

### Continue or resume without replaying completed work

Use the `id` returned by smoke, or inspect `par status` after interruption:

```sh
par continue RUN_ID "What did you just do? Do not use tools." --worker codex
par resume INTERRUPTED_RUN_ID --worker codex --acknowledge-uncertainty
```

`continue` creates a new request/task on the saved SDK thread and is **read-only**,
including after a writable task. `resume` creates a new attempt of the latest
failed/paused/cancelled task, keeping workspace, immutable artifacts and thread.
The smoke budget permits two explicit retries. A completed remote turn or saved
worker-result checkpoint is collected, not executed again. If verification failed,
an explicit retry allows the model to repair the invalid local output. Only the
fixed idempotent summary operation is writable; no generic external effects are
supported. Existing partial work is not reset.

Cancel from the UI/API while a server owns the run, or press Ctrl+C during an
offline command. The adapter requests `AsyncTurnHandle.interrupt()` and records
acknowledged/uncertain status; acknowledgement is **not** proof of rollback or
termination. Restart marks stale runs paused. Unknown/active backend turns are
not blindly replayed; inspect/stop them with the official Codex client first.
If a workspace or the external Codex thread store was lost, resume fails rather
than silently reconstructing an empty session. See [audit](docs/v02-audit.md).

### Separately invoked authenticated tests

These commands can consume model quota and, when enabled, authorize the fixed
writable task. Default tests never invoke a real model.

```sh
# POSIX, Linux/macOS
PAR_LIVE_CODEX=1 python -m pytest tests/test_codex.py -m live -q -rs
```

```powershell
# PowerShell: read-only live test (Windows writable mode is not enabled)
$env:PAR_LIVE_CODEX = "1"
python -m pytest tests/test_codex.py -m live -k "not writable" -q -rs
Remove-Item Env:PAR_LIVE_CODEX
```

Opted-in missing authentication is a **test failure**, not a skip or completion.
Here, both opted-in tests failed with `No authenticated Codex session; run codex
login on this host`. Offline SDK contract doubles test interruption, continuation,
reconciliation and failure paths; they do not establish live model behavior.

Images/PDFs remain retained but blocked on this adapter. No multimodal, scheduler,
parallel execution or new memory subsystem is introduced in V0.2.

## Explicit command verification

The mock-backed acceptance suite creates a disposable Git workspace, makes a
reversible change, saves a diff and runs an explicitly selected unittest command.
It never commits or pushes. This fixture does **not** mean the normal mock can
perform arbitrary coding tasks.

For a completed run with a reviewed local workspace:

```sh
par verify --approve --seconds 30 RUN_ID python -m unittest
```

Options must precede `RUN_ID`; the remaining arguments are the exact command.
**This command executes with your OS permissions, not in an OS sandbox.** Review
all code first. Approval is mandatory and never inferred from model text. A
zero exit code records `passed`; nonzero exit/timeout records `failed`, with a
bounded-output report artifact. This verifies only the selected command, not
all claims. Windows process-tree termination has limitations.

## Backup / restore

Stop the service first. Destination must be outside the data root:

```sh
par --data-root .par-data backup par-backup.zip
par --data-root .par-data export par-export.zip
par --data-root restored-data import par-backup.zip
par --data-root restored-data status
par --data-root restored-data serve
```

`backup` and `export` are aliases. The archive contains an SQLite backup snapshot,
a version manifest, and all registered artifacts with SHA-256/size metadata.
Import rejects traversal/symlink/duplicate entries and oversized archives,
checks SQLite integrity/foreign keys and artifact hashes, and requires a **new or
empty** data root. Never merge a live database. Original workspaces, Codex's
external thread store/login, and arbitrary unregistered files are not included.
Treat archives as private, trusted local data; they are not encrypted.

## HTTP API

Core endpoints: `GET /api/state`, `POST /api/requests`, `POST /api/upload`,
`GET /api/runs/{id}`, `POST /api/runs/{id}/cancel`,
`POST /api/runs/{id}/retry?acknowledge_uncertainty=true`,
`POST /api/runs/{id}/continue` (JSON `{"text":"..."}`),
`GET /api/worker/readiness` (503 when unavailable),
`PATCH /api/projects/{id}`, `GET/POST /api/memories`,
`PUT/DELETE /api/memories/{id}`, `GET /api/artifacts/{id}`.

Clients first GET `/api/session` and send its `csrf` value in `X-PAR-CSRF` for
mutations. Cross-origin mutations are rejected. Example using Python/httpx:

```python
import httpx
with httpx.Client(base_url="http://127.0.0.1:8000") as client:
    client.headers["X-PAR-CSRF"] = client.get("/api/session").json()["csrf"]
    response = client.post("/api/requests", json={
        "text": "Plan my reading", "route": "task",
        "budget": {"seconds": 60, "turns": 1, "tool_calls": 4, "retries": 1}
    })
    response.raise_for_status()
    print(response.json())
```

## Security boundary

- Loopback-only by default, with Host and same-origin/CSRF checks. No CORS grants.
- Explicit remote bind requires a strong `PAR_ACCESS_TOKEN`. API clients use
  `Authorization: Bearer ...`; the browser has a token login page and HttpOnly,
  SameSite=Strict cookie. TLS is **not** provided: use a trusted TLS reverse proxy
  or private tunnel. Do not expose plain HTTP on the public internet.
- Generated file names, bounded payloads, download-only artifacts, escaped UI
  output, checked paths, and atomic file replacement.
- No publishing, purchasing, messages, installs, secret access or arbitrary
  commands are available through the default runtime capability registry.
- Redaction covers common labeled secrets/token patterns in events, context and
  responses. It is not a universal secret detector. Original requests/uploads
  are intentionally preserved locally: **do not put credentials in them**.
- Forget removes memory records and their correction chain, not historical
  snapshots, original requests, SQLite remnants or previously exported backups.
- No automatic retry after a potentially ambiguous effect. Cancellation prevents
  later PAR steps; it cannot undo actions already performed by another process.

## Tests

```sh
python -m pytest -q
python -m pytest tests/test_runtime.py tests/test_api_cli.py -q
python -m pip wheel --no-deps --wheel-dir wheelhouse .
```

The default tests require no credentials. Live tests skip only when not opted in;
when explicitly enabled, missing authentication fails. CI is configured for Ubuntu, Windows and macOS with Python
3.11–3.13; those remote CI runs have **not** been observed in this session.

## Troubleshooting

- **No authenticated Codex session:** log in via official Codex on this host;
  check `CODEX_HOME` matches your intended session; run `par doctor` again.
- **SDK missing:** install the optional `[codex]` extra. The core remains usable.
- **Data root in use:** use the existing web/API server, or stop it before offline
  run/backup/verification. Never launch multiple writers manually.
- **Paused after restart:** inspect the saved checkpoint/error before explicit
  retry. No queued task is automatically resumed.
- **Retry budget exhausted:** create a new explicit request; prior runs remain.
- **Blocked image/PDF:** the attachment is retained. Use text input for now.
- **Unverified result:** normal for subjective responses. A worker's confidence
  is not independent verification.

See [decisions](docs/decisions.md), [limitations](docs/limitations.md), and
[implementation evidence](docs/status.md).
