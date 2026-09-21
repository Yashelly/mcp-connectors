# Connector implementation requirements

Work in `C:\Users\rober\mcp-connectors`, the standalone Windows 11 repository
at https://github.com/Yashelly/mcp-connectors. Read `AGENTS.md`, `README.md`,
`pyproject.toml`, the browser layer, server, and adapters before changing code.

Use Python 3.12+, official MCP Python SDK v2, async Playwright, and Chromium.
Preserve stdio, loopback Streamable HTTP, lifecycle cleanup, and the offline
browser check. Placeholder adapters do not count as working connectors.
Record current evidence and limitations in [docs/VALIDATION.md](docs/VALIDATION.md).

## Scope

Implement public-data adapters for CVbankas, CVmarket, CVonline, Autoplius,
and Autogidas. Inspect real search pages, form parameters, pagination, empty
states, and detail pages. Never invent selectors or treat fixture checks as
proof of live access. Start with CVbankas, then CVmarket, CVonline, Autoplius,
and Autogidas.

Use `C:\Users\rober\Job_Seeker` as a read-only code reference, especially
`src/cvbankas_tracker/sources/browser_fetch.py`, `cvbankas.py`, and `cvmarket.py`.
Do not modify it or transfer secrets, cookies, profiles, databases, accounts,
or personal files.

Required behavior:

- Search, verified filters, bounded pagination, and listing URL reads.
- Jobs: title, company, location, salary/currency/period/raw text, description,
  requirements, date where available, URL, and source.
- Cars: make, model, year, price/currency, mileage, fuel, transmission, engine,
  location, description, date where available, URL, and source.
- Typed models and clear MCP tools. Missing values remain null.
- Limits on results, pages, concurrency, timeouts, and retries.
- Source-specific errors and useful partial results.
- Distinct empty, layout-change, network, missing-listing, and blocked statuses.
- HTTP(S)/domain/path validation, redirect checks, and private-network rejection.
- Headless Chromium by default. CAPTCHA/interactive verification returns
  `blocked`; no hidden manual or visible-browser fallback.

Authentication, applications, ad publication, messaging, and paid services are
outside scope. Keep Windows setup reproducible. Do not replace MCP with REST
or make Docker/Linux mandatory.

## Acceptance and delivery

Add anonymized fixtures and tests for every source: parsing, missing fields,
empty results, blocked pages, invalid URLs, and limits. Run a small live search
and one detail read per site through a real MCP client. Check stdio and HTTP.
Record inaccessible sites and their concrete failure reasons; do not mark them
ready.

Update the README with actual tools, examples, filters, limits, and statuses.
Pin dependencies in `requirements.lock`. Repeat Windows setup and
`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1`.

Create a `codex/*` branch, review changes, commit, and push it to GitHub.
Never commit to or merge into `main`. Report per-source results, limitations,
unverified behavior, and launch commands. All authored project text is English;
direct conversation with the user is Russian. Preserve literal source text
where parsing requires it.
