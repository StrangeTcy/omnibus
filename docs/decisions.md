# Implementation decisions

- **Foundation first:** new package in an otherwise empty repository, preserving
  the supplied brief. No remote repository creation, commits, pushes, global
  software installation or edits to other repositories.
- **Stack:** Python/FastAPI/Uvicorn/Jinja2, light vanilla JS, Pydantic, sqlite3,
  platformdirs. `filelock` is the only additional runtime utility, for a portable
  single-authority lock. No frontend build step.
- **Schema:** explicit versioned SQL migration and `PRAGMA user_version`. Typed
  object envelopes live in JSON columns; relational identity/project/task/run
  references and dependency edges use SQLite foreign keys. UUID4 IDs; timezone-
  aware UTC timestamps. Event triggers prohibit UPDATE/DELETE. Writes use
  transactions, WAL and a process-local lock. Database and artifact integrity
  are checked on startup/import/read.
- **Ownership:** one server owns execution. Offline writers take the same lock.
  SQLite supports concurrent status reads, not multi-master synchronization.
- **Routing:** auto conservatively answers; intent modes are explicit. No
  speculative classifier or automatic elaborate plan. A simple task is one node;
  dependencies are optional and cycle checked, not auto scheduled.
- **Artifact consistency:** atomic temp-file replacement, generated names,
  immutable revisions. Backup locks the writer and takes an SQLite snapshot plus
  registered file content. CLI backup is offline for cross-process consistency.
  Import only into a fresh root avoids destructive replacement of user state.
- **Worker seam:** descriptor + typed invocation/result. Mock is a deterministic
  demonstration, not a substitute falsely labeled as a real model. Installed
  `openai-codex==0.160.0` was introspected (module is `openai_codex`, not `codex`).
  Async client, thread methods, enums, result fields and ExternalMessage signatures
  were inspected directly. SDK is pinned as an optional extra.
- **Permission trade-off:** Codex is read-only with deny-all escalation; no external
  write approval bridge exists. Configured MCP/apps/hooks are rejected. The
  adapter owns its internal sub-loop; PAR does not claim tool-by-tool auditing.
  Context is passed as SDK `ExternalMessage` with lower/tool-level authority.
- **Capabilities:** only executable `artifact.write` is advertised. Input/output
  schemas, side-effect class, permission scope, byte/time metadata and idempotency
  are explicit. Call and byte budgets are enforced; this bounded local synchronous
  operation has no preemptive disk-I/O timeout.
- **Verification:** subjective answers stay unverified. Operator-approved command
  verification is a distinct offline boundary, not an automatic model tool. It
  is not a security sandbox; results are limited to the selected command.
- **Recovery:** queued/running attempts become paused after process loss. Manual
  retry requires acknowledgement and remaining budget; a new run preserves old
  evidence. No automatic external effect replay.
- **Config:** CLI/environment configuration instead of a TOML loader, avoiding
  duplicate precedence mechanisms at this size. `config.example.env` is reference
  documentation, not an automatically loaded dotenv file.
- **Memory:** explicit records only; lexical/project-scoped retrieval. Corrections
  supersede old records with provenance. Forget erases the correction chain but
  does not rewrite immutable historical run snapshots or external backups.

## V0.2 amendments (supersede V0.1 worker/recovery statements above)

- Preserve the package/runtime/store boundaries. Add optional JSON fields with
  backward-compatible defaults, not a needless SQL migration for JSON payloads.
- Real-only readiness/smoke fail nonzero; opt-in integration tests fail on missing
  auth. Default mock remains labeled for compatibility, never a fallback.
- Use inspected public `thread.turn`/`handle.interrupt`/`thread.read` APIs. Persist
  thread, turn, session and allowlisted execution metadata, not raw notifications
  or provider errors that might contain credentials.
- Retain the task workspace under its first run ID. Retry is a new run, completed
  results are immutable checkpoints, and backend-completed turns are reconciled
  without a second model turn. Unknown or active turn state fails closed.
- Continuation is a new read-only request on the stored backend thread. It never
  inherits writable authorization. Retries require original worker identity.
- Limit authorized writing to the immutable sales fixture / JSON summary task.
  Use SDK workspace_write with deny_all, no extra roots/tmp/network, and no generic
  turn sandbox override (which would replace the configured thread policy).
  The built-in Python oracle checks saved bytes, not generated test code.
- Restrict writable mode to Linux/macOS pending Windows validation. This is
  documented SDK write confinement, not an observed live isolation guarantee.
