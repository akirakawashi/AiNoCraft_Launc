# AiNoCraft Launcher

Desktop launcher for AiNoCraft built on pywebview.

## What It Does

- Fetches aggregated startup state from `GET /api/v1/launcher/bootstrap`
  (builds catalog, storage URLs, feature flags) with a local
  `build_profiles.json` fallback when the backend is unreachable.
- Authenticates against the AiNoCraft Yggdrasil-compatible backend and
  restores/refreshes the session between launches.
- Loads the authenticated profile, avatar, and effective role from the shared
  `GET /api/v1/me` account contract using the active game access token.
- Downloads and extracts build archives directly from S3/MinIO storage.
- Compares installed build revisions with `downloads/builds.json`, installs
  updates through a staging directory, and rolls back when activation fails.
- Stores per-build settings (RAM, bounded by the machine's memory). Java is
  bundled with each build and picked automatically.
- Builds a Minecraft Java command with `authlib-injector` when an online token
  is present.
- Builds a PyInstaller executable and publishes a bootstrapper manifest through
  GitHub Actions.

## Architecture

```text
config/       # runtime.py (dev/prod resolution), constants, paths, profiles, user_prefs
core/         # auth, backend_client, downloader, game, injector, java, settings, system_info, updater
ui/api.py     # pywebview bridge (window.pywebview.api)
ui/web/       # UI: index.html + css + js (api, shell, auth, home, builds, settings, modals, app)
```

## Setup

```powershell
cd C:\AiNoCraft_Project\AiNoCraft_Launcher
pdm sync --clean --no-self
```

The project requires Python `3.12.*`; `.pdm-python` points PDM at the local `.venv`.

## Run Modes (dev / prod)

Mode resolution priority: CLI `--mode` → `AINOCRAFT_ENV` → default `prod`.

| Mode | API | Storage |
| --- | --- | --- |
| `prod` (default) | `https://api.ainocraft.com/api/v1/` | `https://storage.ainocraft.com/` |
| `dev` | `http://127.0.0.1:8000/api/v1/` | `http://127.0.0.1:9000/` |

### Dev (local backend)

```powershell
pdm run python launcher.py --mode dev
```

or:

```powershell
$env:AINOCRAFT_ENV = "dev"; pdm run python launcher.py
```

Dev mode rebases avatar URLs onto the local storage base (the backend may
advertise production storage URLs in its auth responses).

### Prod

```powershell
pdm run python launcher.py
```

The packaged production executable must be started by `AiNoCraft_Bootstrapper`.
The bootstrapper checks for updates and passes a short-lived, one-time launch
ticket. Starting `AiNoCraftLauncher.exe` directly shows an informational
message and exits. Source runs through `python launcher.py` do not require a
ticket, so the development workflow above remains unchanged.

## Data Locations

The launcher keeps its preferences, saved session, injector cache, crash log,
and temporary build downloads in `%LOCALAPPDATA%\AiNoCraft\Launcher\data`.
This is adjacent to the bootstrapper-managed `Launcher\current` directory,
but is never part of the launcher release payload.

Game builds are stored separately in `%APPDATA%\AiNoCraft\`, with one folder
per build profile — for example `%APPDATA%\AiNoCraft\AiNoCraftTech`.

The Java process output for each build is saved to
`%APPDATA%\AiNoCraft\<build folder>\logs\launcher-game.log`. The file contains
the launch time, selected Java and RAM, and Java/Minecraft console output.
Logs larger than 10 MiB are rotated with three backups.

## Build Release

```powershell
pdm run python tools/build_release.py `
  --version prod-smoke `
  --base-url https://storage.ainocraft.com/launcher/releases/prod-smoke/ `
  --release-dir release/AiNoCraftLauncher `
  --manifest release/manifest.json
```

The generated manifest uses the schema consumed by `AiNoCraft_Bootstrapper`.

## Environment Variables

- `AINOCRAFT_ENV=dev|prod` — run mode (CLI `--mode` wins)
- `AINOCRAFT_API_BASE_URL` — override the backend origin
- `AINOCRAFT_STORAGE_BASE_URL` — override the storage base URL
- `AINOCRAFT_BUILD_PROFILES=path\to\build_profiles.json` — local build catalog fallback
- `AINOCRAFT_BUILDS_MANIFEST_URL` — override the shared MinIO build revision manifest;
  defaults to `<storage-base>/downloads/builds.json`
- `AINOCRAFT_AUTHLIB_INJECTOR_JAR=path\to\authlib-injector.jar`
- `AINOCRAFT_LAUNCHER_MANIFEST_URL` — override the self-update manifest URL
- `AINOCRAFT_LAUNCHER_SELF_UPDATE=1` — enable direct launcher self-update;
  normally the bootstrapper updates the launcher before startup.

`AINOCRAFT_LAUNCH_TICKET_PATH` and `AINOCRAFT_LAUNCH_TOKEN` are reserved for
the internal bootstrapper-to-launcher handshake. Do not set or persist them in
user configuration.

## Publish Flow

`.github/workflows/publish-launcher.yml` builds the executable on Windows, generates `release/manifest.json`, uploads the artifact, then the self-hosted runner publishes:

- immutable release files under `launcher/releases/<version>/`
- stable manifest at `launcher/stable/manifest.json`

Release the bootstrapper version with launch-ticket support before publishing
a launcher build that requires the ticket. A legacy bootstrapper can download
the guarded executable, but cannot start it because it does not provide the
one-time ticket.

## Publish a Game Build

The launcher reads one shared MinIO manifest. Start from
`builds.example.json`, edit it, and publish it as `downloads/builds.json`.
Each archive must contain `ainocraft-build.json` in its root:

```json
{
  "build_id": "tech",
  "revision": "2026.07.10-01"
}
```

Each `builds.json` entry must repeat the same `revision` and carry the
archive's `sha256` (lowercase, 64 hex). The launcher verifies the downloaded
ZIP against this hash **before** extracting it; a mismatch aborts the install
and keeps the current build. In prod an entry **without** `sha256` is refused
(fail-closed); in dev mode it installs with a warning. Only `https` download
URLs are accepted (plus `http` to a loopback host for local dev).

```json
{
  "format": 1,
  "builds": {
    "tech": {
      "revision": "2026.07.10-01",
      "download_url": "downloads/AiNoCraftTech-2026.07.10-01.zip",
      "sha256": "<sha256 of the ZIP>",
      "archive_size_bytes": 2147483648,
      "unpacked_size_bytes": 7516192768
    }
  }
}
```

Publish a game update in this order:

1. Put the new `ainocraft-build.json` into the build folder.
2. Create the revisioned ZIP such as
   `downloads/AiNoCraftTech-2026.07.10-01.zip` and compute its SHA-256, e.g.
   `Get-FileHash -Algorithm SHA256 AiNoCraftTech-2026.07.10-01.zip`.
3. Upload the ZIP.
4. Put the revision, URL, `sha256`, compressed `archive_size_bytes`, and total
   ZIP-entry `unpacked_size_bytes` into `downloads/builds.json`, then upload
   it last.

The size fields are optional for compatibility with older manifests, but new
production entries should include them. The launcher always enforces its own
hard limits (16 GiB download, 64 GiB unpacked data, 250,000 entries, and 8 GiB
per file), checks available disk space, and counts bytes while extracting.
The numeric values above are illustrative and must be replaced with metadata
from the archive being published.

Configure `builds.json` with a short cache lifetime or `Cache-Control:
no-cache`. Revisioned ZIP files may use long-lived caching.

> Rollout: because prod is fail-closed, every prod `builds.json` entry must
> already carry a valid `sha256` before releasing a launcher build that
> enforces it — otherwise existing users cannot download or update.

## Публикация игровой сборки (RU): хеширование и добавление

Практическая инструкция, как посчитать хэш и добавить сборку в каталог.

### 1. Что должно быть в архиве

В **корне** ZIP:

- `ainocraft-build.json` — **валидный JSON** (с кавычками и двоеточиями!):

  ```json
  {
    "build_id": "tech",
    "revision": "2026.07.10-01"
  }
  ```

  Файл без кавычек/двоеточий лаунчер отвергнет с ошибкой «Файл ревизии
  поврежден».
- стандартная раскладка инстанса: `assets/`, `libraries/`, `versions/`, и
  папка версии `versions/<Name>/` с клиентскими `<Name>.json` и `<Name>.jar`
  (для сборки `tech` это `versions/Tech/Tech.json` и `versions/Tech/Tech.jar`).
- перед упаковкой лучше убрать личные/рантайм-файлы: `usercache.json`,
  `usernamecache.json`, `command_history.txt`, `authlib-injector.log`.

### 2. Как посчитать sha256 и размеры

```powershell
$zip = "C:\AiNoCraft_Project\AiNoCraftTech-version-0.1.0.zip"; Get-FileHash -Algorithm SHA256 $zip; (Get-Item $zip).Length

python -c "import sys, zipfile; z=zipfile.ZipFile(sys.argv[1]); print(sum(i.file_size for i in z.infolist()))" $zip
```

Скопируй значение `Hash` — это `sha256` архива (регистр неважен, лаунчер сам
приводит к нижнему). Хэш считается по **всему ZIP-файлу**, а не по файлу внутри;
если пере-зиповал архив — пересчитай. Две следующие команды выводят соответственно
`archive_size_bytes` и `unpacked_size_bytes`.

### 3. Как вписать сборку в `builds.json`

```json
{
  "format": 1,
  "builds": {
    "tech": {
      "revision": "2026.07.10-01",
      "download_url": "downloads/AiNoCraftTech-2026.07.10-01.zip",
      "sha256": "<Hash из Get-FileHash>",
      "archive_size_bytes": 2147483648,
      "unpacked_size_bytes": 7516192768
    }
  }
}
```

- `revision` **обязана совпадать** с `revision` внутри `ainocraft-build.json`.
- `sha256` — хэш из шага 2.
- `archive_size_bytes` — точный размер ZIP в байтах (`(Get-Item архив.zip).Length`).
- `unpacked_size_bytes` — сумма распакованных размеров всех записей ZIP; поля
  размеров пока опциональны для совместимости, но для новых prod-сборок их
  следует указывать. Числа в примере условные — замени их значениями своего
  архива.
- `download_url` — путь в storage, куда зальёшь ZIP (относительный от
  storage-base или полный `https://…`). Переименование файла хэш не меняет,
  пере-зиповка — меняет.

### 4. Как лаунчер проверяет сборку

1. Схема URL: `https` (или `http` только к loopback для локального dev).
2. Качает ZIP, считает sha256 на лету и сверяет с `builds.json`. Не совпало —
   установка отменяется, текущая сборка остаётся.
3. Нет `sha256` в записи: в **prod** установка запрещена (fail-closed), в **dev**
   ставится с предупреждением. Заглушка вида `0000…0000` — это **неверный** хэш
   (не «отсутствует»), такая сборка будет падать даже в dev.
4. Распаковка, сверка `revision` из архива и наличие клиентских JSON/JAR.

Перед скачиванием и распаковкой лаунчер также проверяет точные размеры из
манифеста (если заданы), жёсткие аварийные лимиты, число файлов и свободное
место. Во время загрузки и распаковки фактические байты считаются потоково —
отсутствующий или неверный `Content-Length` не обходит защиту.
5. Атомарная замена: новая сборка активна, старая уходит в бэкап и удаляется.

### 5. Порядок публикации

1. Положить валидный `ainocraft-build.json` в корень папки сборки.
2. (Опц.) удалить личные файлы (см. п.1).
3. Собрать ZIP.
4. Посчитать `sha256` (`Get-FileHash`).
5. Вписать `revision` / `download_url` / `sha256` / `archive_size_bytes` /
   `unpacked_size_bytes` в `builds.json`.
6. Залить в storage: **сначала ZIP, затем `builds.json` последним**.

> Перед выкаткой лаунчера с проверкой у **всех** прод-записей в `builds.json`
> должен быть валидный `sha256` — иначе fail-closed сломает загрузку/обновление
> у текущих пользователей.
