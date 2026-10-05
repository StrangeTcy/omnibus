> V0.3 adds [independent public discovery and richer recommendation evidence](v03.md).
> Use the [separate real-account operator test](v03-operator-acceptance.md);
> browser-account acceptance remains unverified in this sandbox.

# Browser accounts: Playwright + installed Chrome

**Intended backend:** your signed-in ChatGPT, Claude or DeepSeek website account,
not an assumed API subscription and not a required Ollama installation.

**Implementation status (2026-10-04): experimental.** The executable browser
transport and semantic pipeline are connected. Provider DOM presets exist for all
three sites, but none has been verified against an authenticated live account in
this sandbox. Tests use synthetic DOM/CDP fixtures, not your provider account.
A reachable debugger is not proof of a valid login, working selector or model access.

## Why installed Chrome, and why manual login?

Google explicitly says sign-in can be blocked for browsers controlled by software
automation. Old browser versions are another possible cause, not the only cause.
An up-to-date Chromium build or spoofed user-agent is **not** a guaranteed fix.

Use a current installed Chrome (or compatible Chromium-based browser). First sign
in manually in a dedicated profile **without Playwright attached**. Then attach
Playwright for approved chat interactions. If Google/provider security still
rejects the session, stop and use the supported manual login/recovery path.
No stealth patches, CAPTCHA solving, credential interception, cookie copying,
MFA automation, disabled browser security or bypass of provider restrictions.

Chrome 136+ does not honor remote-debugging switches on its default data directory.
Use a separate `--user-data-dir`, not your existing personal Chrome profile.
This is also an important security boundary: CDP provides powerful control over
that browser. Do not put unrelated accounts, private tabs, extensions or saved
passwords in this dedicated profile. Keep Chrome current.

## Local setup

Omnibus, Playwright and the browser must run **on the same computer as your
accounts**. The Arena sandbox cannot reach your laptop's localhost or borrow its
login. Do not upload account sessions, passwords or profile archives to Arena.

Install the optional Python dependency inside Omnibus's environment:

```sh
python -m pip install -e ".[browser]"
```

You do **not** need `playwright install chromium` when attaching to installed
Chrome. Omnibus does not automatically install Chrome, launch an account session,
or authorize an external submission for you.

### 1. Manual sign-in, dedicated profile, no debugging

Example Linux command (adjust executable if your distribution uses another name):

```sh
google-chrome --user-data-dir="$HOME/.omnibus-browser-profile" https://chatgpt.com/
```

macOS:

```sh
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --user-data-dir="$HOME/.omnibus-browser-profile" https://chatgpt.com/
```

Windows PowerShell (adjust Chrome's path for per-user installations):

```powershell
& "$env:ProgramFiles\Google\Chrome\Application\chrome.exe" "--user-data-dir=$env:LOCALAPPDATA\OmnibusBrowserProfile" https://chatgpt.com/
```

Sign into the desired provider yourself. Complete Google sign-in/MFA/security
checks manually. Also use `https://claude.ai/` or `https://chat.deepseek.com/` if
needed. Select ordinary text chat, not an agent/action mode with connected apps.
This adapter does not enforce the provider's internal tool permissions.

Close **all windows belonging to this dedicated profile** before step 2. Leaving
its original process running can cause Chrome to reuse it without enabling CDP.
Do not delete the profile to solve a login issue; it contains your account session.

### 2. Reopen the same dedicated profile with loopback debugging

Linux:

```sh
google-chrome --user-data-dir="$HOME/.omnibus-browser-profile" --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222
```

macOS:

```sh
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --user-data-dir="$HOME/.omnibus-browser-profile" --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222
```

Windows PowerShell:

```powershell
& "$env:ProgramFiles\Google\Chrome\Application\chrome.exe" "--user-data-dir=$env:LOCALAPPDATA\OmnibusBrowserProfile" --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222
```

Keep port 9222 loopback-only. Do not expose it through Arena previews, a LAN bind,
reverse proxy or tunnel. CDP is not the authenticated Omnibus web API. Local
malicious software can control this debug-enabled profile. Close the browser
when not using it. Profile isolation is an operator setup requirement, not a
sandbox inferred automatically from CDP metadata.

### 3. Select the account and approve an analysis

In `/life` → Semantic analysis → Browser account, select the provider, confirm the
dedicated profile, and check readiness. Import actual text or scan a book root.
Select source units and approve sending them to the **displayed provider**.
Local Ollama consent does not authorize uploading content to a website.

Equivalent CLI (stop the Omnibus server first to release its data-root lock):

```sh
par life browser --provider chatgpt --confirm-dedicated-profile --check
par life import-text lecture.txt --title 'Lecture transcript'
par life resources
par life analyze UNIT_ID_A UNIT_ID_B --authorize-provider chatgpt
par life analyses
par life review-analysis RUN_ID confirmed
```

Replace `chatgpt` with `claude` or `deepseek` for the other presets. Each job freezes
its selected provider and source snapshot; later settings changes cannot reroute
it. There is no automatic provider/account fallback, parallel swarm or quota bypass.
Website use may consume your plan allowance. Check the provider's current terms
and permitted automation; a consumer subscription does not automatically permit
all automated access. No paid API key is required by this browser transport.

## Exactly what the adapter does

1. Check the configured loopback CDP endpoint and validate its advertised websocket
   is also loopback on the configured port. Disable HTTP redirects/environment proxies.
2. Attach Playwright to that already running browser. Open **one new provider tab**;
   do not enumerate other tabs, read old conversations or export credentials.
3. Require the expected HTTPS origin, one editable empty composer, a recognized
   visible signed-in account control, and no previous
   answers. Stop on a login redirect or incompatible page rather than guess controls.
4. Persist a submission-attempt marker **before text entry** (sites may autosave
   drafts). Fill the selected source prompt and JSON schema, then press Enter once.
5. Read only the response selector in that new tab. Accept a bounded JSON document
   stable over four observations while no recognized Stop control is visible.
   This is a DOM heuristic, not an official provider completion event. No model
   identity or token usage is fabricated; the site-selected model remains unverified.
6. Pass the result through the existing source-ID/verbatim-quotation validator.
   Only valid outputs install provisional graph relations. Human review remains
   necessary because a correct quotation does not prove semantic equivalence.

If a response never appears, streams too long, hits limits, needs human attention,
or the layout changes, the job stops rather than resending or changing accounts.
Login/challenge diagnosis is intentionally conservative: not every provider banner
is recognized. After possible text entry, failure/cancellation is an **uncertain
submission**. The durable marker survives restart and prevents retry from silently
sending the same prompt again, even with the runtime's retry acknowledgement.
Inspect the browser tab and explicitly create a new approved analysis if appropriate.
There is not yet an automated “reattach and reconcile this unfinished chat” workflow.

In legacy single-analysis mode the new tab is left open for inspection. In collection
mode its completed response is saved durably before closing that owned tab; uncertain
uncaptured tabs stay open. Local validation can resume from the captured response. The code disconnects its Playwright client;
it never calls `browser.close()` on your attached browser. Cancellation does not
retract an already submitted prompt or cancel the provider's generation. No
screenshots, HAR, traces, cookies or storage state are collected by this adapter.
Keep Playwright debug logging off when handling sensitive material.

## Data, portability, limits

The selected text is **external disclosure**, not local inference. Provider retention,
training/privacy settings and plan limits apply. Source text snapshots, response
artifacts, provenance and submission metadata are kept locally in Omnibus. Provider
chat history also exists in your account; Omnibus does not automatically delete it.
The adapter grants itself no permission to purchase, publish, change account
settings or use connected applications.

Keep the browser profile outside Git, synced folders and Omnibus's data root.
Omnibus backup/export does not package browser credentials. On another computer,
create a new dedicated profile and sign in there rather than copying cookie databases.
Native Linux/macOS/Windows instructions above are not claims of tested native login.

The default [collection assistant](collections.md) now orchestrates the bounded
transport automatically across entire supported collections, with one scoped
disclosure approval. Legacy single-analysis mode still uses up to six 2,000-character
units and per-analysis approval under advanced controls. Safe pre-send collection
failures back off; uncertain sends never replay automatically. Reader tracking and
general-purpose browser task automation are not implemented. Authenticated native
acceptance remains required; see [the Windows test](collection-native-windows.md).

## Official references checked

- Google supported-browser/sign-in troubleshooting:
  https://support.google.com/accounts/answer/7675428
- Chrome 136 remote-debugging/default-profile change:
  https://developer.chrome.com/blog/remote-debugging-port
- Playwright CDP attachment (Chromium-based browsers, lower fidelity than native protocol):
  https://playwright.dev/python/docs/api/class-browsertype#browser-type-connect-over-cdp
