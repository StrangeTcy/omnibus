# Browser-account correction — 2026-10-04

User clarified the intended backend: their signed-in ChatGPT/Claude/DeepSeek
websites, controlled by Playwright, not a required local model. Added an optional
CDP transport for current installed Chrome/Chromium, provider-specific disclosure
consent, dedicated-profile confirmation, durable submission markers and blocked
uncertain replay. UI/CLI/API select browser accounts. Website responses use the
same source quotation validation and provisional graph pipeline.

**Experimental, not live accepted:** no authenticated browser/provider session is
available here. Preset DOM selectors, Google login behavior and real completion
quality remain unverified. No credentials were requested, imported or tested.
The browser-account requirement is recorded in [browser-accounts.md](browser-accounts.md),
including Chrome 136 profile restrictions, manual sign-in and native setup steps.

Current suite: **85 passed, 3 skipped** with the optional browser extra installed;
15 browser protocol/consent/recovery cases are synthetic, not live-provider tests.
Python compileall and JS syntax checks pass. Historical milestones follow below.

---

# Current correction — 2026-10-04

The previous milestone below was insufficient for the requested intelligent assistant.
An executable local Ollama semantic path is now implemented (API/CLI/UI), not just
an adapter protocol. It extracts source-quoted provisional concepts/relations and
connects reviewed coverage to progress-based recommendations. Read
[the implementation and acceptance limits](local-semantic-analysis.md).

**Not complete:** no live inference has run here, and external content discovery,
whole-library reconciliation and reader integration are still absent. Actual CLI
readiness failed with `model_unavailable`; no backend/weights are installed and
model-download probes failed TLS EOF. Protocol tests must not be read as model-quality
or real-book evidence. The historical counts below describe the prior environment.

Current verification: **70 passed, 3 skipped** (15 new semantic protocol/validation
cases); Python compileall and JavaScript syntax checks passed. The three skips
are the optional SDK contract and two opt-in live Codex tests in this environment.
The actual local semantic readiness CLI returned `model_unavailable`, exit **1**.
No new visual browser or real-model quality test is claimed.

---

# Omnibus — Intellectual Life milestone status (2026-10-04)

## Outcome

Fetched upstream `main` at **10881b1**, read `omnibus plans.txt`, and implemented
its final **Idea Hypergraph and Personal Intellectual Assistant** vertical slice
in the existing runtime. No model or paid API is required or called for it.

The working capability is: configure Books root → read-only scan → persistent
resources/content units → manual progress/corrections → daily chart → explicit
n-ary idea relationships → sparse, evidence-supported recommendations → inspect/
correct/dismiss → portable graph export/import.

**No automatic semantic discovery is claimed.** The new recommendation evidence
was synthetic/manual, not analysis of Milewski, GEB, interviews or the user's real
library. No semantic backend or reader-app connector is configured. The existing
optional Codex worker is preserved; its previous authentication blocker is not a
blocker for this deterministic capability.

## Git/workflow handling

Removed `.github/workflows/tests.yml` from the previously rejected, unpushed commit
by amending that commit, then merged the upstream plans on the fixed session
branch. No workflow exists in the reachable branch history. Workflow files are
ignored; no workflow permissions are requested. Original brief/plans are preserved.

## Files changed / migrations

New implementation:

- `src/par/knowledge_models.py`: validated nodes, evidence, n-ary edges, activity,
  feedback/preferences and settings.
- `src/par/knowledge.py`: durable graph/progress/corrections, concept merge and
  bounded incidence-neighborhood queries.
- `src/par/library.py`: bounded read-only EPUB/text/Markdown/HTML and optional PDF
  parsing, hashes/duplicate locations/versioned changed content, scan reports.
- `src/par/recommendations.py`: confirmed-evidence policies, persistent sparse
  quota and inspectable explanations/feedback.
- `src/par/graph_io.py`: versioned transactional JSON import/export with reference,
  schema, cycle and conflict validation.
- `src/par/enrichment.py`: explicit optional interfaces, unavailable production
  backend and model-proposal evidence validation (no production fake).
- `src/par/life_api.py`, `src/par/life_cli.py`: existing server/CLI extensions.
- `src/par/templates/life.html`, `src/par/static/life.js`, `life.css`: Today/library/
  detail/graph/recommendation/settings page with vanilla JS and SVG.
- `src/par/migrations/002_intellectual_life.sql` and paired `.down.sql`.
- `tests/test_intellectual_life.py`, `tests/manual_life_dom.cjs`.

Updated: `src/par/db.py` migration runner/table refs; `api.py` route/static mount;
`cli.py` life subcommands; runtime template navigation; `pyproject.toml` parser
extras/static packaging; schema-version assertion in `tests/test_runtime.py`;
`.gitignore`; README and documentation. Added implementation audit and full guide
at `docs/idea_hypergraph_implementation_notes.md` and `docs/intellectual-life.md`.
No general-runtime entities or worker architecture were replaced.

Migration 002 adds `nodes`, `edges`, `edge_members`, append-only `activity`,
`preferences`, `recommendations`, `library_roots`, `knowledge_settings`. Existing
runtime tables remain intact. Upgrade and explicit destructive capability-only
downgrade/reupgrade were tested with populated graph/runtime data. Back up before
upgrading/downgrading; the down script is never run automatically.

## Actual automated results

Host: **Linux, Python 3.11.2**. New parsing dependencies tested: defusedxml 0.7.1,
pypdf 6.19.0 (optional books extra). No paid calls, no workflow/remote CI run.

```sh
.venv/bin/python -m pip install -e ".[test,books]"
.venv/bin/python -m pytest -q -rs
```

**56 passed, 2 skipped, 0 failed.** Two skips: old authenticated Codex integration
tests not opted in. One existing Starlette/httpx TestClient deprecation warning.
The previous runtime's behavioral tests remain green; only its expected schema
version assertion was updated from 1 to 2 for the real migration.

```sh
.venv/bin/python -m pytest tests/test_intellectual_life.py -q
```

**15 passed, 0 failed.** Coverage includes:

- EPUB metadata/spine; Markdown/text/HTML; real pypdf parsing of a generated
  200-page PDF; unchanged source SHA-256/mtime; repeat scan; exact duplicates;
  changed versions; possible moved locations; malformed/unsupported/symlink/XML
  entity rejection without aborting neighboring files.
- 90→100→110 on a known 200-page resource: 20 newly read pages, 55%, exact daily
  chart; correction/revisit deduplication; EPUB chapter units; restart persistence.
- Hyperedge with three nodes and three distinct roles; membership/evidence/confidence
  preserved; valid export/import, no-op reimport, schema/ID/conflict/cycle rejection.
- Synthetic A covers X/Y, B covers X/Y/Z, completed A: overlap X/Y and represented
  additional Z, traceable to stored edges. Similar titles alone yield no claim.
- Current section → concept/motif → supplied recording recommendation; dismissal
  survives restart; explicit positive interview reaction → newer same-guest link;
  ignore weakens priority without fabricating a negative preference.
- Relationship rejection/supersession, concept merge/history, disabled/expired/
  unconfirmed relation behavior, unavailable semantic backend and rejection of
  invented semantic evidence locators.
- UI HTTP/CSRF flow, CLI subprocess progress/export, migration rollback and whole-
  database backup/restore with the graph included.

Clean **wheel-installed core-only** environment (no pypdf or Codex SDK):

```sh
.venv/bin/python -m pip wheel --no-deps -w /tmp/omnibus-life-wheel .
/tmp/par-core-env/bin/python -m pip install --force-reinstall --no-deps /tmp/omnibus-life-wheel/personal_agent_runtime-0.2.0-py3-none-any.whl
/tmp/par-core-env/bin/python -m pip install "defusedxml>=0.7,<1"
/tmp/par-core-env/bin/python -m pytest -q -rs
```

**54 passed, 4 skipped, 0 failed.** Extra skips: optional SDK contract and optional
PDF parser. This validates packaged templates/static assets/migrations as well as
operation without a model SDK. The separate core environment was created during
the preceding milestone; it was updated with the new wheel.

Also passed: `python -m compileall -q src`, `node --check src/par/static/life.js`,
`node --check tests/manual_life_dom.cjs`, `git diff --check`.

## Actual running-application smoke

Started real Uvicorn on `0.0.0.0:8765` in this preview environment, with an explicit
throwaway access token and temporary data root. Default product binding remains
loopback-only. Unauthenticated requests were rejected. All smoke servers were
stopped afterward; no public unauthenticated service was left running.

Ran the committed `tests/manual_life_dom.cjs` with jsdom against that live HTTP
server (jsdom installed in a temporary directory). **Passed, zero DOM script
errors.** It exercised:

1. Authenticated `/life` HTML and CSS/JS assets.
2. Settings root form and actual read-only Scan button for a temporary Markdown book.
3. Library display and newly populated graph participant selectors.
4. Resource progress form twice: 90→100 and 100→110.
5. Displayed 55% / 20 new pages and chart SVG.
6. Synthetic concept + supplied fixture recording, actual hyperedge diamonds and
   clickable evidence panel.
7. Contextual suggestion, dismissal button and suppression on refresh.
8. Semantic/reader unavailable notices and graph export.
9. Original source file unchanged.

Stopped and **restarted the entire server process** against the same data root;
queried HTTP state again: 20 newly read pages, 55%, graph edges and dismissal
survived, with no duplicate recommendation. Re-ran the committed DOM smoke on a
second fresh data root successfully.

A real Chromium visual test was attempted but **blocked**: Playwright's browser
CDN download failed with TLS `ECONNRESET`. JSDOM is DOM/HTTP interaction evidence,
not a rendered-browser/accessibility audit. No successful visual test is claimed.
The reproducible optional smoke commands and native Windows manual checklist are
in `docs/intellectual-life.md`.

## Start the application

Linux/macOS:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[books,test]"
.venv/bin/par serve
```

Windows PowerShell/cmd:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[books,test]"
.venv\Scripts\par.exe serve
```

Open **http://127.0.0.1:8000/life**. Configure a directory under Settings, scan it,
then open a resource. The existing runtime remains at `/`. Directory paths refer
to the server host. No SQLite cloud-sync arrangement is implemented or required.

## Supported / unsupported / unresolved

- Supported locally: EPUB, UTF-8 text/Markdown/HTML; PDF with `[books]`, including
  page count and bounded early-page excerpts. No source originals edited/moved.
- Unsupported: DRM/encrypted books, OCR, MOBI/AZW/DJVU/DOCX, audio/video decoding,
  remote metadata/transcript acquisition, YouTube/media API integrations.
- No real semantic enricher or reader integration was configured/tested. Structured
  parsing is not semantic understanding. Manual concepts/relations/progress work.
- Small-library scope: synchronous bounded parsing, some whole-table queries and
  limited UI neighborhoods; no large-corpus performance or adversarial parser
  sandbox claim. Limits are detailed in the guide. HTML currently yields one text
  unit; EPUB uses spine sections, not reliable print chapters/pages.
- Library metadata correction edits title/creators without rewriting file identity
  or progress units. Unit completion does not implicitly move the parent cursor.
- Concept merge/correction preserves evidence, but there is no general multi-master
  conflict resolution, sophisticated preference learning or marginal-value model.
- Graph exports carry provenance paths/excerpts, not book bytes, scan authorization
  or external worker sessions. Configure roots separately on another machine.
- Windows/macOS and Python 3.12/3.13 were not executed; manual instructions exist.
- No workflow files are committed. No real model calls were made in this milestone.

**Next useful increment:** identify the user's actual reading application and
implement/test its documented position/history adapter, keeping imported position
assertions distinct from measured reading sessions. This removes manual progress
friction without spending model allowance or pretending semantic discovery exists.
