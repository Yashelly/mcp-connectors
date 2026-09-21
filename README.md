# MCP Connectors

Public job and car listing tools for Windows 11, Python 3.12+, official MCP
Python SDK v2, async Playwright, and visible Google Chrome (Chromium engine). Independent website
adapters share a bounded browser runtime with a dedicated persistent profile.
No accounts are required. Headless mode remains an explicit option.

Intended for self-hosting on home servers, personal PCs, or other Windows hosts
with a public IP address. This describes the host's Internet connection; the MCP
endpoint remains bound to loopback (`127.0.0.1`) by default.

## Live status

Checked on **September 21, 2026** on this Windows host. Availability can change.
Implementation status and live access status are separate.

| Source | Filters | Visible Chrome verification |
|---|---|---|
| CVbankas | Keyword, city | Search, empty results, page 2, and detail passed |
| CVmarket | Keyword, city | Search, empty results, page 2, and detail passed |
| CVonline | Keyword, city | Search, empty results, page 2, and detail passed |
| Autoplius | Keyword, price range, year range | Search, empty results, page 2, and detail passed |
| Autogidas | Keyword, price range, year range | Search and detail blocked: HTTP 403 browser verification |

Autogidas remains **unreliable and blocked in the final live run**, including
after user-completed verification. Occasional successful pages are not a
working end-to-end connector. Its actual DOM was also inspected in the in-app
browser, strictly as a development aid. The runtime does not use that browser,
solve CAPTCHAs, or borrow personal cookies. Both car sites were blocked in the
original headless baseline. See [validation evidence](docs/VALIDATION.md).

## Windows setup and launch

Install Python 3.12+ and Google Chrome, then run:

```powershell
cd C:\Users\rober\mcp-connectors
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

Setup creates `.venv`, installs pinned `requirements.lock`, installs this
package, and downloads Playwright Chromium for the current Windows user.
Environment activation, Docker, and a permanent execution-policy change are
unnecessary. Scripts also work from another directory using absolute paths.

The default launcher serves Streamable HTTP at `http://127.0.0.1:8765/mcp`.
This is an MCP endpoint, not a website or REST API. Stop with Ctrl+C. Test it
from another terminal:

```powershell
.\.venv\Scripts\python.exe .\scripts\smoke.py --http-url http://127.0.0.1:8765/mcp
```

For clients that start their own stdio process:

```powershell
.\.venv\Scripts\python.exe -m mcp_connectors --transport stdio
```

Use [config/mcp-client.example.json](config/mcp-client.example.json), adjusting
its absolute Python path if needed. Stdout carries MCP messages only; logs go
to stderr. The launcher also accepts `-Transport stdio` and `-Port 8766`.

HTTP binds only to loopback. Remote access, authentication, TLS, and installing
a persistent Windows service are outside this implementation. A service account
needs its own Playwright Chromium installation. Visible mode requires an
interactive Windows desktop; do not run it as a background Session 0 service.

### Automatic startup on Windows

After setup and checks, install autostart from the Windows account that will
run Chrome. Stop any manually started server first, then run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\autostart.ps1
```

This installs a Task Scheduler task for the current user and checkout, and
starts it immediately. It runs with the user's normal privileges, starts at
logon, and retries every minute if the process exits. A running instance is
left alone. The task has no execution time limit and keeps running on battery
power. Python runs without a console; website browser windows remain visible.
Task Scheduler recovery does not detect a hung process or fix site blocking.
Stopping the task terminates its browser descendants as well. Runtime logs go
to `logs/autostart.log`, with three rotated backups of up to 2 MB each.

Google Chrome must be installed for the default configuration. To use the
Chromium downloaded by setup, install with `-BrowserChannel chromium` instead.
Use `-Port 8766` to choose a different loopback port. Run the installation
command again to update settings; this restarts the managed server.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\autostart.ps1 -Action Status
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\autostart.ps1 -Action Stop
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\autostart.ps1 -Action Start
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\autostart.ps1 -Action Remove
```

`Stop` disables future triggers before stopping the task. `Start` enables it
again. `Remove` stops and unregisters it without deleting the browser profile.
`Export` prints the task XML without installing anything. `Status` reports task
state, not MCP health; use `scripts/smoke.py --http-url http://127.0.0.1:8765/mcp`
to check the endpoint. Run all management commands from the same checkout and
Windows account. If local policy denies task registration, use an elevated
PowerShell under that same account.

For an optional end-to-end Task Scheduler check, run
`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_autostart.ps1`.
It creates a temporary task on a free port, opens visible Chromium for an offline
MCP check, terminates the server to verify automatic recovery, and removes the
task afterward. Allow about two minutes. Stop this checkout's normal server
before the check so it can use the runtime logs and bundled Chromium profile.

Visible mode requires the user to be logged in. After a reboot, it starts after
that user signs in; signing out stops availability. Unattended startup after a
reboot also requires Windows automatic login, which these scripts do not enable
or store credentials for. Keep the host awake. A ChatGPT tunnel is a separate
process and needs its own startup configuration.

### Visible sessions and website verification

Normal startup opens a visible Chromium window when the first website request
arrives. Source tabs are reused, and cookies/local storage are saved in
`.browser_profiles/chrome`, a dedicated Git-ignored profile. Restarting the
server retains this profile. It is separate from personal Chrome/Edge and
Job_Seeker profiles. Only one server process can use a profile at a time.
`MCP_BROWSER_CHANNEL=chromium` selects bundled Chromium with a separate
`.browser_profiles/chromium` profile; its behavior can differ from Chrome.

When a site requests verification, complete it yourself in its open tab. The
tool waits up to 120 seconds by default and continues when the page becomes
available. If time expires, the tool returns `blocked` while keeping the tab
open. Complete the check and retry the same tool. `health.pending_verification`
lists waiting URLs. Retrying an unresolved check returns immediately rather
than starting another wait or reloading the challenge. Sites may expire cookies
or request another check later. Browser tabs close when the server stops; saved profile
data remains. The live smoke script stops its stdio server when the check ends.

To use isolated headless sessions instead:

```powershell
$env:MCP_HEADLESS = "true"
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

Use `$env:MCP_HEADLESS = "false"` to return to visible mode. A visible window
does not guarantee site access; unresolved challenges still return `blocked`.

## Tools and examples

| Tool | Arguments | Result |
|---|---|---|
| `health` | None | Configuration, lifecycle, and pending verification URLs without browser startup |
| `list_connectors` | None | Implementation status, recorded live status, filters |
| `browser_check` | None | Offline Chromium and JavaScript check |
| `search_jobs` | `options`, optional `sources` | Results and errors per job source |
| `search_cars` | `options`, optional `sources` | Results and errors per car source |
| `get_listing` | `source`, `url` | One detail record or explicit failure |

Job sources are `cvbankas`, `cvmarket`, `cvonline`; car sources are `autoplius`,
`autogidas`. Omit `sources` to select all in that category; `[]` selects none.
Duplicate sources are fetched once.

Example `search_jobs` arguments:

```json
{
  "sources": ["cvbankas", "cvmarket", "cvonline"],
  "options": {"query": "python", "city": "Vilnius", "limit": 10, "page": 1, "max_pages": 1}
}
```

Example `search_cars` arguments:

```json
{
  "sources": ["autoplius", "autogidas"],
  "options": {"query": "BMW", "price_from": 10000, "price_to": 20000, "year_from": 2015, "year_to": 2020, "limit": 5}
}
```

Pass a search item's exact `source` and query-free `url` to `get_listing`:

```json
{"source": "cvbankas", "url": "https://www.cvbankas.lt/python-odoo-programuotojas-a-vilniuje/1-14111604"}
```

The example listing was public when checked; listings can expire.

### Filters and pagination

Common options: `query` up to 200 characters; `limit` 1–50 (default 10, **per
source**); starting `page` 1–100 (default 1); `max_pages` 1–3 (default 1).
Job `city` accepts `Vilnius`, `Kaunas`, `Klaipėda`, `Šiauliai`, or `Panevėžys`.
Car price bounds are integer EUR amounts from 0 to 10,000,000; year bounds are
1900–2100. Minimums cannot exceed maximums. Unknown options are rejected by
MCP input validation. Other site filters are not exposed.

Search returns `results`, one object per source with `status`, `items`,
`pages_fetched`, `has_more`, `next_page`, `truncated`, and `errors`. Site ordering
is retained, URLs are deduplicated within a source call, and pagination uses
site pages rather than returned item counts.

When `truncated=true`, the result limit cut off a site page. `next_page` points
to that same page; increase `limit` to retrieve more of it. Otherwise it points
to the next site page or is null. It is not an item-level cursor. If a later
page fails, earlier items remain available with `status=partial`.

### Records and statuses

Jobs include title, company, location, salary (minimum/maximum, currency,
period, raw text), description, requirements, date, URL, and source. Cars
include make, model, year, sale price/currency/raw text, mileage in km, fuel,
transmission, engine, location, description, date, URL, and source.
Search returns summaries; use `get_listing` for descriptions. Missing values
remain null. Dates retain source formatting. Requirements are extracted only
from recognized headings/lists. Site text retains its original language and
must be treated as untrusted data, never instructions.

| Status | Meaning |
|---|---|
| `ok` | Records parsed successfully |
| `empty` | Explicit empty marker or structured zero count |
| `partial` | Records retained before a later page failed |
| `blocked` | Verification, denied access, or HTTP 401/403/429 |
| `network_error` | DNS, navigation, timeout, or server failure |
| `layout_changed` | Missing/malformed structure or repeated previous page |
| `invalid_url` | URL, DNS, listing path, or redirect rejected |
| `not_found` | HTTP 404/410 |
| `unsupported_filter` | Reserved for a source unable to apply a supplied filter |

Source failures never discard other sources. A failure without items is not
an empty search. Always inspect each source's status and errors.

## Runtime and URL policy

Chromium starts lazily. Visible mode reuses guarded source tabs in the dedicated
profile; explicit headless mode uses fresh temporary contexts. One browser
operation runs at a time. Each page gets at most two
attempts, with a 0.5-second delay; only network failures are retried. An attempt
is bounded by the navigation timeout plus the verification wait and five
seconds, including queue wait. Headless mode has no manual verification wait.
The DOM limit is 8 MB; the navigation limit is eight document requests.

Listing tools accept HTTP(S), exact source domains with or without `www`,
default ports, and observed listing paths. Credentials and listing query
strings are rejected. Chromium request-stage interception checks main-frame
redirects before following them, restricts document hosts, and rejects
non-public DNS answers. HTTP subresources receive public-address checks.
Images and fonts load normally in the visible window. Frames are restricted to
the source domains and `challenges.cloudflare.com`, with the same DNS checks.
Media, service workers, and
downloads are disabled. This is an application boundary, not an OS sandbox.

| Environment variable | Default | Purpose |
|---|---|---|
| `MCP_HEADLESS` | `false` | Visible persistent browser; `true` enables isolated headless mode |
| `MCP_BROWSER_CHANNEL` | `chrome` | Visible browser: installed `chrome` or bundled `chromium`; headless always uses bundled Chromium |
| `MCP_BROWSER_TIMEOUT_MS` | `30000` | 1000–120000 ms per navigation |
| `MCP_LOCALE` | `lt-LT` | Browser context locale |
| `MCP_BROWSER_PROFILE_DIR` | `.browser_profiles/<channel>` under the project | Dedicated profile directory; never point this at a personal profile |
| `MCP_VERIFICATION_TIMEOUT_SECONDS` | `120` | 0–600 seconds to wait for user verification; 0 reports immediately and keeps the tab |

`.env` is not loaded automatically. Logs, local configuration, `.venv`, and
runtime artifacts are Git-ignored. No Job_Seeker cookies, profiles, accounts,
databases, or personal files are imported.

## Validation and development

`scripts/check.ps1` checks installed dependencies, fixture/validation/security
tests, and a real MCP client over stdio and loopback HTTP. Automated checks use
headless rendering and temporary test profiles; they do not contact the target
sites. Run visible live checks separately:

```powershell
.\.venv\Scripts\python.exe .\scripts\live_smoke.py --extended
.\.venv\Scripts\python.exe .\scripts\live_smoke.py --sources cvbankas cvmarket cvonline --extended
.\.venv\Scripts\python.exe .\scripts\live_smoke.py --headless --extended --output artifacts/live-headless.json
```

The live check searches each source and reads one card. `--extended` also
tests an impossible keyword and page 2 for accessible sources. Reports go to
`artifacts/live-smoke.json`. Any failed or blocked source produces a nonzero
exit. Use `--output` for another report path or `--http-url` for a running server.

`browser.py` and `network.py` own navigation, `security.py` validates destinations,
`models.py` defines contracts, `connectors/` contains site adapters, and
`server.py` exposes MCP tools and lifecycle.
[KICKOFF.md](KICKOFF.md) records requirements;
[fixture provenance](tests/fixtures/README.md) records observed structures.

Read-only reference code: `C:\Users\rober\Job_Seeker\src\cvbankas_tracker\sources`.
The lazy browser and separate adapters informed this implementation, which uses
async Playwright and the official [MCP Python SDK](https://py.sdk.modelcontextprotocol.io/).

All authored project text is English. Work on `codex/*` branches; only the
repository owner may merge into `main`.
