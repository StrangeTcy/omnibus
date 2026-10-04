# V0.3 audit — before implementation (2026-10-04)

Inspected scanner/parser, graph/provenance/corrections, semantic worker, browser
transport, recommendation policy, API/CLI/UI, interchange and current documentation.
Baseline: aabb857 on arena/01a107a0-omnibus. Preserve these components and schema.

| Operation | Actual state at audit |
| --- | --- |
| Scan/extract local resources | Executable, read-only bounded EPUB/text/HTML/optional PDF; hashes, units, repeat/version handling. No OCR, reader or whole-library semantics. |
| Provider proposals | Executable Playwright/CDP path for ChatGPT/Claude/DeepSeek presets, and optional Ollama. Synthetic tests only; none authenticated-live-accepted here. Browser reachability is NOT login or model evidence. |
| Validate/review | Exact supplied ID/quote/schema checks; model assertions proposed, explicit confirmation/rejection, correction/supersession in graph inspector. Does not verify semantic truth. |
| Update graph | Atomic n-ary proposal installation and batch review; separate batches do not reconcile concepts automatically. |
| Recommend | Confirmed coverage + recorded progress; illustration path; liked-interview/shared-person/newer-supplied-date rule. Sparse persisted feedback. URLs/guest relations so far supplied by user, NOT discovered. |
| Discover/verify external URLs | Absent. Browser model's claimed search is not observed search evidence. No retrieved link metadata or source snapshots. |

Defects to address: recommendations do not clearly distinguish link verification,
source-reported metadata, additional represented concepts and unknown coverage;
no real search/retrieval capability; no complete persisted stage ledger or rendered
acknowledgement; editable composer alone is not evidence of an authenticated account.

Plan: bounded public search + independently fetched page snapshots behind an
explicit network permission, replaceable search/fetch interfaces, no credentials
or model dependency; preserve uncertain candidate semantics as proposals. Use
existing artifacts/nodes/events (no new scheduler or architecture). Add comparison
report over confirmed graph, evidence-rich recommendation fields, stage ledger,
API/UI/CLI and deterministic/security tests. Document a separate real-account
operator test. If search/retrieval fails, show failure and manual-unverified URL
path; never call a title/URL guess verified or claim a model searched.
