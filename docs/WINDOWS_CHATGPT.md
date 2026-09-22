# Windows home server and ChatGPT setup

This guide runs the MCP server and OpenAI tunnel client on your home Windows
host. ChatGPT can be used from another computer. Creating a tunnel in the web
dashboard does not install its client on the server.

Use Windows 11, Git, Python 3.12+, and a normal interactive Windows account.
Home servers, personal PCs, and other hosts with residential or other public
Internet connections are intended deployment targets. NAT is supported: the
tunnel uses outbound HTTPS, so no inbound port forwarding is needed. Website
access still depends on the source site's policies and your outbound IP.

Commands below use PowerShell. Copy only the contents of code blocks, without
prompts, Markdown fences, or link formatting. Run everything under the same
Windows account that will run the browser and store the tunnel credential.

## 1. Install the project

Clone the branch containing this guide until the owner merges the PR:

```powershell
cd $env:USERPROFILE
git clone --branch codex/tunnel-autostart-guide https://github.com/Yashelly/mcp-connectors.git
cd mcp-connectors
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1
```

For an existing checkout, first inspect `git status` and preserve local changes.
Then run `git fetch origin`, `git switch codex/tunnel-autostart-guide`, and the
setup/check commands above. Do not clone over an existing checkout.

Setup creates `.venv`, installs locked dependencies and bundled Chromium. No
activation or permanent execution-policy change is required. Installed Google
Chrome is the default browser; this guide explicitly uses bundled Chromium,
which also works when Google Chrome is absent.

## 2. Start MCP automatically

Stop any manual MCP process with Ctrl+C before installing the task:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\autostart.ps1 -BrowserChannel chromium
.\.venv\Scripts\python.exe .\scripts\smoke.py --http-url http://127.0.0.1:8765/mcp
```

Expect `"status": "ok"`. The endpoint is MCP, not a web page. The browser opens
when a browser operation is requested. A dedicated persistent profile stores
site sessions; never replace it with your personal browser profile. Complete
site verification manually in the visible tab. An unresolved challenge returns
`blocked`, not an empty result. Autogidas was still blocked in the last full run.

## 3. Create the OpenAI tunnel and runtime key

In the [OpenAI tunnel dashboard](https://platform.openai.com/settings/organization/tunnels),
create a tunnel named `Home MCP Connectors`, with description
`Job and car listing MCP connectors hosted on a home Windows server.`
Select the organization and associate the ChatGPT workspace you will use.
Copy the generated `tunnel_...` ID. This step can be done on your main PC.

Create a runtime key in [API keys](https://platform.openai.com/settings/organization/api-keys)
with Restricted permissions: **Tunnels: Read and Use**. The principal also needs
access to this tunnel. The daemon does not need an organization admin key or
tunnel-management permission. See [OpenAI's Secure MCP Tunnel guide](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).

On the home server, save the key using a hidden prompt:

```powershell
.\.venv\Scripts\python.exe -m mcp_connectors.tunnel --save-key
```

This stores a generic Windows credential named `Home MCP Tunnel`, username
`api_key`, for the current Windows user. If that credential already exists,
skip this step; running it again replaces the saved key. Do not paste the key
into Git, command arguments, or chat. The launcher reads it at each start and
passes it only in the child process environment. `.env` is not auto-loaded.
The runtime key authenticates the tunnel client to OpenAI; the local MCP server
does not use that key. Any plaintext file you previously created is not removed
by this installer; remove it yourself after verifying the saved credential.

## 4. Install the tunnel client

The tested client release is v0.0.14, Windows AMD64 (x64). Download the full
client, not a runtime-only archive:

```powershell
$TunnelDir = Join-Path $env:USERPROFILE 'mcp-tunnel'
New-Item -ItemType Directory -Force -Path $TunnelDir | Out-Null
Invoke-WebRequest -Uri 'https://github.com/openai/tunnel-client/releases/download/v0.0.14/tunnel-client-v0.0.14-windows-amd64.zip' -OutFile "$TunnelDir\client.zip"
$Expected = '784ab8da7b5a88f0109f1fd8aaf0a1c86067430b896dddf307ef7e3cc49fa1a5'
if ((Get-FileHash -LiteralPath "$TunnelDir\client.zip" -Algorithm SHA256).Hash -ne $Expected) { throw 'Archive checksum mismatch.' }
Expand-Archive -LiteralPath "$TunnelDir\client.zip" -DestinationPath $TunnelDir -Force
Get-ChildItem -LiteralPath $TunnelDir -Recurse -File -Filter 'tunnel-client.exe'
```

The expected executable is `$env:USERPROFILE\mcp-tunnel\tunnel-client.exe`.
If your extraction differs, supply the actual absolute path using `-ClientPath`
in the next step. Release: [v0.0.14](https://github.com/openai/tunnel-client/releases/tag/v0.0.14).

## 5. Enable tunnel autostart and recovery

Stop a manually running tunnel with Ctrl+C first, so port 8080 is available.
Leave the scheduled MCP server running. Enter your tunnel ID when prompted:

```powershell
$TunnelId = Read-Host 'Tunnel ID'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\tunnel-autostart.ps1 -TunnelId $TunnelId
```

The installer validates the executable, ID and current-user credential, writes
only nonsecret settings to ignored `tunnel.local.json`, and starts a separate
`MCP Tunnel <checkout/user hash>` task. It runs without a console window at normal
user privilege. Logs rotate in `logs/tunnel.log` (2 MB, three backups). The client
and its descendants are terminated when the task process is stopped.

Both tasks start at user logon and retry every minute if their process exits.
Running instances are not duplicated. Recovery is process-exit recovery, not a
watchdog for hung processes or a fix for invalid keys, outages or site blocking.
The tunnel can start before MCP; it remains subject to the client's connection
behavior and task retry. Check readiness after installation:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\tunnel-autostart.ps1 -Action Status
Invoke-RestMethod -Uri 'http://127.0.0.1:8080/readyz'
```

Allow startup time; expect `ready`. The optional local dashboard is
`http://127.0.0.1:8080/ui` on the server. Port 8080 is reserved for this tunnel
installation; this script does not support multiple concurrent tunnels.

**After reboot the account must sign in.** Both tasks use an interactive token.
Signing out or sleeping makes this deployment unavailable. Keep the host awake.
These scripts do not configure automatic Windows login or store the Windows
account password. A visible browser cannot run as a Session 0 service. Windows
Server editions and reboot/sign-out behavior have not been validated here.

## 6. Connect ChatGPT

On your main PC, open ChatGPT in the workspace associated with the tunnel:

1. Enable **Settings > Security and login > Developer mode** (subject to account
   and workspace availability).
2. Open **Plugins**, select **+**, and name the connection `Home MCP Connectors`.
3. Set **Connection: Tunnel**, select your tunnel, and set
   **Authentication: No authentication / None** for this local MCP server.
4. Create the connection and review the discovered tools.
5. Start a new chat, select the connection in the tools menu, and request:
   `Call health and list_connectors. Then find five Python jobs in Vilnius on CVbankas.`

Do not select OAuth: this MCP server does not implement it. The private tunnel's
runtime key and workspace association are separate from upstream MCP OAuth.
See the [official ChatGPT connection guide](https://developers.openai.com/plugins/deploy/connect-chatgpt).

The deployment session confirmed `ready` and user-reported successful ChatGPT
calls to health, connector listing, and CVbankas search on September 22, 2026.
That does not establish live availability for every source.

## Operations and troubleshooting

Use the same account and checkout for all management commands:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\tunnel-autostart.ps1 -Action Stop
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\tunnel-autostart.ps1 -Action Start
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\tunnel-autostart.ps1 -Action Remove
```

`Stop` disables recovery before stopping; `Start` re-enables it. `Remove` keeps
the credential, local configuration and logs. Use `autostart.ps1` with the same
actions to manage MCP. Re-run tunnel installation without `-TunnelId` to reuse
saved settings, or provide ID, `-ClientPath` and optional `-Port` to replace them.
After updating the saved key, stop/start the tunnel to load it. Stop both tasks
before upgrading dependencies; start MCP first and then the tunnel.

| Symptom | Action |
|---|---|
| `Error fetching OAuth configuration` | Choose None for MCP authentication in ChatGPT; do not change the runtime key. |
| Credential preflight fails | Use the same Windows account that saved `Home MCP Tunnel`; save a replacement key if necessary. |
| Tunnel unavailable in ChatGPT | Check its workspace association and runtime principal's Read/Use permissions. |
| Port 8080 already in use | Stop the manual tunnel or other known owner before enabling the task. |
| `/readyz` fails | Read `logs/tunnel.log`; check MCP smoke, network access and API permissions. |
| Task is Running but calls fail | Task state is not endpoint health; test readiness and MCP independently. |
| LastTaskResult is 267009 | This is Windows `0x41301` (task currently running), not a failure. |
| Browser verification loops | Keep the tab available, complete it manually, retry; report persistent blocking honestly. |
| Chrome missing | Install MCP task with `-BrowserChannel chromium`. |
| Folder not found / unrelated recursive access errors | Verify the exact directory with `Test-Path -LiteralPath`; create/extract the client folder before searching it. |
| PowerShell shows Markdown, `>` or a formatted URL | Cancel with Ctrl+C and paste only executable code from the code block. |

Do not publish unreviewed runtime logs: they can contain listing data and host
metadata. Logs, profiles, credentials and `*.local.*` configuration are not
version-controlled.

For a local task recovery smoke test, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_tunnel_autostart.ps1
```

This creates a temporary task and a dummy client, checks restart after client
termination and cleanup when the task stops, then removes its task and temporary
files. It does not read your API key or contact OpenAI. Allow about two minutes.
Use an elevated PowerShell under the same user if task policy requires it.
