# V0.2 pre-change audit (2026-10-04)

Baseline: `python -m pytest -q`: **21 passed, 1 skipped**. Read adapter,
worker protocol, full execution loop, Store/migration, artifact store, CLI/API
startup/cancel/retry, verification, and all existing tests before edits.

## Verified SDK contract

Installed `openai-codex==0.160.0`, import `openai_codex`. Inspected public
AsyncCodex/AsyncThread/AsyncTurnHandle source, generated Thread/Turn/ThreadItem/
ThreadStartResponse/usage models, and `_sandbox`/turn-result collection code.

- `async with AsyncCodex()` launches app-server; `await account()` reuses official
  host authentication. PAR neither performs login nor transfers auth from Arena
  to another machine. An account existing does not prove model access/quota.
- Thread APIs: `thread_start`, `thread_resume(id, ...)`, `thread.read(include_turns=True)`.
  SDK thread history persists outside PAR in the configured Codex home. Thread
  contains session_id, model/provider (configured, not per-turn telemetry), turns.
  Turn contains id/status/times/items/error. Completed agentMessage items carry text.
- `thread.turn(input)` gives AsyncTurnHandle with id, `run`, `stream`, `interrupt`.
  `thread.run` hides this handle; merely closing the client is not an acknowledged
  interrupt. `handle.run()` raises on failed turns before returning a TurnResult.
- Sandbox enums: read_only, workspace_write, full_access. Approval enums: deny_all,
  auto_review. Defaults include auto_review, so PAR must explicitly deny escalation.
- Thread config accepts JSON overrides. Workspace-write mode includes cwd and
  configured additional roots; it is NOT full filesystem/read isolation. The turn
  `sandbox=` preset creates a fresh policy, so do not overwrite a carefully
  configured thread policy with a generic turn preset.
- Verified tagged configuration schema (not guessed keys):
  https://raw.githubusercontent.com/openai/codex/rust-v0.160.0/codex-rs/core/config.schema.json
  SandboxWorkspaceWrite has writable_roots, network_access, exclude_slash_tmp,
  exclude_tmpdir_env_var. By default temporary directories are not excluded.
  This is documented capability, not evidence the host sandbox works live.

## Defects/gaps recorded BEFORE modification

1. Default is mock (labeled, no adapter fallback). A configured real worker never
   falls back, but retry can silently switch workers after a config change.
2. Readiness lives in doctor only (doctor exits zero even without auth); live test
   skips missing auth even when explicitly requested. No failing reproducible
   real-only smoke command or deterministic live output verification.
3. Thread ID is saved before the model turn. Turn ID is not saved; result metadata
   discards actual usage/timing and checkpoints record only a counter.
4. Retry carries thread_id but creates an empty new per-run workspace. Completed
   local work is not carried forward. There is no completed-conversation follow-up
   command and no reconciliation of a remotely completed turn after a crash.
5. Cancellation changes SQLite, cancels only scheduled asyncio jobs, then closes
   SDK resources. It never invokes SDK interrupt or records its acknowledgement.
   Direct execute/CLI invocations are absent from jobs. Shutdown can cancel twice.
6. Recovery only marks queued/running attempts paused. No work is resumed until
   explicit retry; that is safe but does not prove actual SDK continuation.
7. Returned worker result is not durable until all output processing succeeds.
   A failure between completed model work and final persistence can repeat it.
8. Failures are generic strings. Authentication, provider failures, timeout and
   interruption are not machine-distinguishable. Raw SDK error text is passed
   through regex redaction rather than using safe allowlisted diagnostics.
9. Adapter's read-only policy explicitly prohibits file writes, has no output path
   collector or independent artifact verifier. It only supports answers/plans.
10. Inherited config guard checks only home config MCP/apps/hooks. It does not
    constrain extra writable roots/tmp/network or project configs for a writable
    task. SDK process launches from ambient cwd, not the disposable workspace.
11. Current tests prove mock lifecycle and SQLite persistence, not successful real
    execution, SDK interruption, thread reconciliation or sandbox enforcement.

Plan: preserve architecture; add typed failure/checkpoint/control metadata,
explicit real-only readiness/smokes and continuation, retain task workspace,
reconcile saved turns without blind replay, implement one authorized local JSON
summary fixture/verifier. Keep existing read-only/default-mock demonstration
behavior backward compatible, with explicit labeling; live commands reject mock.
