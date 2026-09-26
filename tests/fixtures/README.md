# Fixture provenance

Inspected on September 21, 2026. These are reduced, anonymized DOM excerpts,
not full page archives. Company names, job titles, descriptions, listing IDs,
and contact information were replaced or removed. Original Lithuanian labels,
CSS classes, salary formats, and public JSON keys remain to test parsing.
No cookies, account state, browser profiles, or Job_Seeker data are included.

| Source | Observation method | Public pages inspected |
|---|---|---|
| CVbankas | Local Playwright Chromium, headless | Keyword/city search, empty search, `/python-odoo-programuotojas-a-vilniuje/1-14111604` |
| CVmarket | Local Playwright Chromium, headless | Keyword/city search, empty search, `/flight-control-software-engineer-vilnius-alliance-recruitment-uab-2296612` |
| CVonline | Local Playwright Chromium, headless | Search form submission, `keywords[0]` search, empty search, `/lt/vacancy/1654148/naujieji-zenklai-uab/lauko-sportines-bei-laisvalaikio-irangos-montuotojas` |
| Autogidas | Public DOM inspection in the in-app browser | Search, empty search, price/year filters, page 2, `/skelbimas/cadillac-cts-2016-m-sedanas-0139917402.html` |
| Autoplius | Public DOM inspection in the in-app browser | Search, empty search, price/year filters, page 2, `/skelbimai/bmw-330-2-0-l-sedanas-2020-benzinas-elektra-31644037.html` |

The shared blocked fixture is reduced from the actual localized Cloudflare
response received by local headless Chromium on both car sites. Successful
in-app inspection is **not** evidence of successful local headless access.
The runtime never uses the in-app browser as a fallback.

The visible-session follow-up also inspected Autogidas native finance banners:
they use `a.item-link` with `rel="sponsored"` and no car title. A regression test
includes a reduced banner so it cannot invalidate an otherwise valid result page.

Autoplius color row: observed September 26, 2026 on public listing 32152464
(Volkswagen Passat). The `Spalva` parameter used the existing parameter-row,
parameter-label and parameter-value classes, with value `Pilka / sidabrinė`.
Only that nonpersonal DOM row was added to the anonymized detail fixture.
