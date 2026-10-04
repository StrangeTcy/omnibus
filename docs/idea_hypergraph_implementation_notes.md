# Intellectual Life implementation audit — 2026-10-04

Read the fetched `omnibus plans.txt` (the final Idea Hypergraph build spec
supersedes the earlier Books-only proposal), current README/status, Store and
migration 001, API/CLI/templates, capabilities, worker interface and tests.

Reuse: sqlite3 transactions/WAL, UUID/UTC identity, artifact backup, append-only
runtime events, FastAPI security boundary and Jinja/vanilla JS, CLI data-root and
single-authority lock. Preserve tasks/projects/runs/memory and optional workers.
The current UI is a runtime journal, not a library or graph. Add an Intellectual
Life page linked from it, rather than replace the runtime. No model calls are
needed for scanning, manual progress, graph queries or known-relation suggestions.

Schema conventions: versioned SQL plus JSON object payloads, FK references and
Store CRUD. Extend with migration 002 and a documented explicit down script;
keep typed resource/concept/unit nodes plus actual edge-membership rows (arbitrary
cardinality), append-only activity, explicit preferences and recommendations.
Existing schema-version assertion will change to 2; all behavior tests must pass.

Parsing available: stdlib ZIP/XML/HTML/text; add small `defusedxml` dependency for
untrusted EPUB XML, optional `pypdf` extra for PDFs. No frontend dependency needed
for an SVG incidence graph (hyperedge nodes and role-labeled memberships) or daily
charts. Never fetch URLs or send text to a model as a side effect of scanning.

Plan: migration + validated graph/provenance services → bounded read-only scanner
and correction-aware range progress → library/detail/Today UI and CLI → graph
neighborhood/export/import → small evidence-based recommender + feedback → optional
semantic and reader interfaces with an honest unavailable production state →
fixtures/regression/manual server smoke and accurate docs. No workflows will be
committed. The unpushed workflow-containing commit was amended before merging the
new upstream plan; the workflow path is now ignored, not in branch history.

## Semantic correction review — 2026-10-04

Identified gap: the shipped `UnavailableEnricher` plus manual graph and deterministic
rules did not implement the user's requested semantic intelligence. This was
explicitly acknowledged before the correction, but this persisted audit addendum
was written during implementation, not before the first source edit.

Reuse the actual runtime lifecycle/worker interface (optional run_id added),
artifacts and serial execution gate; no new database migration or scheduler.
Add explicit local Ollama configuration, actual structured chat requests, bounded
source snapshots and quotation validation, atomic proposed graph installation,
review and existing recommendation integration. No mock substitution or model
installation by the application. Source scanning itself remains inference-free.

Acceptance gap is concrete: no local model daemon/weights, download TLS failures,
no live model output. Tests are labeled protocol simulations. Do not relabel this
as completion of the full intellectual assistant. See local-semantic-analysis.md.

## Browser-account correction audit (before implementation)

The user's intended backend is their signed-in ChatGPT/Claude/DeepSeek website
accounts, not a required local model or API subscription. Current defects: Ollama
is the only semantic client; consent describes local-only processing; worker and
provenance labels assume Ollama; there is no browser delivery uncertainty journal.
Add an optional Playwright/CDP browser transport, explicit provider-disclosure
consent, manual login boundary and durable pre-send marker. No automatic retry
of a possibly sent browser prompt, provider switching, account extraction or
security-challenge bypass. Keep the existing inference/quotation/review pipeline.

Verified official docs: Chrome 136+ ignores remote-debugging switches for its
normal/default data directory; use a dedicated non-default profile. Google says
software-controlled browsers can be rejected even when current, so “update
Chromium” is not a guaranteed sign-in fix. Sign in manually with current installed
Chrome before attaching automation; stop if rejected. Playwright connect_over_cdp
supports Chromium-based browsers with lower fidelity than its native protocol.
Provider DOM selectors and authenticated behavior cannot be verified here without
the user's host/session; mark adapters experimental, not live-tested integrations.
