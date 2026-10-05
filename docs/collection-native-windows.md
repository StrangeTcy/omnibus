# Native Windows 11 / real website-account acceptance

**Status on 2026-10-05: BLOCKED / NOT RUN.** The implementation environment is Linux
and has no signed-in provider account. JSDOM, provider doubles and Linux tests are
not native Windows or live model evidence. The executable below refuses Linux/WSL
and Windows builds below 22000. No credentials are needed in chat or Arena.

## Preparation (on the actual Windows computer)

Use native Python 3.11–3.13, current installed Chrome, and a new dedicated browser
profile outside Git, synced storage and Omnibus data. Follow
[browser setup](browser-accounts.md), including manual login and loopback-only CDP.
Google can reject automated sign-in even with current Chrome; no bypass is promised.
Use standard chat without connected external-action tools. Never expose port 9222.

In PowerShell, from the checkout:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[books,browser,test]"
$case = Join-Path $env:LOCALAPPDATA ("OmnibusAcceptance-" + (Get-Date -Format yyyyMMdd-HHmmss))
$books = Join-Path $case "Books"
.venv\Scripts\python.exe tests\create_collection_fixture.py $books
```

This creates two Markdown and two EPUB fixtures, each spanning multiple passages,
with overlapping definitions of composition, identity and functors and distinct
wording. These are synthetic **input study notes**; the live test must obtain real
website responses, not synthetic model output. Existing directories are not overwritten.

## Required UI run

```powershell
.venv\Scripts\par.exe --data-root "$case\ui-data" serve
```

1. Open `http://127.0.0.1:8000/`. Select the already signed-in provider if not configured.
2. Enter one request: `Read all the books in "<actual $books path>". Build an idea graph across the whole collection, merge duplicate concepts where justified, connect related ideas, and preserve evidence showing where each idea came from.`
3. Inspect files, omissions, batch count and the real plan. No provider submission
   may occur until the **single collection disclosure approval**.
4. Approve once. Verify automatic successive batches without unit selection or
   additional checklists. Do not falsely mark a challenge/login as available.
5. Require completed/planned passage and batch counts to match, no extraction
   omissions, real cross-book findings and justified identity reuse. Inspect EPUB
   final chapters and Markdown tails. Spot-check quotes against passage artifacts.
6. Confirm dashed provisional coverage, provenance and explicit uncertainty; confirm
   or correct an edge afterward and verify the changed status/current evidence.
7. Repeat the command: same operation, no new model requests or graph duplicates.
   Add a new fixture book: unchanged validated passages should be reused.
8. Pause/restart between completed batches: retained progress, no duplicate graph.
   A stop after text entry may be ambiguous; verify it stops for inspection rather
   than sending again. Never use “verified not sent” if sent or uncertain.
9. Close/unavailable Chrome before a new batch; observe safe retries and clear
   attention state. A genuine security challenge must require manual resolution.

Keep dated Windows build/Python/Chrome versions, provider, job/run IDs, screenshots
of scope/progress/graph/evidence, and observed failure/restart results locally.
Do not publish profiles, cookies, debugger URLs, passwords or private book text.
Mark any failed step FAIL/BLOCKED; do not relabel it as a passing mock test.

## Additional executable real-account check

Stop the server first. Use a **fresh** data root (cached results are refused as a
fresh live acceptance). The flag below is consequential: it authorizes all fixture
text/derived evidence to the named provider through your dedicated signed-in profile.
This consumes real account allowance. No login is automated and no model is mocked.

```powershell
.venv\Scripts\python.exe tests\native_windows_collection.py `
  --data-root "$case\live-script-data" --books $books --provider chatgpt `
  --approve-collection-disclosure --timeout 3600
```

Use `claude` or `deepseek` only when actually testing that configured account.
The script records `native-windows-acceptance.json` in the local data root. PASS
requires all passages completed across multiple batches, real `playwright-cdp`
response metadata for the requested provider, cross-book connections and identity
reuse. UI/semantic spot checks above are still required; a script PASS alone does
not certify general semantic correctness. Failure/timeout is not success. Inspect
and resume an interrupted operation through the UI rather than blindly rerunning.
