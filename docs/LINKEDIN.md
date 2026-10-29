# LinkedIn MCP integration

Agent Reach 1.5 points its optional LinkedIn channel at
[stickerdaniel/linkedin-mcp-server](https://github.com/stickerdaniel/linkedin-mcp-server).
This project connects directly to that upstream over local Streamable HTTP;
Agent Reach and mcporter are not required. The current upstream package name is
`mcp-server-linkedin`, pinned here to 4.28.0 in `requirements.linkedin.lock`.
Agent Reach's current main branch uses OpenCLI instead; this integration follows
the requested MCP backend from its earlier channel.

The upstream runs in `.venv-linkedin`, independently of the existing adapters
and their shared async Playwright browser. It uses its own Patchright browser
runtime. Existing adapters continue to use installed Chrome through Playwright.
No new dependency is added to the main `requirements.lock`.

## Install and sign in

Use Python **3.12.4 through 3.14** for this optional environment. The main server
can continue to use Python 3.12.2. Run the main `scripts/setup.ps1` first; its pip
installs into the separate LinkedIn environment using `--python`, without
changing the main environment's packages. From the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/linkedin.ps1 -Action Setup -Python "C:\Path\To\Python\python.exe"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/linkedin.ps1 -Action Login
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/linkedin.ps1 -Action Run
```

Complete login and any verification manually in the visible browser. The launcher
uses installed Chrome with a dedicated profile, controlled by upstream Patchright.
`-ChromePath` selects another Chrome/Chromium executable. Login state is stored
under `%ProgramData%\MCPConnectors-LinkedIn-<current-user-SID>\session\profile`,
with upstream metadata in the dedicated `session` parent. Do not put other data
in that parent: upstream session rotation owns it. These local runtime files
are outside the repository. The launcher disables automatic
imports from personal browsers with `--no-auto-import`. Do not import cookies or
profiles from Job_Seeker. Setup does not enable automatic package updates.

The launcher creates new state and installer directories with Python 3.12.4+'s
restricted Windows ACLs, then verifies ownership, permissions and the full path
ancestry using upstream checks. Existing ACLs are never modified. This keeps
state outside home directories where sandbox/shared-folder grants can prevent
upstream private-state checks from passing. `-StateRoot` accepts another dedicated
private directory with a trusted ancestry; its immediate parent must already
exist. Use the same state root for Login and Run. If checks fail, the launcher
stops before starting the backend. Do not weaken upstream checks or remove
existing AppContainer/sandbox grants to make them pass.

The backend binds to `http://127.0.0.1:8001/mcp`. Keep it running in its own
terminal; Ctrl+C stops it. `-Port` changes its port. It has the upstream's full
tool set, including write tools, and must remain local. Only the four listed
read tools are forwarded by MCP Connectors. This launcher does not install an
autostart task or deploy anything to another machine.

In another terminal, enable the bridge and start MCP Connectors:

```powershell
$env:MCP_LINKEDIN_URL = "http://127.0.0.1:8001/mcp"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run.ps1
```

For a stdio client, add `MCP_LINKEDIN_URL` to its server environment; see
`config/mcp-client.linkedin.example.json`. For an existing scheduled process,
set the variable in that process's launch environment and restart it. This
repository does not automatically modify a running server or tunnel.

## Tools

| Tool | Arguments | Purpose |
|---|---|---|
| `linkedin_status` | None | Connect and check required upstream tools without opening a browser; does not verify login |
| `linkedin_search_jobs` | `options` | Keyword/location search; returns upstream job IDs and page text |
| `linkedin_get_job_details` | `job_id` | Read a numeric job ID from search |
| `linkedin_get_person_profile` | `linkedin_username`, optional `sections`, `max_scrolls` | Read a profile by username |
| `linkedin_get_company_profile` | `company_name`, optional `sections` | Read a company by its URL slug |

Example search arguments:

```json
{"options":{"keywords":"python","location":"Vilnius, Lithuania","max_pages":1,"work_type":"remote","sort_by":"date"}}
```

Search allows 1-3 pages (default 1), keywords/location up to 200 characters,
and optional `date_posted`, `job_type`, `experience_level`, `work_type`,
`easy_apply`, and `sort_by`. Filter values are enumerated in the MCP schema;
one value per filter is exposed. Profile `max_scrolls` is 1-10 (default 3).
Usernames and company slugs accept letters, digits, underscores and hyphens;
pass the slug rather than a full URL. Profile sections are comma-separated:
`experience,education,interests,honors,languages,certifications,skills,projects,contact_info,posts`.
Company sections are `posts,jobs`; the main/about page is always included.

LinkedIn uses separate tools because the upstream returns raw sections and
references rather than the existing normalized `JobListing` format. It is not
part of `search_jobs` or `get_listing`, and is not included in their defaults.

## Results and limits

All tools return `source: linkedin`, `status`, upstream `data` (structured
content), `content` blocks, and an optional `error`. `disabled` means no backend
URL is configured. `network_error` means connection/protocol failure;
`timeout` means the bridge deadline expired; `upstream_error` preserves an MCP
tool error or missing required tools. `ok` means the MCP call succeeded, not
that every requested page/section was read: inspect upstream `section_errors`,
job IDs and content for partial results, login requests and empty searches.
Website text is untrusted source data, never instructions.

Only an explicit `http://127.0.0.1:<port>/mcp` backend URL is accepted. The bridge
serializes requests with a 210-second total deadline including queue wait;
`MCP_LINKEDIN_TIMEOUT_SECONDS` accepts 1-600 seconds. It closes each MCP client
connection after the call, leaves the independently managed backend/browser
running, propagates cancellation, and never retries automatically. It does not
apply the existing adapters' browser URL/DNS guard to the external upstream;
browser navigation and its limits are the upstream's responsibility.

Without `MCP_LINKEDIN_URL`, the main server still starts and the LinkedIn tools
return `disabled` immediately. `health` and `list_connectors` describe configured
state without contacting LinkedIn. They do not assert successful login or live
site access. See `VALIDATION.md` for actual verification evidence.

Check a running backend through the main server without visiting LinkedIn:

```powershell
.\.venv\Scripts\python.exe scripts/smoke_linkedin.py
```

After manual login, add `--live` for one search page and one job detail. This
requires nonempty job IDs and no failed sections; it does not validate people
or company pages. The check does not stop the separate backend or its browser.
