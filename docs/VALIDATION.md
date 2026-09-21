# Validation record

Date: September 21, 2026. Platform: Windows 11, Python 3.12, Playwright 1.63.0
bundled Chromium, headless mode, MCP Python SDK 2.2.0. No saved browser profile,
cookies, login state, proxy rotation, or CAPTCHA solving was used.

## Live MCP results

Command:

```powershell
.\.venv\Scripts\python.exe .\scripts\live_smoke.py --extended
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

## Observed structures and regressions

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

## Automated checks

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

## Remaining limits

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
