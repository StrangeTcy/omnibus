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
