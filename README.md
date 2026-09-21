# MCP Connectors

Public job and car listing tools for Windows 11, Python 3.12+, official MCP
Python SDK v2, async Playwright, and headless Chromium. Independent website
adapters share a bounded browser runtime. No accounts are required.

## Live status

Checked on **September 21, 2026** on this Windows host. Availability can change.
Implementation status and live access status are separate.

| Source | Filters | Local headless verification |
|---|---|---|
| CVbankas | Keyword, city | Search, empty results, page 2, and detail passed |
| CVmarket | Keyword, city | Search, empty results, page 2, and detail passed |
| CVonline | Keyword, city | Search, empty results, page 2, and detail passed |
| Autoplius | Keyword, price range, year range | Search and detail blocked: HTTP 403 browser verification |
| Autogidas | Keyword, price range, year range | Search and detail blocked: HTTP 403 browser verification |

The car adapters are implemented and fixture-tested, but **not verified as
usable in local headless operation**. Their actual search, filters, pagination,
empty states, and detail DOM were inspected in the in-app browser. That was a
development aid, never a runtime fallback. The server returns `blocked` without
solving CAPTCHAs, borrowing cookies, or opening an interactive browser.
See [validation evidence](docs/VALIDATION.md).

## Windows setup and launch

Install Python 3.12+ and run:

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
needs its own Playwright Chromium installation.

## Tools and examples

| Tool | Arguments | Result |
|---|---|---|
| `health` | None | Configuration and lifecycle state without browser startup |
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

Chromium starts lazily. Each fetch uses a fresh context without saved cookies
or profiles. One browser operation runs at a time. Each page gets at most two
attempts, with a 0.5-second delay; only network failures are retried. An attempt
is bounded by the configured timeout plus five seconds, including queue wait.
The DOM limit is 8 MB; the navigation limit is eight document requests.

Listing tools accept HTTP(S), exact source domains with or without `www`,
default ports, and observed listing paths. Credentials and listing query
strings are rejected. Chromium request-stage interception checks main-frame
redirects before following them, restricts document hosts, and rejects
non-public DNS answers. HTTP subresources receive public-address checks;
third-party frames, images, media, and fonts are blocked. Service workers and
downloads are disabled. This is an application boundary, not an OS sandbox.

| Environment variable | Default | Purpose |
|---|---|---|
| `MCP_HEADLESS` | `true` | `false` only for deliberate local debugging |
| `MCP_BROWSER_TIMEOUT_MS` | `30000` | 1000–120000 ms per navigation |
| `MCP_LOCALE` | `lt-LT` | Browser context locale |

`.env` is not loaded automatically. Logs, local configuration, `.venv`, and
runtime artifacts are Git-ignored. No Job_Seeker cookies, profiles, accounts,
databases, or personal files are imported.

## Validation and development

`scripts/check.ps1` checks installed dependencies, fixture/validation/security
tests, and a real MCP client over stdio and loopback HTTP. It does not contact
the target sites. Run live checks separately:

```powershell
.\.venv\Scripts\python.exe .\scripts\live_smoke.py --extended
.\.venv\Scripts\python.exe .\scripts\live_smoke.py --sources cvbankas cvmarket cvonline --extended
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
