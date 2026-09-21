# MCP Connectors

- Write all documentation, comments, application messages, commit text, and authored project text in English.
- Communicate directly with the user in Russian.
- Preserve literal source-site text only when required for parsing or fixture fidelity.

- This is a standalone project, hosted on Windows 11 with Python 3.12+.
- Start each feature/fix on a new `codex/` branch. Never commit to or merge into `main`.
- Use async Playwright's Chromium engine behind the shared browser layer. Visible installed Chrome with a dedicated persistent profile is the default; bundled Chromium and headless mode are explicit options.
- Keep verification tabs open for the user. Never automate CAPTCHA solving or import personal browser profiles.
- Keep adapters independent. Current targets: CVbankas, CVonline, Autogidas, CVmarket, Autoplius.
- Inspect `KICKOFF.md` before implementing website tools. Placeholder adapters are not working scrapers.
- Use the official MCP Python SDK v2 API. Keep stdout exclusively for MCP protocol messages.
- Never copy cookies, accounts, personal files, databases or browser profiles from Job_Seeker.
- Logs, local configuration and runtime data stay ignored by Git.
- Validate with `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1`.
- Keep dependencies small and setup reproducible; update requirements.lock when changing runtime dependencies.
