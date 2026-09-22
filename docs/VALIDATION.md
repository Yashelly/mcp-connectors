# Validation record

## Windows autostart: September 21, 2026

`scripts/autostart.ps1` installs an interactive, least-privilege scheduled task
for the current Windows user and checkout. The exported definition has a logon
trigger, an indefinite one-minute recovery trigger, no execution time limit,
and `IgnoreNew` for concurrent starts. Stop disables recovery before terminating
the task. No Windows automatic-login settings or user credentials are changed.

The console-free Python entry point fixes visible browser settings, writes
rotating local logs, and assigns itself and browser descendants to a Windows
job with kill-on-close behavior. A forced-exit test verifies descendant cleanup.
`pywin32==312`, already present in `requirements.lock`, is now an explicit
Windows runtime dependency.

The Windows check suite contains 42 tests plus real stdio and HTTP MCP checks.
The additional tests cover the actual exported task definition, management
ordering, unrelated-task protection, and forced process-tree termination.

The opt-in `scripts/smoke_autostart.ps1` check registers a temporary real task,
verifies MCP and visible Chromium offline, kills the server process, waits for
the actual recovery trigger, verifies MCP again, and confirms that stopping the
task releases its port. The temporary task is removed afterward. This check
passed on Windows 11. Reboot/logon triggers were inspected in the task definition;
the host was not rebooted or signed out during validation. Windows Server,
automatic Windows login, and a ChatGPT tunnel were not tested or configured.

## Visible-session follow-up: September 21, 2026

The user requested visible operation after the headless car-site failures.
Visible Google Chrome is now the default, driven by Playwright's Chromium
engine, with a dedicated `.browser_profiles/chrome` profile. Bundled Chromium
is available through `MCP_BROWSER_CHANNEL=chromium`; explicit headless mode
retains isolated temporary contexts. No personal browser profile was imported.

Final real MCP stdio command:

```powershell
$env:MCP_VERIFICATION_TIMEOUT_SECONDS = "0"
.\.venv\Scripts\python.exe .\scripts\live_smoke.py --extended --output artifacts/live-visible-final.json
```

Verification waiting was disabled only for this final test to avoid asking the
user to repeat a looping challenge. Production defaults to a bounded 120-second
manual wait. The final report records `headless=false`, `browser_channel=chrome`.

| Source | Filtered search | Detail | Empty probe | Page 2 |
|---|---|---|---|---|
| CVbankas | `ok`, 2 items | `ok` | `empty` | `ok`, 2 items |
| CVmarket | `ok`, 2 items | `ok` | `empty` | `ok`, 2 items |
| CVonline | `ok`, 2 items | `ok` | `empty` | `ok`, 2 items |
| Autoplius | `ok`, 2 items | `ok` | `empty` | `ok`, 2 items |
| Autogidas | `blocked`, HTTP 403 | `blocked`, pending verification | Not run | Not run |

The suite exits **1** because Autogidas remains blocked. Its final detail call
did not overwrite the pending search challenge. An earlier direct detail
navigation also returned a verification page. Four sources passed all live
probes. Autoplius detail populated make/model, year, sale price/currency/raw
text, mileage, fuel, transmission, engine, location, and description; no
publication date was available.

Autogidas was investigated with visible bundled Chromium and installed Chrome,
both using new dedicated profiles. Some unfiltered/filtered pages returned
HTTP 200, but other searches and detail navigation requested Cloudflare
verification. The user reported that manual completion looped. The same
filtered request could fail without our request interception, so the loop is
not explained solely by the network guard. A single successful page was not
counted as a successful connector.

An accessible Autogidas page also exposed native finance banners sharing the
`item-link` class. The parser now excludes the observed `rel="sponsored"`
banners while still rejecting malformed real cards. A fixture-based regression
test covers that distinction.

Persistent-session tests use real Chromium with synthetic local responses and
temporary profiles. They check source-tab reuse, closed-tab recovery, cookie
persistence after restart, manual completion, bounded expiry, immediate return
for an unresolved retry, and no manual wait in headless mode. The challenge
provider frame is permitted with public DNS checks; unrelated frames remain
blocked. Existing redirect/private-address tests remain in place.

Windows setup was repeated successfully. The current `scripts/check.ps1`
suite includes **36 tests** and real MCP stdio/Streamable HTTP checks.
No automated CAPTCHA solving, fingerprint spoofing, or personal cookie import
was added. A visible desktop and installed Google Chrome are required by the
default mode. One process can use a profile at a time. Manual verification does
not guarantee acceptance by the site.

## Initial headless baseline

Date: September 21, 2026. Platform: Windows 11, Python 3.12, Playwright 1.63.0
bundled Chromium, headless mode, MCP Python SDK 2.2.0. No saved browser profile,
cookies, login state, proxy rotation, or CAPTCHA solving was used.

### Headless MCP results

Equivalent command with the current CLI:

```powershell
.\.venv\Scripts\python.exe .\scripts\live_smoke.py --headless --extended
```

The check used a real MCP stdio client. Job queries were `python`, city `Vilnius`,
limit 2, one page. Car filters were EUR 10,000–20,000 and years 2015–2020,
limit 2. A separate impossible keyword and unfiltered page 2 were checked for
accessible sources. Full local reports are in Git-ignored
`artifacts/live-smoke.json`; this document records the shareable summary.

| Source | Search | Detail | Empty probe | Page 2 |
|---|---|---|---|---|
| CVbankas | `ok`, 2 items | `ok` | `empty`, 0 items | `ok`, 2 items |
| CVmarket | `ok`, 2 items | `ok` | `empty`, 0 items | `ok`, 2 items |
| CVonline | `ok`, 2 items | `ok` | `empty`, 0 items | `ok`, 2 items |
| Autoplius | `blocked`, HTTP 403 | `blocked`, HTTP 403 | Not run locally | Not run locally |
| Autogidas | `blocked`, HTTP 403 | `blocked`, HTTP 403 | Not run locally | Not run locally |

The complete live suite exits **1**, correctly reflecting two blocked sources.
It is not an all-sites pass. The job-only suite can be run separately.
CVbankas and CVmarket detail records populated company, location, salary,
description, requirements, and publication date. CVonline populated company,
location, salary, description, and publication date; the checked card did not
produce a recognized requirements list, so that field remained null.

Both car sites returned localized Cloudflare verification pages. The observed
markers included `Luktelėkite...`, `Tikriname jūsų naršyklę`, and
`Saugumo patvirtinimo atlikimas`. Blocking remained explicit for search and
direct detail requests, with no records fabricated from the challenge page.

### Observed structures and regressions

| Source | Verified search parameters | Primary search/detail evidence |
|---|---|---|
| CVbankas | `keyw`, `location[]`, `page` | `a.list_a`; `#jobad_heading1`, `#jobad_company_title`, salary component, itemprop description/date |
| CVmarket | `search[keyword]`, `search[locations][]`, `start` in steps of 30 | `a.jobad-url`; public JobPosting JSON-LD and employer header |
| CVonline | `keywords[0]`, `towns[0]`, `limit=20`, `offset` | `__NEXT_DATA__`, `searchResults`, vacancy ID links and detail payload |
| Autoplius | `qt`, `sell_price_from/to`, `make_date_from/to`, `page_nr` | `a.announcement-item`; `.title-text`, `.parameter-row`, `.price` |
| Autogidas | `f_376`, `f_215/216`, `f_41/42`, `page` | `a.item-link`; `h1.sticky-title`, `.sticky-price strong`, label/value pairs |

CVonline keyword/city parameters were captured by submitting the actual public
form, then checked with a fresh headless navigation. City IDs for all exposed
cities came from site forms or public location data; the live smoke exercised
Vilnius, not every city individually.

CVmarket's `start=0` redirect double-encoded bracketed parameters and silently
dropped filters. The adapter omits `start` on page 1. Its JSON-LD also referenced
`PostalAddress` IDs while defining `Address` IDs; the adapter resolves this
observed discrepancy and uses the visible employer header when the referenced
organization has no definition. Tests reproduce both failures.

CVonline's town dictionary sometimes arrives as a list. Both representations
are fixture-tested. A simple `keywords` parameter was rejected by the site;
the adapter uses the observed indexed key `keywords[0]`.

Public car DOM was inspected through the in-app browser because local headless
requests were blocked. Price/year values were verified on filtered page 2,
including selected form values and the next-page links. Explicit empty messages
and detail fields were inspected. These observations support selectors and
fixture parsing, **not** local runtime accessibility. Full attribution and
example public paths are in [fixture provenance](../tests/fixtures/README.md).

### Automated checks at the initial baseline

Completed on the recorded host: `scripts/setup.ps1` exited 0;
`scripts/check.ps1` exited 0 with **29 tests passed**, consistent installed
dependencies, and successful real MCP stdio and Streamable HTTP checks.

Run `scripts/check.ps1` for dependency consistency, all unit/integration tests,
and real MCP stdio plus loopback Streamable HTTP smoke. Coverage includes:

- Search/detail parsing, missing fields, empty markers, and challenge pages for
  all five sources.
- Salary decimals/ranges, sale price versus loan/export amounts, verified query
  parameters, city mappings, and source data variations.
- Input bounds, unknown options, invalid URLs, private DNS/mixed DNS answers,
  blocked subresources, and navigation limits.
- A real Chromium redirect fulfilled locally with an HTTP 302 to loopback;
  interception rejects it before following the destination.
- Pagination limits, deduplication, repeated-page detection, and retained
  records when a later page fails.
- Lazy startup, browser recovery/cleanup, tool registration, MCP validation,
  and JavaScript execution over both transports.

Windows setup installs the pinned dependencies and Chromium. Check scripts do
not contact target sites. Live checks are separate and intentionally small.

### Remaining limits at the initial baseline

- Car-site local headless access is blocked. Successful end-to-end car search
  and detail extraction has not been demonstrated on this host.
- Only the documented filters and five job cities are exposed. The live suite
  does not exhaust all combinations, cities, or pages.
- Fixtures are reduced and anonymized DOM excerpts, not complete site archives.
  Rare listing layouts may require additional fixtures.
- Requirements extraction recognizes specific heading/list structures. Dates,
  currency, periods, and other absent source values remain null rather than
  being inferred. Autoplius detail publication date was not available.
- URL/DNS checks are an application safeguard. They are not DNS pinning or an
  operating-system network sandbox; sites remain untrusted external content.
- Remote hosting, authentication, TLS, Windows service installation, and
  sustained-load testing were not part of this implementation.


## Tunnel deployment and recovery (September 22, 2026)

- The user supplied successful home-host client v0.0.14 startup logs and a
  `ready` response from `/readyz`, then reported successful ChatGPT health,
  connector listing and CVbankas search calls. This is user-provided deployment
  evidence, not a fresh live check of every source.
- `scripts/check.ps1` passed 48 tests and both stdio and HTTP MCP/browser smoke
  checks after the tunnel launcher was added.
- `scripts/smoke_tunnel_autostart.ps1` passed with a real temporary Windows
  scheduled task and dummy child: launch, restart after forced child exit,
  and descendant termination when the task stops. Temporary artifacts were
  removed. No real tunnel credential or OpenAI connection was used in this test.
- Tests cover task XML, secret decoding, child-only environment, log redaction,
  safe preflight failure output, and disabling recovery before stopping.
- The new managed tunnel task still needs installation on the home server.
  Reboot, sign-out, Windows Server editions, and real OpenAI outage recovery
  were not tested. Periodic triggers recover exited processes, not hangs.
