# V0.2 limitations and security boundary

## Not live-proven in this environment

No authenticated Codex account is available. Both real smoke attempts recorded
`failed / authentication`; both explicitly enabled live tests failed. No model
response, live writable task, real SDK interruption, real conversation recall,
or OS sandbox enforcement was successfully exercised here. Offline doubles
establish the PAR protocol logic, not provider behavior. See `status.md` for exact
results and README for same-host login and reproduction commands.

## Deliberately narrow functionality

- Default execution remains read-only. A write authorization enables only the
  built-in sales-summary task on Linux/macOS, not a general code-execution agent.
  Windows writable execution fails closed pending platform-specific validation.
- SDK workspace-write policy confines **tool writes**, not reads, to the supplied
  workspace (with tmp/extra roots excluded). It is not a VM, secret-isolation
  boundary, or disk quota. The trusted SDK keeps its own state outside this root.
  PAR does not intercept every internal SDK tool invocation. No full-access or
  approval escalation fallback is permitted.
- Config preflight rejects known external tools/plugins/hooks/permissions and
  ancestor project configs in writable mode. This is not an exhaustive audit of
  administrator-managed Codex/OS policy. Use a trusted dedicated official Codex
  home/account and least-privilege OS user. Never store credentials in a workspace.
- Shell-tool environment inheritance is disabled; models may need OS-provided
  commands or apply_patch. Provider/sandbox incompatibility fails, not escalates.
- The independent verifier checks the captured JSON and unchanged input, not all
  possible filesystem effects. It never executes model-generated code. The older
  `par verify --approve` command still runs reviewed host code and is a separate,
  explicitly operator-approved boundary, not the live fixture verifier.

## Recovery semantics

- A thread ID is not its transcript. The Codex home/session store must remain on
  the host. PAR stores thread/session/turn identifiers and immutable local evidence.
- Retry reuses the task's disposable workspace. Output files may be replaced only
  by an explicitly retried idempotent summary operation; old artifact versions
  remain. A completed backend turn or local result checkpoint is not rerun.
- Persisted turn status is reconciled before retry. Active/missing/ambiguous turns
  block rather than auto replay. If a crash occurs between backend turn creation
  and ID persistence, operator inspection may be required. This is not an exactly-
  once distributed transaction guarantee.
- SDK interruption acknowledgement is only an acknowledgement. Network/process
  loss can leave work uncertain. Cancellation records uncertainty, prevents later
  PAR steps, and retains bounded partial output; it cannot undo external effects.
- Backup remains database + registered artifacts, not workspaces or Codex's own
  session/auth store. Restoring a backup does not promise writable-task resume;
  missing workspaces fail closed. Same-host process restart is supported/tested
  offline. Interrupted files not yet captured can survive only in that workspace.
- Generic tasks still default to zero retries; live smoke tasks allow two. There
  is no automatic retry, scheduling, multi-agent execution or general DAG engine.

## Other V0.1 limitations retained

- Explicit mock is still the credential-free demo default, visibly labeled. It is
  never selected as a fallback. Real-only readiness/smoke reject mock; run/resume/
  continuation enforce the stored worker identity.
- Image/PDF processing is not wired; files persist and tasks block. Memory is
  explicit, lexical/project-scoped, not a new learning system.
- Secret redaction is bounded pattern matching. Actual auth data is never read,
  copied or emitted by PAR; raw provider diagnostics are withheld. Original user
  requests/uploads are preserved, so never submit credentials. Memory deletion
  does not erase old snapshots, SQLite remnants or backups. Storage is unencrypted.
- UI displays existing run metadata/events/artifacts but has no new dedicated
  writable authorization/continuation wizard; use the documented CLI/API.
- Only Linux Python 3.11 tests and a clean wheel installation were observed here.
  Windows/macOS and Python 3.12/3.13 CI is configured, not observed. No browser
  visual audit was performed. The Starlette/httpx deprecation warning remains.
- Network access is loopback by default; remote token access still requires an
  externally managed private/TLS boundary. No public unauthenticated deployment.

**Next task:** run the documented live smokes with a legitimately authenticated
same-host Codex account, then exercise live interrupt/restart/resume and validate
actual sandbox denial outside the disposable workspace before expanding scope.
