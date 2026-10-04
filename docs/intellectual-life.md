> **Update:** the prior unavailable semantic seam now has an executable local Ollama path.
> See [current setup, tests and remaining blockers](local-semantic-analysis.md).
> Live-model acceptance and autonomous discovery remain incomplete; historical
> no-backend descriptions below refer to the earlier manual milestone.

# Intellectual Life guide

## Start with your actual library

Install `.[books,test]` for optional PDF parsing, or `.[test]` for the EPUB/text/
Markdown/HTML core. The Codex extra is unnecessary. Start `par serve`, then open
`http://127.0.0.1:8000/life` (or follow the link from the existing runtime page).

1. **Settings → Library roots:** enter a native directory path on the server host.
   A browser on a different computer cannot scan its own disk through this field.
2. Click **Scan read-only**. Inspect the report for malformed/unsupported files,
   duplicate locations, changed versions or missing locations.
3. **Library:** search/filter and open a resource. Correct title/creators if metadata
   is absent; filename-derived titles are explicitly marked as such.
4. **Resource detail:** inspect content units and provenance. Record an initial
   **position** rather than pretending all prior pages were read today. Then use
   **reading** with start/end boundaries. `90 → 100` means 10 pages, not 11.
5. Marking a content unit complete is a position assertion, not fabricated daily
   reading time; it does not automatically move the parent book's cursor. EPUB uses spine sections labeled chapters, not invented pages.
6. **Today:** daily charts show newly encountered ranges, grouped by their actual
   unit (pages, chapters, percent or seconds). Dates are UTC, explicitly labeled.

Progress and chart history are durable. Reading ranges are unioned, so rereading
an already represented range adds no new-reading credit. Revisit events add no
credit. Imported positions and estimates add none. A correction targets an earlier
progress event; the original row remains append-only, while the corrected range
is attributed to its original day. Current position can move backward; it is not
an assertion of how much you understood or how many unique pages exist in memory.

## Connect ideas without making things up

Use **Add resource, URL, concept or person**. A URL is stored and validated, not
fetched; supply a real link yourself. Persons are resource nodes with kind `person`.
Concept kind can be idea, motif, question, claim, method, etc.

Under **Idea graph → Connect resources and ideas**, choose any number of member
nodes with roles. Common patterns:

- `covers`: source = resource/content unit; concept = each concept it covers.
- `illustrates`: resource = recording/example; concept or motif = what it illustrates.
- `features_person`: resource = interview; person = guest resource node.
- `overlaps_with`, `adds_material`, `prerequisite_for`, `created_by`, `related_to`,
  and user-reaction edge types are also stored and inspectable. The current
  recommender does **not** execute a policy for every possible relation type.

Write an explanation and provenance. These are **your assertions**, not proof
from an AI reading the book. Choose proposed if uncertain; only confirmed, active,
non-expired edges with confidence at least 0.6 feed recommendations. A purely
model/heuristic edge cannot be submitted as confirmed without explicit user
confirmation evidence.

The SVG is an incidence graph: every diamond is one hyperedge and every spoke
names a participant's role. Click a node to inspect/expand a neighborhood; click a
diamond to inspect all members, confidence and evidence. Search and relation-type
filters limit the view. Confirm, reject/disconnect, or edit a relationship's JSON;
edits append a replacement and preserve the superseded edge. Concept merges retain
old nodes, aliases and historical edge membership rather than silently destroying
provenance.

## What the recommendation policy actually does

The policy uses only stored evidence and user state, never lexical similarity:

- Completed resource/unit coverage can establish a **represented concept set**.
  Another resource with confirmed coverage exposes shared and additional concept
  IDs. This is not a measured percentage of equivalent text or a guarantee that
  all material is represented.
- A concept at the current resource/unit position plus a confirmed `illustrates`
  edge can suggest a supplied linked recording/example.
- An explicit positive interview reaction plus `features_person` edges and valid
  supplied publication dates can suggest a newer interview with the same guest.
  It explicitly says topic overlap has not been established.

Stored explanations include supporting edge IDs, triggering activity IDs, overlap/
additional concepts, confidence, policy score, and supplied attention-minutes when
available. The display provides why/why-now evidence, not an endless feed.

Default: at most three **new** suggestions per UTC day, persisted across refreshes
and restarts. Settings allow zero through five, or disable all suggestions. Accept/
dismiss/defer/ignore feedback is stored. Dismissal permanently suppresses a repeat
in this milestone; deferral lasts one day; ignoring reduces priority weakly and
never creates a definitive dislike. Explicit dislike reactions suppress the target.
Accept/dismiss feedback records an explicit scoped preference, not a general topic
inference. Rejected/superseded relationships cease supporting future suggestions.

## CLI (native POSIX, PowerShell and cmd)

Activate your virtual environment, or use `.venv/bin/par` on POSIX and
`.venv\Scripts\par.exe` on Windows. Stop the server before offline CLI commands
that access Intellectual Life. Prefix every command with `--data-root PATH` if
using a non-default root.

```text
par life --help
par life root "C:\Users\you\Books"
par life root "/home/you/Books"
par life scan ROOT_ID
par life resources --search "Milewski"
par life inspect RESOURCE_ID
par life edit RESOURCE_ID --title "Corrected title"
par life progress RESOURCE_ID --kind position --end 90
par life progress RESOURCE_ID --start 90 --end 100 --date 2026-10-04
par life progress RESOURCE_ID --kind correction --corrects EVENT_ID --start 95 --end 100
par life react RESOURCE_ID like
par life add "Concept X" --node-type concept --kind idea --evidence "My explicit concept label"
par life add "A supplied recording" --kind recording --url "https://YOUR-ACTUAL-URL" --evidence "Manually supplied link"
par life connect --type covers --member RESOURCE_ID:source --member CONCEPT_ID:concept --explanation "This section introduces X" --evidence "My notes, section 2"
par life graph --focus RESOURCE_ID
par life recommendations
par life feedback RECOMMENDATION_ID dismissed --note "Already familiar"
par life relationship EDGE_ID rejected
par life edge-json corrected-edge.json
par life merge-concepts OLD_CONCEPT_ID TARGET_CONCEPT_ID
par life settings --daily-limit 2
par life settings --disable
par life export intellectual-life.json
par life import intellectual-life.json
```

The URL above is a placeholder, not a promised working recording. Use a link you
actually have. IDs come from commands/UI. A corrected edge JSON uses the same
validated Edge fields plus `supersedes: OLD_EDGE_ID`; old provenance remains.

## Data, migration, export and portability

Migration **002_intellectual_life.sql** extends the existing SQLite store:

- `nodes`: typed resources/concepts/content units; optional parent FK.
- `edges` + `edge_members`: true n-ary relationships and role-bearing membership.
- `activity`: append-only progress/reactions/corrections (database triggers).
- `preferences`, `recommendations`, `library_roots`, `knowledge_settings`.

Existing projects/tasks/runs/artifacts/events/memory remain unchanged. Upgrades are
transactional; backup first. The paired `.down.sql` deliberately removes only new
capability tables and returns schema version 1. It is an **offline destructive
rollback**, never automatic; existing runtime data is preserved. Reopening with
the current app reapplies migration 002.

Graph JSON uses `format: omnibus-idea-graph`, `version: 1`. It includes nodes,
provenance, edges/members, activity, preferences, recommendations/feedback and
frequency settings. IDs survive import. Reimport of identical records is a no-op;
conflicting existing IDs reject the **whole transaction** with a conflict list.
Invalid references, schemas and parent cycles reject before writes. This is not
a merge/synchronization protocol. Export is bounded to 10,000 nodes/edges and
50,000 activities; import to 20 MiB.

Source paths may appear as provenance, but imported paths never authorize scans.
Library roots must be configured explicitly on each host. Book contents are not
copied into export; only bounded excerpts/hashes/locators. Ordinary `par backup`
also includes these database tables, not original Books directories. Do not put
live SQLite files in consumer cloud-sync folders.

## Supported formats and honest limits

- **EPUB:** ZIP/container/OPF metadata, ordered spine sections and bounded excerpts;
  defused XML, no archive extraction. Section count is not a physical page count.
  DRM/encrypted, unusual encodings/unsupported manifest references may be reported
  malformed rather than decoded. No cover extraction or EPUB reader integration.
- **PDF:** optional pypdf metadata, fixed page count (1–2000); short text excerpts
  from the first 100 pages. No OCR; encrypted PDFs are unsupported. Blank/scanned
  PDFs still have pages but do not magically yield text.
- **Markdown:** UTF-8 headings, text excerpt units and character locators.
- **Text/HTML:** UTF-8 plain text/HTML title, script/style-free excerpt; a single
  text unit. No browser execution, remote assets or general HTML article scraper.
- **Unsupported:** MOBI/AZW/DJVU/DOCX/audio/video decoding and all other extensions
  are reported per file. A malformed file does not abort neighboring files.

Bounds: 50 MiB input files; 2 MiB plain text/chapter parsing; 30 MiB total expanded
EPUB; 2000 archive members; 10,000 directory entries per scan. Symlink files and
symlink directories are not followed. File changes during a read are detected;
OS-level races and adversarial parsers are not a full security sandbox. Use local
files you trust. PDF parsing has no hard CPU/memory isolation. Scans hash files
each time but skip re-parsing unchanged content. Exact hashes add locations; changed
bytes create a new version. A move is indicated as an additional identical-content
location plus a missing prior path, not inferred identity from similar filenames.

This is a small-library milestone: several queries currently load whole tables;
there is no paging/indexed full-text search or large-corpus performance guarantee.
The library display is capped at 100 filtered resources, unit detail at 250 units,
graph at 200 visible nodes/60 complete hyperedges, chart at 30 recorded days.
No background watcher, auto-scan scheduler, natural-language Books router, or
notifications have been added. Entering a request in the old mock-backed task
journal does not invoke this capability; use Intellectual Life UI/CLI/API.

## Optional enrichment and readers

`SemanticEnricher` and `ReaderAdapter` protocols are replaceable seams, not claims
of installed integrations. `UnavailableEnricher` is the production state. There
is no configured backend/plugin loader or reader connector yet. A future backend
must return validated proposed concepts/edges with locators from supplied context;
invalid/provenance-free proposals fail validation. No mock enricher is selected in
production, and no semantic extraction was performed in this milestone.

Manual editing is the functional path now. Supplied text is parsed structurally,
not semantically read by a model. YouTube metadata/transcripts/music, local reader
position APIs and nuanced overlap discovery remain unimplemented.

## Tests and reproducible UI smoke

```sh
python -m pytest -q -rs
python -m pytest tests/test_intellectual_life.py -q
node --check src/par/static/life.js
```

Default tests are credential-free. Optional PDF and SDK contract tests explain
skips if the corresponding extras are absent. The old real Codex tests remain
opt-in; they are not needed for this capability and were not called in this task.
No CI workflow is committed.

For the DOM/live-HTTP interaction smoke, use a **fresh** disposable data root.
This optional test uses Node/jsdom, not a rendered Chromium browser; it is not a
production frontend dependency.

Terminal 1:

```sh
par --data-root .par-life-smoke serve --port 8765
```

Terminal 2, from this checkout:

```sh
npm install --prefix .cache/life-dom jsdom --no-audit --no-fund
node tests/manual_life_dom.cjs
```

The script creates its own temporary Books fixture on the same host. It exercises
root configuration/scan, library display, progress forms, 55%/20-page calculations,
chart SVG, graph evidence inspection, a synthetic contextual recommendation,
dismissal and export. If the server uses token auth, set the same
`PAR_ACCESS_TOKEN` in the test process; it is not printed or committed. Override
`PAR_SMOKE_BASE` or `PAR_JSDOM_MODULE` for another local port/module location.

### Manual smoke on another OS (not claimed tested here)

On native Windows: use the README PowerShell install commands, start
`.venv\Scripts\par.exe --data-root .par-life-smoke serve`, and open `/life`.
Create a temporary Books folder with a Markdown heading and a known EPUB/PDF.
Configure/scan it, verify discovered metadata and scan errors. Add a manual
200-page fixture, set initial page 90, record 90→100 and 100→110 on the same date:
expect 20 new pages, 55%. Repeat/revisit the range: no extra new pages. Connect a
section to a motif and a supplied recording using covers/illustrates; record a
position in the section, inspect/dismiss the recommendation. Restart the service:
progress, chart data and dismissal should persist. Verify source hashes/mtimes
before/after. Export/import to a fresh data root, reconfigure paths separately.
macOS uses the same POSIX commands as Linux. Neither OS was run in this session.
