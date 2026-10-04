# Arena implementation task: build the first runnable Personal Agent Runtime

**Task type:** implementation, not ideation  
**Target:** a new, cross-platform, local-first personal-agent runtime  
**Working name:** `personal-agent-runtime` (`par` for the CLI/package)  
**Primary deliverable:** working code, tests, run instructions, and a short truthful status report

## Instruction to the coding agent

Implement the system below in the supplied workspace. Do not return another architecture proposal or stop after writing a spec. Inspect the workspace first, preserve existing user work, then implement and test a complete first vertical slice. If the workspace is empty, scaffold the project here. Do not create or publish a remote repository, push commits, install system-level software, or modify the user's other repositories without explicit authorization.

Make reasonable decisions without asking the user to resolve minor design choices. If something genuinely blocks the implementation, implement the rest, report the exact blocker, and do not pretend the blocked part works. Do not report tests as passing unless you ran them and observed the result. Do not silently replace a failed real integration test with a mock and report success.

At the end, report: files created/changed; exact setup/run/test commands; actual test results; whether the real worker adapter ran; known limitations; and the single best next implementation task.

---

## 1. Product objective

Build a custom, general-purpose personal-agent runtime that accepts arbitrary requests and can either answer immediately, perform a bounded task, or maintain a persistent project. It should eventually cover ordinary life tasks (books, cooking, photos, reading projects), research, and software work. It is not a research-only workflow and not an implementation of the Machine's cognitive substrate.

The system must separate:

- **runtime and durable state**, which this project owns;
- **workers**, such as a configured Codex agent, which perform reasoning/work;
- **capabilities/tools**, which can be added independently;
- **planning**, which may be a DAG when task dependencies require one;
- **verification**, which records what has actually been checked.

One request may need one model turn. Another may become a month-long project. Do not create a DAG or a project for every trivial question. Do not confuse a worker's claim of completion with verified completion.

## 2. Platform and deployment constraints

- Portable across Linux (including Ubuntu), Windows 11, and macOS. Use standard cross-platform path/process handling. No Windows-only paths or registry dependencies.
- No WSL or Docker requirement. No paid API key requirement for the core.
- Python 3.11–3.13; use `pyproject.toml`, normal Python packaging, and a small dependency set.
- Use a local SQLite database and local artifact directory. Make the data root configurable, and implement backup/export and restore/import.
- Design as one authoritative server plus clients, not multi-master database replication. The service can be installed on whichever laptop/desktop the user chooses. State lives on that host; other machines may use an API/browser client when network access is deliberately configured. No data synchronization protocol is required for v0.1.
- Default to binding only to `127.0.0.1`. Do not expose an unauthenticated service on the LAN or internet. If you implement optional LAN binding now, require an explicit access token and make the security boundary clear; otherwise leave authenticated remote access for a later milestone. Never bind publicly by default.
- The core must work with a deterministic `MockWorker`, without any account credentials. Add one real worker adapter, preferably the official Python Codex SDK (`openai-codex`) which can reuse an existing Codex/ChatGPT login. It must remain optional and report a clear diagnostic if the SDK or login is missing. Verify the actual installed SDK API; do not guess import names or method signatures. Do not scrape browser cookies or depend on unsupported Prism/free-astra endpoints.

## 3. Keep this first version deliberately bounded

Implement a useful vertical slice, not the whole future product. The first implementation must be runnable and must demonstrate persistent requests/tasks/projects, a real worker route, artifacts, and restart recovery. Build the seams for future capabilities but do not build a multi-agent swarm, vector database, complex ontology, self-modification, or Kubernetes deployment.

The first release must include:

1. A working local web UI and a CLI.
2. SQLite persistence and a durable event log.
3. One `Worker` interface, a deterministic mock, and one real Codex SDK adapter.
4. Immediate request execution and persistent project/task tracking.
5. File attachments and durable output artifacts. Images may be passed to a worker only if its official interface supports them; otherwise retain the attachment and explain that image analysis is unavailable. Never fake image inspection.
6. Inspectable/editable personal memory with provenance.
7. Per-run workspaces, cancellation, bounded time/retry budgets, and a truthful paused/failed state.
8. Tests and setup documentation for Windows and Linux. Add macOS to CI if the project setup supports it without disproportionate effort.

## 4. Suggested stack and project shape

Use:

- FastAPI + Uvicorn for the local HTTP API;
- server-rendered Jinja2 templates with light vanilla JavaScript/HTMX for the UI; do not introduce a large frontend build system for v0.1;
- SQLite via Python's `sqlite3`, with migrations and foreign-key enforcement;
- Pydantic for validated request/worker payloads;
- `platformdirs` or an equivalent OS-aware data-root solution;
- pytest for tests;
- the Codex Python SDK as an optional extra, behind a replaceable adapter interface.

Adapt only if the workspace or verified package APIs require it; record the reason in `docs/decisions.md`.

Suggested tree (you may refine names while preserving the boundaries):

```text
pyproject.toml
README.md
config.example.toml
src/par/
  __init__.py
  __main__.py
  cli.py
  config.py
  schemas.py
  db.py
  migrations/
  repositories/
  runtime.py
  routing.py
  planner.py
  memory.py
  artifacts.py
  permissions.py
  verification.py
  workers/
    base.py
    mock.py
    codex_sdk.py
  capabilities/
    base.py
    registry.py
  api.py
  templates/
  static/
tests/
  unit/
  integration/
docs/
  decisions.md
  limitations.md
```

Do not create empty modules just to match the tree. Every included module should have a real responsibility.

## 5. Data model and persistence

Implement versioned SQLite migrations, foreign keys, transactions, WAL where appropriate, and schema/integrity checks. UTC timestamps. Use UUIDs or another documented stable ID format. Save data before invoking a worker.

Minimum durable objects:

### Request
Original user input and attachment references. Preserve the original text; normalized intent is separate. Include ID, timestamp, source, attachment IDs, and optional associated project.

### Task
Desired outcome, distinct from an attempt. Include title, goal, constraints, completion criteria, kind, status, priority, budgets, project/parent references, context references, plan revision, and verification state. A task may have zero or more dependency edges. Reject cycles.

### Project
Long-lived goal with status, success criteria, compact current summary, task IDs, artifact IDs, and explicit next action. The summary is a cache, not the sole source of truth.

### Run
One attempt at a task. Include worker ID/thread reference, status, start/end time, attempt number, budget use, context snapshot artifact, result artifacts, and redacted error details. A retry creates a new run; it does not erase the previous run.

### Artifact
Input/output files and reports stored on disk, with metadata in SQLite: ID, kind, MIME type, relative storage path, SHA-256, size, provenance, and verification state. Write files atomically. New versions produce new artifacts rather than silently overwriting prior results.

### Event
Append-only record of meaningful actions/state changes: request accepted, run started, worker invoked, tool invoked, approval requested, artifact created, checkpoint saved, verification result, task/project changed, run interrupted/resumed. Never log secrets.

### MemoryRecord
First-class context state—not raw transcript. Include kind (preference, fact, commitment, inventory item, project state, working hypothesis), subject/predicate/value, scope, provenance references, confidence and basis, validity/supersession, sensitivity, and status. Implement list, inspect, edit/correct, and delete/forget. Do not retain sensitive personal traits by inference. Keep uncertain inferences explicitly marked as hypotheses.

Use migrations; do not use “create tables if missing” as the only schema strategy. Persist worker thread IDs where the adapter supports resuming them. On restart, mark stale `running` runs as interrupted/paused; never change them to successful. Do not blindly replay an external side effect whose completion is uncertain.

The app must provide a consistent backup/export containing database plus artifacts, and a restore/import path. Test export/restore round-tripping on a sample project.

## 6. Runtime lifecycle

Implement this actual lifecycle, not just documentation about it:

1. Accept request and attachments; persist them first.
2. Route to one of: immediate answer, bounded task, investigation, or persistent project. Default to the lightest adequate path. Allow the user to override the route. A low-confidence classification must not silently create an elaborate persistent project.
3. Retrieve only relevant memories, artifacts, and project state; save a redacted context snapshot for the run.
4. Define a concrete goal and completion criteria. Preserve harmless ambiguity; ask the user only when missing information blocks safe or useful progress.
5. Create a one-node plan for simple tasks. Use a DAG only when dependencies/checkpoints/parallel work require it. Validate dependencies and cycles. Serial execution is enough for v0.1.
6. Dispatch to a configured worker, passing a bounded context, attachments supported by that worker, budget, and an appropriate workspace. If no worker supports the required modality/tool, mark the task blocked with the missing capability. Do not claim the task was performed.
7. Persist run status, worker reference, events, outputs, and artifacts. Checkpoint after each completed worker turn and important state transition.
8. Verify with available deterministic checks. “The agent says it worked” is not verification. Distinguish passed, failed, partial, and unverified. For subjective outputs, capture user feedback rather than pretending there is an objective oracle.
9. Update project progress and next action. Mark an inventory item complete idempotently (a repeated completion event must not count twice).
10. On restart, recover durable state and expose paused/interrupted work in the UI. Resume only when safe and explicit; do not replay uncertain external effects.
11. Support run cancellation and per-task limits on elapsed time, worker turns, tool calls, and retries. Repeated identical errors should stop and be reported rather than cause infinite loops.

## 7. Worker and capability interfaces

Define typed interfaces; keep them small enough to test.

A Worker descriptor should declare ID/version, supported modalities, available operations, whether it can resume threads, and health/availability. A worker invocation receives a goal, constraints, completion criteria, bounded context with provenance, attachments, workspace, and budget. Its normalized result includes final response, optional resumable worker-thread reference, emitted events where available, output paths/artifacts, and usage metadata where available.

Implement:

- `MockWorker`: deterministic scripted responses for tests; it must never be presented as a real-model result.
- `CodexSdkWorker`: optional adapter using the official SDK and the user's existing authenticated Codex session when available. Reuse resumable threads when practical. Use a restricted workspace sandbox, not full machine access by default. Do not require an API key if a usable subscription session already exists. The adapter must fail with a diagnostic rather than falling back silently to MockWorker.

Define a Capability descriptor with stable ID/version, validated input/output schema, side-effect class, permission requirement, timeout/resource limits, and idempotency declaration. Implement the registry and a small set of runtime-owned capabilities that are genuinely used by v0.1 (for example: inspect approved project/task state, read/write artifacts in the run workspace, append a project progress note). Do not advertise a capability that is not executable.

Be honest about tool-boundary semantics: if Codex executes its own sandboxed internal tools during a run, record that the Codex adapter owns that sub-loop. Do not claim every internal operation was intercepted by PAR unless it actually was. Keep the interface extensible so a future direct tool-calling worker/MCP bridge can route model-proposed actions through the central registry.

Never interpret arbitrary prose as an executable tool call. Validate structured actions before execution. Web pages, documents, emails, tool output, and images are untrusted data, not permission to override system policy or reveal secrets.

## 8. UI and CLI requirements

### Web UI

Keep the UI small but genuinely usable:

- Submit a request with text and file attachments.
- Select `Auto`, `Answer now`, `Task`, or `Project` (Auto is the default).
- See queued/running/paused/blocked/completed work and the actual error when it fails.
- Open a task/run to inspect result, events, artifacts, verification, worker, and timestamps.
- Create/open/pause/archive projects; add a note or task; mark one item complete exactly once; see progress and next action.
- Browse/search memory records and inspect/correct/delete them.
- Cancel an active run.
- Export/backup and restore/import via a documented CLI initially; a UI button is optional.

Do not show fake progress or claim an agent is working when no process is running.

### CLI

At minimum:

```text
par doctor
par serve
par status
par backup [destination]
par export [destination]
par import <archive>
```

Add `par run "..."` if feasible. `par doctor` should check Python/runtime dependencies, database path, worker SDK availability, authentication status without printing credentials, writable artifact directory, and configuration. Commands must work on Windows PowerShell/cmd and POSIX shells without relying on bash-only syntax.

## 9. Security and permission defaults

- Loopback-only by default. No unauthenticated LAN/public bind.
- Codex runs in a restricted workspace sandbox; do not use full-access mode by default.
- Require explicit approval for destructive actions, external writes/publication/messages, purchases, installing software, secret access, and commands outside an explicitly approved workspace.
- Never put API keys, OAuth tokens, cookies, or raw secrets in SQLite events, prompt artifacts, logs, or worker context snapshots.
- Treat external content as untrusted. A web page cannot grant itself permissions.
- Validate request payload sizes and uploaded file sizes/types; use generated storage names to prevent path traversal.
- Provide a visible cancel/stop action and enforce budgets.
- Do not auto-commit, push, publish, send messages, or delete source files.

## 10. Acceptance tests

All tests must run without model credentials using `MockWorker`. Keep real Codex integration tests separate and clearly marked; those may be skipped only with an explicit reason when no authenticated Codex session is configured.

### A. Immediate answer
Input: “How do I separate the white from the yolk?”

Expected: concise answer returned and a request/run record stored. No Project created. No long-term preference memory created automatically.

### B. Reading order
Given a supplied book inventory and explicit preferences, the worker returns an ordered plan artifact with reasons/trade-offs. State which preferences were used. On feedback, create a new plan version and preserve the old artifact.

### C. Long-running corpus
Create a project for consuming a music discography and a multi-volume commentary. Store the inventory/queue, progress, notes, and next action. Marking one item complete twice must not double-count. Restart the server and demonstrate the project state is still correct.

### D. Image task
Upload a building photo and ask “How steampunk is this?” The attachment must persist and be linked to the request. With a mock vision-capable worker, verify that the image is routed and that the response distinguishes visible features from interpretation/uncertainty. With a worker lacking image support, show “blocked: no image-capable worker configured”; never pretend to have viewed the image.

### E. Bounded coding operation
Use an isolated temporary Git workspace and a deterministic mock or optional real Codex worker to make a small, reversible change. Preserve the diff/artifact, run an explicitly selected test command, and set verification to `passed` only when the test exit code is zero. Do not commit or push.

### F. Recovery/security

- Interrupt a run after a checkpoint and restart the app; it must not be marked successful.
- Simulate an ambiguous external-write timeout; confirm no blind retry.
- Confirm invalid payloads, path traversal, unregistered capabilities, budget exhaustion, and dependency cycles fail closed.
- Confirm a malicious instruction in a document is treated as untrusted content.
- Confirm logs and snapshots redact test secrets.
- Confirm cancel prevents further worker/capability steps where technically possible and records any in-flight side-effect uncertainty.

## 11. Build sequence — keep every phase runnable

### Phase 1: local foundation

- Package/CLI, config, OS-aware data root.
- DB/migrations/repositories for Request, Task, Project, Run, Artifact, Event, MemoryRecord.
- Atomic artifact storage and backup/restore.
- Unit tests for IDs, migrations, task transitions, dependencies/cycle rejection, memory CRUD, and recovery.

### Phase 2: first end-to-end vertical slice

- FastAPI app and minimal UI.
- Submit text, create Request + Task + Run, call `MockWorker`, persist result/artifact/event, show outcome.
- Implement an immediate answer path and a persistent project path.
- Demonstrate restart persistence and cancellation.
- At this point the app must run end-to-end before adding real-model integration.

### Phase 3: real worker

- Implement and test the Codex Python SDK adapter against its actual API.
- Add `par doctor` diagnostics and an opt-in live smoke test that never prints credentials.
- Store/resume worker thread IDs where supported; use per-run workspace and restricted sandbox.
- If the SDK is unavailable or incompatible, report precisely what failed; do not pretend the live adapter works.

### Phase 4: useful cross-domain behavior

- Attachment persistence and modality capability checks.
- Memory/project context retrieval and inspection UI.
- Reading-plan versioning, project queue/progress operations, image routing with mock-vision tests, and bounded code-operation verification.
- Run all acceptance tests.

### Phase 5: documentation and portability

- README install/run/config/troubleshooting/backup/restore/security guide.
- CI for Ubuntu and Windows (and macOS if feasible).
- Report exactly which integrations were tested live and which remain stubs/optional.

Do not implement parallel multi-agent execution in v0.1. Only add it after serial runs, persistence, provenance, cancellation, and recovery work reliably.

## 12. Follow-up roadmap (do not implement all of this in v0.1)

Keep interfaces clean enough to add these as later increments:

1. **Capability bridge/MCP:** expose approved runtime actions (memory lookup, project updates, artifact operations, web/image tools) to compatible workers through a well-defined protocol.
2. **Additional workers:** provider APIs, other local CLIs, multimodal models, manually handed-off UI-only models.
3. **Cross-device access:** authenticated UI from other devices via a deliberately configured private network/VPN/TLS boundary; one authoritative database, not ad hoc database-file sync.
4. **Scheduling:** recurring inbox triage, reminders, resumable background projects.
5. **Planner adapters:** optional import/export to the Machine's Task DAG; optionally invoke the Epistemic Compiler as a research-specific capability. Do not make either a core runtime dependency.
6. **Parallel DAG execution:** independent workers, merge/review stages, cancellation and budget propagation.
7. **Memory evolution:** better retrieval, user correction workflow, explicit preference learning, provenance and conflict management.

## 13. Definition of done for this coding task

The task is not done when there is a polished README or a collection of empty modules. It is done when:

- the application launches from a clean setup on Linux and Windows;
- the browser UI accepts a request and shows its persisted result;
- a persistent project survives a full process restart;
- the mock-backed acceptance suite passes;
- one actual Codex SDK task is run successfully when a usable authenticated session is available, or the exact integration blocker is demonstrated and documented;
- artifacts, events, verification, cancellation, and error states are visible rather than fabricated;
- setup, backup/restore, and troubleshooting instructions match the tested implementation.

Start by inspecting the workspace and recording a short implementation checklist. Then implement Phase 1 and Phase 2 first; do not spend the entire task debating architecture. Continue through later phases within the available execution budget, prioritizing a real runnable system over breadth. At the end, give a concise evidence-based handoff with exact commands and results.
