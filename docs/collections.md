# Command-driven collections — V0.4

The default `/` page (also `/life`) is now the collection assistant. Enter:

> Read all the books in `D:\Books`. Build an idea graph across the whole collection, merge duplicate concepts where justified, connect related ideas, and preserve evidence showing where each idea came from.

Use a directory **on the server's computer**. Quote paths containing punctuation
or spaces. A Linux server cannot open the Windows computer's `D:` drive. This is a
bounded natural-language collection intent parser, not a general arbitrary-task
planner. Unsupported requests fail explicitly; they do not fall back to MockWorker.

## Ordinary flow

1. Install the browser extra and manually sign into current Chrome's dedicated
   profile as described in [browser setup](browser-accounts.md). Existing configured
   website accounts are reused. No API key, Ollama, Codex or bundled old Chromium
   is required. Account availability is not inferred from saved settings.
2. Enter the command on `/`. Local read-only inventory and extraction produce the
   actual manifest, passage snapshots, extraction issues and inspectable plan.
   This local preparation can take time; nothing goes to a model yet.
3. Approve the **named provider and collection disclosure once**. Every remaining
   passage is scheduled automatically in serial batches of at most six passages,
   each at most 2,000 characters, with bounded prior canonical evidence. No unit-ID
   selection, six-chunk manual loop or per-batch disclosure checklist is required.
4. Follow progress, omissions, failures and remaining batches. Inspect the graph,
   themes, cross-book connections, identity reuse, single-book topics and unresolved
   uncertainty. The graph is useful provisionally: reviewing every edge is **not**
   a prerequisite to completing the operation. Corrections remain available in
   advanced controls and update the collection view.

The former forms are preserved under **Advanced controls**. The old runtime journal
is `/runtime`. Legacy per-analysis tools retain their own explicit approvals;
these are not steps in the collection workflow. Collection execution is not exposed
through the legacy `par run` command.

## What “complete” means

EPUB spine text, Markdown/text/HTML sections, and extractable PDF page text are
partitioned into contiguous passages, including tails and short sections. Full
mode includes Markdown headings and PDF pages beyond the scanner's first 100-page
excerpt window. Citations retain the original file SHA, section/page locator,
exact section character range and immutable passage artifact. Original books are
never modified, renamed or moved. Whitespace-only characters are counted but not
submitted for interpretation. PDF requires `[books]`; EPUB uses the core parser.

Every submitted source must be cited verbatim in a finding or explicitly accounted
for as uncovered. Missing accounting, invented quotes, schema errors or unsupported
canonical IDs fail the batch without installing graph assertions. A completed job
means every planned text passage has a validated accounting result, **not** proof
that a model understood every idea or produced an exhaustive ontology.

Unsupported files, malformed/encrypted files, image-only/empty sections, no OCR,
extraction limits and scan limits stay visible. They cause `partial`, not a false
claim that the entire original collection was understood. Current defensive limits
include 50 MiB per file, 10,000 scan entries, 500 Markdown headings, 1,000 EPUB spine
entries, 2,000 PDF pages, 2 MiB per extracted section and 20 MiB full text per book;
EPUB also bounds expanded ZIP size. Exceeding a full-mode limit rejects that
extraction rather than silently reading an excerpt. External links are not fetched.

The snapshot is fixed: later file changes are not silently sent. Credential
redaction is best effort and can change supplied text; the saved semantic input
snapshot is the authority for quotation validation. Do not approve secret material.
Provider retention, privacy settings, permitted automation and quotas still apply.
Use ordinary chats, not agent/research modes or connected external-action tools;
Omnibus does not enforce the provider's own tool permissions or sandbox its service.

## Persistence, restart and limits

`collection_jobs` (SQLite migration 003) stores the manifest, signature, approval,
current batch/run IDs, attempts, statuses and retry time. Approval freezes provider
configuration and snapshot signature. Later settings changes do not redirect it.
Child runs are recorded before execution. Semantic graph installation and its
checkpoint are atomic. Restart reconciles checkpoints before submitting more work.

Identical commands over an unchanged snapshot return the existing operation.
Adding books reuses prior validated batches whose inputs remain entirely inside
this scope; old passages are not sent again. Concurrent planning is serialized.
Changed file versions get new immutable passages. Repeating a partial operation
rechecks extraction omissions; if a local failure is resolved, completed analysis
is reused while newly available passages are planned for approval. Local preparation itself is
synchronous; a crash during preparation requires repeating the command and reuses
stable passages, rather than recovering a durable per-file planning cursor.

Only clearly safe pre-submission unavailability/quota/interruption failures retry
automatically, after 60, 300 and 900 seconds. Exhaustion, login/security challenges,
changed layouts and invalid replies stop visibly. After resolving the cause, resume
retains finished work. There is no quota bypass or automatic provider substitution.

A marker is persisted **before text entry**, since a site can autosave drafts. If
submission might have occurred but no response was captured, execution stops for
inspection: it never blindly replays. The explicit “verified NOT sent” override is
only for an operator who actually inspected the provider. If sent or uncertain,
do not use it. Automated recovery of an unfinished provider conversation is not
implemented. A completed JSON response is durably captured before closing only
its automation-owned tab; interruption afterward can resume local validation without
another provider send. Other tabs/browser and uncertain tabs remain untouched.

Canonical context is limited to 16 relevant existing findings and two quotations
each, from this scope. Identity reuse needs current quotes, a supplied prior quote,
a substantive justification and confidence ≥ .85. It remains a **provisional model
hypothesis**, not semantic truth. Label equality alone never merges. Co-discussion
n-ary edges are explicitly heuristic, not causation. Explicitly evidenced people
are supported; a general entity-resolution system is not claimed. The main drawing
shows at most 20 books/30 themes for readability, not as a processing cap. Single-book
topics are not proof of novelty or absence elsewhere.

## Evidence and outstanding acceptance

See [current results](status.md) and [native Windows acceptance](collection-native-windows.md).
Automated model responses are labeled synthetic fixtures. No authenticated provider
or native Windows run has been executed in this Linux workspace. Experimental
website selectors, real completion quality and real-account collection throughput
remain unverified. This live acceptance requirement is **outstanding**, not passed.
