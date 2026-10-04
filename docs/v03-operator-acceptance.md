# V0.3 operator acceptance — real browser accounts, not synthetic fixtures

Run this on the machine that owns your provider account. Do not send passwords,
MFA codes, browser profiles, session cookies, or CDP access to Arena. A passed
pytest suite is NOT a pass of this procedure. Repeat separately for every provider
you intend to use; ChatGPT, Claude and DeepSeek can have different DOM behavior.

## 0. Prepare and record scope

- Install `[browser,books]` in the local Python environment; neither Ollama nor
  Codex SDK is required. Start current installed Chrome with the dedicated profile
  described in [browser-accounts.md](browser-accounts.md). Sign in manually first.
- Check the provider's current permitted automation and account/privacy settings.
  Use ordinary text chat without connected actions/apps. No CAPTCHA bypass, stealth,
  login automation, security downgrade, or alternative-provider fallback.
- Use accessible real material you are authorized to submit: a book passage and
  lecture transcript with a known shared idea and a known additional idea. Import
  text or scan a read-only library root. Retain original hashes/files.
- Identify exactly which units will be sent. Each analysis uses up to six units,
  at most 2,000 characters each; imported transcripts are segmented, scanned
  chapter analysis uses the first 2,000 characters. No claim about an entire
  Milewski chapter/course can follow from an inadequate excerpt.
- Record provider, browser version, date, Omnibus commit and source unit IDs in
  your local acceptance notes. Do not record account/session secrets.

## 1. Separate connection from authenticated use

In `/life`, configure the intended browser provider and check readiness.
`available: true` here means only that local CDP metadata was reachable. It does
not test login, a paid plan, specific model identity or successful generation.

Select the actual units, approve the displayed provider and run Analyze. Inspect
the run's stage list and evidence details:

1. **browser_reachable** — the actual job reached the local CDP endpoint.
2. **provider_session** — expected provider HTTPS page, editable composer and a
   recognized visible account control. This is a DOM observation, not verification
   of account identity/subscription. If the selector no longer matches, stop and
   update/test that adapter; do not reinterpret an anonymous composer as login.
3. **submission_attempted** — durable marker written BEFORE text entry (drafts may
   autosave), followed by one Enter action. It does not prove provider receipt.
4. **response_captured** — actual returned text persisted as an artifact; inspect
   its backend/model-identity-unverified metadata. No invented token counts.
5. **semantic_validated** — schema, source IDs and literal quotes passed. Inspect
   quotes against both originals; this stage does NOT independently prove semantics.

The browser's JSON stability/Stop-control check is heuristic, not an official
completion event. A failure must stay visible in the run. In particular, a
reachable browser or usable page must not mark stages 3–5 successful.

## 2. Review, compare and recommend

- Before review, graph relations must be **proposed**, and must not support a
  trusted recommendation. Look for one shared concept with citations in both
  passages and any candidate-only finding with its own quote.
- Correct a wrong relationship using the graph inspector (old version becomes
  superseded), reject unsupported assertions, and confirm supported ones. Batch
  review is available before individual edits; partial review is explicitly marked
  and should be completed in the graph inspector.
- **proposals_reviewed** records actual edge decisions, including replacement
  versions. Rejection is a completed review, not endorsement. A no-findings result
  is not a successful recommendation workflow.
- Use Discovery & comparison → Compare confirmed evidence. Verify shared ideas,
  additional represented ideas and supporting paths. Its ratio is an **unweighted
  fraction of represented confirmed concepts**, not a whole-book similarity score.
  Missing coverage means unknown, not that a source adds nothing.
- Record actual reading/progress on the source unit (do not fabricate activity to
  make acceptance pass). Refresh Today. The recommendation should explain why now,
  encountered/current concepts, possible additions, URL status, source quotes and
  limitations. Current position is not proof of understanding.
- **recommendation_generated** records server generation from confirmed evidence.
  **recommendation_rendered** is separate: the UI acknowledges insertion into its
  DOM. Refresh analysis status to see that acknowledgement. This is not a screenshot
  or proof of visual quality; personally verify the card is usable.
- Inspect rendered evidence. Accept/dismiss/defer/ignore, restart the server, and
  verify feedback/quota persist. An ignore must not create a broad dislike.

Stage entries are historical observations with timestamps, not a promise that a
past recommendation remains eligible after graph corrections. Each stage needs
its own evidence; do not infer later stages from earlier ones.

## 3. Test actual resource discovery, separately from model analysis

Choose the current unit/interest or a liked interview. Suggest a query from its
confirmed graph, **review the exact public query**, then explicitly authorize
public search/retrieval. This discloses that query to DuckDuckGo and makes anonymous
GET requests to up to three candidate URLs (bounded redirects); it does not use
or export provider cookies. It is independent of chat-provider search claims.

- Search must produce a saved raw search-page snapshot before `search_performed`
  is true. A model saying “I searched” is never accepted as that evidence.
- Candidate URLs must be fetched separately. Inspect the final URL, retrieval time,
  raw page artifact, title, reported date and text snapshot. Retrieval establishes
  source-reported metadata, NOT authoritative truth, guest identity or a listened
  recording. Only one unambiguous reported publication date is used.
- Failed/blocked/rate-limited/JS-only pages must appear as limitations, never as
  verified candidates. If public search is unavailable, supply a URL and explicitly
  verify it, or add a normal library URL labeled **manually supplied, unverified**.
  Verifying a supplied URL is not automatic discovery.
- Analyze retrieved text units with your current book/interview units through the
  authorized browser backend. The model may propose coverage, illustration or an
  explicitly quoted guest identity. All remain proposed until reviewed. A webpage
  summary is not the audio/video/transcript itself.
- Alternatively, inspect the fetched text and propose a connection to an existing
  concept/person with an exact quote. This is explicitly a **user-selected relation**,
  not automatic semantic discovery. Confirm only after checking it.

### Example-specific checks

**Milewski → lecture:** use enough selected actual material to support the claimed
comparison. Shared concept IDs need quotations from both sources; extra concepts
need candidate quotations. No numerical claim of “substantial whole-course overlap”
from a small excerpt or titles.

**GEB → Crab Canon recording:** a reached section must connect to a motif and the
retrieved resource must have quoted, reviewed illustration evidence. Verify the
actual link and description. Do not claim the app listened to the recording.

**Liked interview → newer same guest:** use a confirmed, explicitly identified
person, or analyze both introductions together to propose the same person with
name-bearing source quotes. New interview date must be retrieved page metadata;
its guest relation must have a retrieved quote containing the person's name/known
alias, plus human review. Title/name similarity alone is insufficient. An older
manually supplied date remains labeled a supplied assertion; topic novelty is
unknown unless compared separately. Resolve homonyms/identity ambiguities yourself.

## 4. Failure / recovery tests

- Sign out or use a page without a recognized account control: stop before typing;
  no captured response, validated proposals or recommendation should be fabricated.
- Cancel/disconnect after submission attempt: inspect the provider tab manually.
  Retrying the run must NOT resend, even if uncertainty is acknowledged. A new
  explicitly authorized analysis is a new submission, not silent recovery.
- Alter/remove a source artifact in a disposable test copy: retrieval-dependent
  recommendations must disappear rather than retain a forged “verified” flag.
- Reject/correct supporting coverage: comparison and visible recommendations must
  recompute from the current confirmed graph, not historical rejected assertions.
- Graph-only export/import preserves relationships, not raw runtime artifacts.
  Imported discoveries are unverified until retrieval evidence is available again.
  Use full backup/restore for durable snapshots/jobs; never sync live SQLite.

## Record result honestly

For each provider, record PASS/FAIL/BLOCKED for each stage, relevant run/edge/
artifact/recommendation IDs, source scope and unresolved uncertainties. Do not mark
this acceptance passed based on the synthetic tests, connectivity, or one provider
working when another has not been tested.

This sandbox has **not** passed this real-account procedure. Its actual public
search attempt also failed at network/TLS retrieval, producing a persisted failure
report and zero candidates. That is failure handling evidence, not discovery success.
