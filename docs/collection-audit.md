# Command-driven collection audit — before source changes

Current source inspected: scanner/full-text limits, semantic source snapshots and
proposal validation, graph corrections, runtime serialization/recovery, browser
submission markers, API lifespan/auth, forms and tests. Existing working parts
are reused. The restored checkout's older Git metadata was reconciled to ca0022e
without replacing workspace files.

Missing product behavior: no collection intent, scope grant, whole-text traversal,
batch queue/checkpoints, cross-batch concept context, or executive collection result.
Default scanner semantics deliberately excerpt only (PDF first 100 pages; Markdown
500 headings; EPUB 1000 spine entries). Those defaults must remain compatible, but
the collection path must either extract all permitted content or explicitly fail
with an omission. Never silently adopt scanner truncation as full reading.

Implement a durable collection job around existing serial semantic runs. One
explicit provider/disclosure approval covers the snapshotted directory operation;
no model calls while planning. Full text is split into cited <=2000-character
passages and <=6-passage batches. Persist run references BEFORE execution, reuse
completed work, and block automatic replay after ambiguous browser delivery.
Provider/security setup is a one-time prerequisite, not a per-batch checklist.
Use evidence-backed canonical-context reuse, never title-only merges; identity
and related-idea inferences stay proposed. A completed operation means its planned
text was processed, not that every possible concept/equivalence was discovered.

The newly requested collection orchestration supersedes the prior no-whole-library
scope restriction. No unrelated orchestration or reader integrations are added.
Native Windows 11 / real account acceptance cannot be certified from Linux/Arena.
