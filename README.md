# mcp-connectors

Отдельный проект headless MCP-коннекторов для Windows 11.
Текущий этап — **работающий каркас сервера**, а не готовые парсеры сайтов.

| Коннектор | Сайт | Категория | Статус |
|---|---|---|---|
| CVbankas | https://www.cvbankas.lt | Работа | Заготовка |
| CVonline | https://www.cvonline.lt | Работа | Заготовка |
| Autogidas | https://autogidas.lt | Авто | Заготовка |
| CVmarket | https://www.cvmarket.lt | Работа | Заготовка |
| Autoplius | https://autoplius.lt | Авто | Заготовка |

## Установка на Windows 11

Нужен Python 3.12+ (проверено с 3.12) и PowerShell. В терминале:

```powershell
cd C:\Users\rober\mcp-connectors
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1
```

Установка создаёт локальную `.venv`, устанавливает зависимости из `requirements.lock`,
сам проект и Chromium Playwright в профиль текущего пользователя.
Активация окружения и постоянное изменение Execution Policy не требуются.
Команды работают и из другой папки, если указать полный путь к скрипту.

## Запуск

HTTP-сервер для локального хоста Windows:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

Адрес MCP: `http://127.0.0.1:8765/mcp`. Это MCP endpoint, не веб-интерфейс.
Остановка — Ctrl+C. Для проверки из второго терминала:

```powershell
.\.venv\Scripts\python.exe .\scripts\smoke.py --http-url http://127.0.0.1:8765/mcp
```

Для клиента, запускающего MCP-процесс самостоятельно (stdio):

```powershell
.\.venv\Scripts\python.exe -m mcp_connectors --transport stdio
```

Образец конфигурации — `config/mcp-client.example.json`; поправьте абсолютный путь,
если переносите проект. Stdio-процесс ждёт протокольные сообщения, это нормально.
PowerShell launcher также принимает `-Transport stdio` и `-Port 8766`.

В текущем каркасе HTTP доступен только на loopback, без удаленной авторизации.
Внешний доступ, TLS, OAuth и постоянная служба Windows — отдельный этап перед сетевым хостингом.
Автозапуск и служба не устанавливаются скриптом setup. При будущей настройке службы
нужно установить Chromium под тем же Windows-пользователем, который запускает процесс.

## Что уже работает

- Официальный MCP Python SDK 2.2.0; transports stdio и Streamable HTTP.
- `health`: состояние сервера без запуска браузера.
- `list_connectors`: пять адаптеров со статусом `planned`.
- `browser_check`: реальный запуск Chromium и выполнение JavaScript на локальной странице.
- Playwright 1.63.0: ленивый запуск, headless по умолчанию, отдельный контекст на операцию,
  таймауты и закрытие ресурсов при остановке.
- Проверки через реальный MCP-клиент; smoke не обращается к внешним сайтам.

`search` и `get_listing` пока явно выбрасывают `NotImplementedError` в адаптерах
и **не опубликованы** как MCP tools. Живые сайты на этом этапе не проверялись.

## Настройки

Переменные окружения (в PowerShell: `$env:MCP_HEADLESS = "true"`):

| Переменная | По умолчанию | Назначение |
|---|---|---|
| MCP_HEADLESS | true | false только для локальной отладки с видимым браузером |
| MCP_BROWSER_TIMEOUT_MS | 30000 | 1000–120000 мс |
| MCP_LOCALE | lt-LT | Локаль браузерного контекста |

`.env` автоматически не загружается. Stdout зарезервирован для MCP, логи идут в stderr.
Профили, cookies и персональные данные Job Seeker сюда не копируются.

## Разработка

`src/mcp_connectors/browser.py` — общий браузерный слой.
`src/mcp_connectors/connectors/` — контракт, реестр и отдельные файлы сайтов.
`src/mcp_connectors/server.py` — MCP и lifecycle.
`KICKOFF.md` — готовый промпт следующего этапа.

Подход основан на `Job_Seeker/src/cvbankas_tracker/sources/browser_fetch.py`:
ленивый headless Chromium и изолированные адаптеры. Здесь используется async Playwright,
чтобы работать внутри async MCP runtime.

Начальная ветка — `codex/bootstrap`. Новые задачи — в отдельных `codex/*`.
Коммиты и слияния в `main` выполняет только владелец.

Ссылки по API: [MCP Python SDK](https://py.sdk.modelcontextprotocol.io/),
[Playwright Python](https://playwright.dev/python/docs/library).
