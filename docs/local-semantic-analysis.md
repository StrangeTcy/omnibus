> **Backend correction:** browser website accounts are the intended primary integration;
> Ollama is optional, not required. See [browser-accounts.md](browser-accounts.md).
> The source-validation pipeline below is now shared by both transports. New jobs
> identify as `semantic-analysis`; existing `ollama-semantic` history is preserved.

# Local semantic analysis — implemented path, live acceptance still blocked

**2026-10-04:** the executable Ollama path is implemented. The earlier manual
hypergraph milestone did **not** fulfill the intended intelligent assistant.
This increment is not a claim that all three requested examples now work.

## What this increment does

Select accessible book units and/or supplied transcript segments → snapshot their
actual text → call an installed local model → validate structured concepts and
verbatim source quotations → atomically persist proposed concept/coverage or
illustration hyperedges → inspect and confirm/reject proposals → generate existing
progress-based, evidence-linked recommendations. You do **not** have to author the
concepts or connect every edge yourself.

The model considers selected sources together, so it can assign one concept to
differently worded passages. No hardcoded book titles, embedding similarity, fake
worker, or paid-provider fallback is used. Same concepts from **separate analysis
batches are not yet automatically reconciled**; analyze the passages together.

## Setup on your own host

Install Ollama separately using its official instructions, then explicitly install
an appropriate local model. Omnibus never installs/pulls a model for you. For example,
`ollama pull qwen2.5:3b` is a possible small-model starting point, **not a tested
quality or hardware recommendation from this environment**. Larger local models
may improve inference quality but require more memory. Use local weights, not a
cloud tag; configure the daemon with `OLLAMA_NO_CLOUD=1` as an additional guard.

Ollama and Omnibus must run on the same host. Calling `localhost` in an Arena
server does not reach Ollama on your laptop. Endpoints are restricted to loopback,
redirects/environment proxies disabled, and advertised remote/cloud routes refused.
A deliberately reconfigured local proxy remains outside this application's trust
boundary. There is no paid API configuration or automatic fallback.

In `/life`, use **Semantic analysis**:
1. Configure the exact installed model tag and loopback endpoint; check readiness.
2. Scan a local book root or paste actual transcript/text. URLs are stored, never fetched.
3. Select up to six content units, authorize local inference, and Analyze.
4. Refresh analysis status. Tasks, errors, output artifacts, source snapshots and
   model/digest/token metadata are durable in the existing runtime journal.
5. Inspect quoted evidence and scope. Confirm/reject generated proposals as a batch,
   or correct individual relations in the graph inspector. A batch with individually
   changed edges must be finished through the graph inspector.
6. Record actual reading progress on the analyzed unit. Confirmed model-generated
   coverage now participates in overlap/additional-material suggestions. Proposed
   or rejected edges never silently become trusted recommendation evidence.

The task-runtime `PAR_WORKER` setting is separate: semantic jobs always identify
as `ollama-semantic`, even if ordinary runtime tasks use the default mock worker.
The mock worker cannot perform semantic jobs.

### CLI (stop the server first; the existing data-root lock applies)

```sh
par life model --model qwen2.5:3b --check
par life import-text lecture.txt --title 'Supplied lecture transcript'
par life resources
# Use actual unit IDs from resources, not these placeholder strings:
par life analyze UNIT_ID_A UNIT_ID_B --authorize-local-inference
par life analyses
par life review-analysis RUN_ID confirmed
par life progress UNIT_ID_A --start 0 --end 100
par life recommendations
```

Configure-only: omit `--check`. Disable: `par life model --disable`.
Failed analysis is returned as a persisted failed/paused run with a diagnostic,
not a mocked result. Analyze and explicit readiness-check commands exit 1 on failure. No automatic retries occur. A failed job can be resubmitted
explicitly; no unattended scan-time inference runs.

### API

All mutations use existing access-token/CSRF protection.

- `PUT /api/life/semantic/config`: `{backend:"ollama", model:"exact:tag", endpoint:"http://127.0.0.1:11434", seconds:180}`
- `POST /api/life/semantic/health`: readiness only, no generation.
- `POST /api/life/semantic/text`: `{title, text, url?}`.
- `POST /api/life/semantic/analyze`: `{source_ids:[...], authorize_local_inference:true}`; returns run/task IDs immediately.
- `GET /api/life/state`: includes persisted analyses and configuration.
- `POST /api/life/semantic/{run_id}/cancel`.
- `POST /api/life/semantic/{run_id}/review`: `{status:"confirmed"}` or `rejected`.

Jobs share the original runtime's serial execution lane, cancellation/shutdown
ownership, artifacts and events. No new scheduler or parallel orchestration.
Cancellation stops waiting; computation in the local daemon may continue briefly.
Installed proposals and a durable output reference are committed together so
recovery does not silently apply the same proposal twice.

## Evidence and bounds

- At most six sources, 2,000 characters each. Scanned book units use their first
  2,000 extracted characters; imported transcripts expose consecutive segments.
  This is **not whole-book understanding**. No additional represented concepts is
  not evidence that the rest of a book/course contains nothing new.
- Explicitly re-read only unchanged, configured-root source files. Changed or
  missing content requires a rescan. Unsupported extraction/empty text fails closed.
- Persist selected text in integrity-checked artifacts with input hashes/locators.
  Secret redaction is best effort, not a guarantee that texts contain no secrets;
  inspect material before authorizing inference.
- Validate bounded schema, actual source IDs, duplicate findings/memberships and
  exact quoted substrings before graph writes. Malformed/invented quotes save a
  diagnostic output artifact but install no concepts or edges.
- Quotation validation **does not prove semantic truth**. A model can quote a
  correct sentence while drawing a wrong equivalence. All assertions start proposed.
- No tools, shell execution, URL fetching or broad filesystem access are provided
  to the model. Source text is explicitly marked untrusted data.
- Native graph JSON preserves generated assertions/quotes, not the runtime's
  source artifacts, model configuration or jobs. Use full runtime backup/restore
  to retain those; graph-only imports require source re-association/re-import for
  another analysis. Never cloud-sync a live SQLite file.

## Actual verification and remaining gaps

Protocol tests deliberately use synthetic model responses. They verify the data
flow, source checks, rejection, review, recommendation integration, restart,
checkpoint recovery, cancellation and API security. They are **not** evidence of
successful real semantic reasoning.

The actual CLI readiness check here returned `model_unavailable`. No Ollama daemon,
weights or GPU is installed; direct model-download probes failed with TLS EOF.
**No real model has analyzed a passage in this environment. Live end-to-end
acceptance remains incomplete.** A working local backend is required to assess
semantic quality, prompt reliability, latency and memory usage on real material.

Still absent: automatic transcript retrieval, web/catalog discovery of recordings
or newer interviews, guest-identity extraction/linking, whole-library incremental
concept reconciliation, reader integration and autonomous whole-book processing.
Consequently the full Milewski, GEB → recording, and Fridman → newer Patel interview
examples are **not yet delivered**. The overlap path can now consume real model
output; illustration links can refer to supplied resources, not discovered ones.
