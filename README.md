# AI-Tutor

[🇷🇺 Русский](#-русская-версия) · [🇬🇧 English](#-english-version)

---

<a id="-english-version"></a>

## 🇬🇧 English version

### Contents

- [What it is](#what-it-is)
- [Current state](#current-state)
- [Architecture](#architecture)
- [Stack](#stack)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Repository structure](#repository-structure)
- [Cases and content](#cases-and-content)
- [Admin panel](#admin-panel)
- [HTTP API](#http-api)
- [FSM: domain model](#fsm-domain-model)
- [Development](#development)
- [Testing](#testing)
- [Deployment](#deployment)
- [Documentation](#documentation)
- [Roadmap](#roadmap)
- [License](#license)

---

### What it is

An AI mentor for training the bank's client managers to sell banking products in an interactive simulator format.

The employee trains to sell a banking product in the following modes:

| Mode | Who plays the AI role | Who plays the user role |
|---|---|---|
| **Training** (TRAINING) | Instructor | Student (answers the quiz) |
| **Example** (EXAMPLE) | Bank employee | Client |
| **Practice** (PRACTICE) | Client | Bank employee (evaluated by LLM) |
| **Knowledge** (KNOWLEDGE) | Instructor of weak zones | Student |

If Practice is unsuccessful, the loop **Example → Practice → Knowledge** runs until success. See [`docs/SCOPE.md`](docs/SCOPE.md) for details.

The simulator supports multiple cases (products / sales methodologies) — see [Cases and content](#cases-and-content).

---

### Current state

| Component | State |
|---|---|
| Domain (states, events, transitions, context) | ✅ ready |
| Application (FSMService, SessionRunner, commands, effects, ports) | ✅ ready |
| Persistence (sessions) | ⚠️ in-memory (`InMemorySessionStore`); Postgres — queued |
| Prompt storage | ✅ file-based `PromptStore` (`var/prompts/templates.json`) |
| LLM | ✅ GigaChat adapters (avatar, answer_checker, practice_evaluator, quiz_director, stage_director) + stubs for tests/offline |
| TTS | ✅ SaluteSpeech + `NullTTS` (fallback), file-based audio cache |
| STT | ✅ SaluteSpeech (`/api/stt`) + Web Speech API as fallback |
| Case content | ✅ multi-case (`dialogues.md`, `facts.md`, `checklist.json`) + `default/` references |
| Web UI | ✅ welcome + session (avatar, audio player, PDF presentations) |
| Web API | ✅ `/api/sessions/*`, `/api/audio/{key}`, `/api/stt` |
| Admin panel | ✅ prompts, modes, quiz, stage_director, checklists, case files (upload/download/restore) |
| Deployment | ✅ Docker + docker-compose + nginx + certbot (Let's Encrypt) |

---

### Architecture

Layered, with the dependency rule pointing inward:

```
infrastructure ──▶ application ──▶ domain
       │                │
       └── composition (DI/assembly)
```

**Key rules:**

| Layer | Async? | I/O? | May import |
|---|---|---|---|
| `domain/` | no | no | — |
| `application/` | no | no (effects only) | `domain/` |
| `infrastructure/` | yes | yes | `domain/`, `application/` |
| `composition/` | yes | yes | everything |

**FSMService** is a synchronous pure function: `(state, command, ctx) → (new_state, new_ctx, effects)`. No LLM/DB calls from the FSM; side effects are expressed as effects and executed by adapters.

**SessionRunner** is an async coordinator: loads the snapshot, invokes FSMService, executes effects (persist, LLM calls through ports, TTS synthesis, audio cache), and returns the enriched result.

**Ports** (`application/ports/`): `avatar`, `answer_checker`, `practice_evaluator`, `quiz_director`, `stage_director`, `session_store`, `tts_client`, `stt_client`. Each has a real adapter (`gigachat_*` / `salute_speech`) and a test adapter (`stub_*` / `null_*`).

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for details.

---

### Stack

| Purpose | Technology |
|---|---|
| Language | Python **3.13** |
| Package manager | Poetry |
| Web | FastAPI + Uvicorn |
| Templates | Jinja2 |
| Validation | Pydantic v2, pydantic-settings |
| HTTP client | httpx |
| Multipart forms | python-multipart |
| LLM | GigaChat (`gigachat`) + stubs |
| TTS / STT | SaluteSpeech REST |
| Session storage | in-memory (planned: PostgreSQL) |
| Prompt storage | file-based JSON (`var/prompts/`) |
| Tests | pytest, pytest-asyncio, pytest-cov |
| Quality | ruff (lint+format), mypy strict, pre-commit |
| Deployment | Docker, docker-compose, nginx, certbot |

---

### Quick start

#### Requirements

- Python 3.13
- Poetry ≥ 2.0
- (optional) SaluteSpeech / GigaChat keys — without them the UI runs in text mode on stubs

#### Installation

```bash
git clone <repo-url> ai-tutor
cd ai-tutor
poetry install
poetry run pre-commit install
cp .env.example .env
# edit .env: SaluteSpeech / GigaChat keys (or leave them empty)
```

#### Running the dev server

```bash
poetry run python -m src
```

Or via uvicorn:

```bash
poetry run uvicorn composition.app:create_app --factory --reload --app-dir src
```

It will open at `http://127.0.0.1:8000/`.

---

### Configuration

All settings are read from `.env` (see `.env.example`). The application starts even without `.env`: TTS/STT/LLM degrade to fallbacks.

| Variable | Purpose | Default |
|---|---|---|
| `SALUTESPEECH_API_KEY` | Authorization key (Basic) | empty = TTS/STT off |
| `SALUTESPEECH_SCOPE` | OAuth scope | `SALUTE_SPEECH_PERS` |
| `SALUTESPEECH_VOICE` | Speaker voice | `Bys_24000` |
| `SALUTESPEECH_FORMAT` | Audio format | `wav16` |
| `SALUTESPEECH_CA_BUNDLE` | Path to the Ministry of Digital Development root CA | `russian_trusted_root_ca.cer` |
| `SALUTESPEECH_ENABLED` | Global TTS toggle | `true` |
| `TTS_CACHE_DIR` | File-based audio cache directory | `var/tts` |

> GigaChat keys and admin access — see `.env.example` and `infrastructure/config.py` / `infrastructure/web/security.py`.

The "Russian Trusted Root CA" certificate is required to call `*.sberbank.ru` — it lives in the repository root.

---

### Repository structure

```
src/
├── domain/                  # FSM core: states, events, transitions, context, types
├── application/             # FSMService, SessionRunner, commands, effects
│   └── ports/               # Protocol interfaces for adapters
├── infrastructure/
│   ├── config.py            # settings (pydantic-settings)
│   ├── content/             # cases and checklists
│   │   ├── registry.py      # registry of available cases
│   │   ├── case_loader.py   # read/write/restore case files
│   │   └── cases/<case>/    # dialogues.md, facts.md, checklist.json (+ default/)
│   ├── llm/                 # gigachat_* adapters + stub_* + prompt_store + content_render
│   ├── tts/                 # salute_speech, null_tts, audio_cache, cache_cleaner
│   ├── stt/                 # salute_speech, null_stt
│   ├── persistence/         # in_memory_session_store
│   └── web/                 # FastAPI routes, templates, static
│       ├── routes_api.py    # /api/*
│       ├── routes_ui.py     # / (welcome, session)
│       ├── routes_admin.py  # /admin/*
│       ├── command_mapper.py, schemas.py, serializers.py, security.py
│       ├── templates/       # welcome.html, session.html, admin_prompts.html
│       └── static/          # app.js, welcome.js, styles.css, admin.css, fonts, PDF presentations
└── composition/             # application assembly (DI)

tests/
├── unit/                    # domain, application, infrastructure (llm/tts/web/content)
├── integration/web/         # web API via httpx.AsyncClient
└── fakes/                   # test doubles

deploy/                      # nginx, certbot, scripts (deploy.sh, init-letsencrypt.sh)
docs/                        # ARCHITECTURE, SCOPE, ROADMAP, FSM_*, DEPLOY, DECISIONS, adr/
scripts/                     # dump.sh
var/
├── prompts/templates.json   # file-based prompt storage
└── tts/                     # synthesized audio cache (gitignore)
Dockerfile, docker-compose.yml
```

---

### Cases and content

Available cases (`src/infrastructure/content/cases/`):

| case_id | Purpose |
|---|---|
| `cc_novichok` | Credit card, newcomer (basic) |
| `aida` | AIDA methodology |
| `pusk` | PUSK methodology |
| `spin` | SPIN methodology |
| `storytelling` | Storytelling |
| `xpv` | XPV methodology |

Each case contains three editable files:

- `dialogues.md` — example dialogues;
- `facts.md` — facts about the product/methodology;
- `checklist.json` — practice evaluation checklist by zones (`needs`, `pitch`, `conditions`).

Reference versions are stored under `<case>/default/` and are used for restoration through the admin panel. Read/write/cache invalidation — `infrastructure/content/case_loader.py`; case registry — `registry.py`.

---

### Admin panel

Access is protected by `require_admin` (`infrastructure/web/security.py`). Template — `admin_prompts.html`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin/prompts` | Editor for prompts/modes/quiz/checklists (case selection via query `case_id`) |
| `POST` | `/admin/prompts` | Save system prompt, state templates, mode prompts, quiz, stage_director |
| `GET` | `/admin/case/{case_id}/{file_key}` | Download case file (`dialogues`/`facts`/`checklist`) |
| `POST` | `/admin/case/{case_id}/{file_key}` | Upload case file (UTF-8, ≤ 1 MB) |
| `POST` | `/admin/case/{case_id}/{file_key}/restore` | Restore file from `default/` |
| `POST` | `/admin/case/{case_id}/checklist/edit` | Save/add/remove checklist items |
| `POST` | `/admin/prompts/{case_id}/mode/{mode_key}/restore` | Restore default mode prompt |
| `POST` | `/admin/prompts/{case_id}/quiz/restore` | Restore default quiz prompt |

Prompts are stored in `var/prompts/templates.json` via `PromptStore` (`infrastructure/llm/prompt_store.py`). Defaults — `infrastructure/llm/default_prompts.py`.

---

### HTTP API

Prefix — `/api`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/sessions` | Create a session, get the avatar's first reply |
| `GET` | `/api/sessions/{id}` | Get the current session state |
| `POST` | `/api/sessions/{id}/commands` | Send a command to the FSM |
| `GET` | `/api/audio/{key}` | Get cached TTS audio |
| `POST` | `/api/stt` | Recognize speech (SaluteSpeech) |
| `GET` | `/` | Simulator UI (welcome) |

**Command format:**

```json
{ "command": { "type": "SelectMode", "mode": "training" } }
```

Mapping of API command types to `application.commands.*` — in `infrastructure/web/command_mapper.py`.

---

### FSM: domain model

#### States

`INIT`, `RESUME_PROMPT`, `MENU`, `WELCOME`, `SKIP_WARNING_1/2`, `TRAINING`, `TRAINING_QUIZ`, `TRAINING_EXPLAIN`, `TRAINING_DONE`, `EXAMPLE`, `EXAMPLE_DONE`, `PRACTICE`, `PRACTICE_EVAL`, `PRACTICE_PARTIAL`, `PRACTICE_SUCCESS`, `KNOWLEDGE`, `KNOWLEDGE_DONE`, `FINISH`.

#### Principles

1. **Pure transition table.** `(state, event) → state` without reading the context (`domain/transitions.py`).
2. **Guards live in FSMService.** The context only influences event selection, not the transition outcome.
3. **LLM verdict as a fact.** Commands carry the ready-made decision (`SubmitQuizAnswer(correct=bool)`, `PracticeEvaluated(weak_zones=...)`) rather than raw text. See [ADR-004](docs/adr/ADR-004-llm-verdict-as-fact.md).
4. **Dynamic transition as a special case.** `RESUME_CONFIRMED` → `ctx.saved_state`; it is not part of the table and is handled explicitly.
5. **No remediation loop limits.** `cycle_count` is an observer, not a controller. See [ADR-005](docs/adr/ADR-005-no-cycle-limits.md).

The full Mermaid diagram and transition table — in [`docs/FSM_DESIGN.md`](docs/FSM_DESIGN.md).

---

### Development

#### Lint and format

```bash
poetry run ruff check .
poetry run ruff format .
```

#### Types

```bash
poetry run mypy
```

Strict mode (`strict = true`); tests are softer (see `[[tool.mypy.overrides]]` in `pyproject.toml`).

#### Pre-commit

```bash
poetry run pre-commit run --all-files
```

#### Code conventions

- Lines up to 100 characters.
- Double quotes.
- Imports sorted by ruff (`I`-rules).
- All public functions/classes have docstrings and type hints.
- In `domain/` and `application/` — no `async`, no external imports beyond the standard library and domain.

---

### Testing

```bash
poetry run pytest                       # all tests
poetry run pytest tests/unit            # unit only
poetry run pytest tests/integration     # integration only
poetry run pytest --cov=src --cov-report=term-missing
```

Test structure:

- `tests/unit/domain/` — states, events, transitions, context;
- `tests/unit/application/` — FSMService (by command groups), SessionRunner;
- `tests/unit/infrastructure/` — llm (avatar, checker, prompt_store, content_render), tts (cache, cleaner, null), web (routes_admin, schemas), content (cases, checklists);
- `tests/integration/web/` — web API via `httpx.AsyncClient`.

Markers:

| Marker | Purpose |
|---|---|
| `unit` | Fast, no I/O |
| `integration` | Web API via `httpx.AsyncClient` |

---

### Deployment

Artifacts in `deploy/` + `Dockerfile` + `docker-compose.yml`.

- `deploy/nginx/` — reverse-proxy config (`fppzo.ru.conf`, `nginx.conf`);
- `deploy/certbot/` — Let's Encrypt configuration;
- `deploy/scripts/deploy.sh` — deployment;
- `deploy/scripts/init-letsencrypt.sh` — first-time TLS certificate issuance.

Full instructions — [`docs/DEPLOY.md`](docs/DEPLOY.md).

#### Safe redeploy script

```bash
(
  set -Eeuo pipefail
  umask 077
  cd /root/ai-tutor

  exec 9>/root/ai-tutor-deploy.lock
  flock -n 9 || { echo "Another update is running."; exit 1; }

  command -v python3 >/dev/null
  docker compose version >/dev/null
  docker inspect ai-tutor-app >/dev/null

  var_source=$(docker inspect ai-tutor-app --format '{{range .Mounts}}{{if eq .Destination "/app/var"}}{{.Source}}{{end}}{{end}}')
  test "$var_source" = "/root/ai-tutor/var" || { echo "ERROR: unexpected /app/var mount: $var_source"; exit 1; }

  backup_dir=$(mktemp -d /root/ai-tutor-backup.XXXXXXXX)
  mkdir -p "$backup_dir/cases" "$backup_dir/var" "$backup_dir/verify"

  echo "Backup: $backup_dir"

  trap '
    rc=$?
    echo "ERROR: update interrupted, code $rc. Backup: $backup_dir"
    echo "Check: docker compose ps -a"
    exit "$rc"
  ' ERR

  # Stop the app before syncing
  docker compose stop app

  # Preserve current materials and prompts
  docker cp -a ai-tutor-app:/app/src/infrastructure/content/cases/. "$backup_dir/cases/" || true
  docker cp -a ai-tutor-app:/app/var/. "$backup_dir/var/" || true

  # Sanity-check key files
  test -f "$backup_dir/cases/products.json" || echo "Warning: products.json not found in backup"
  test -f "$backup_dir/var/prompts/templates.json" || echo "Warning: templates.json not found in backup"

  # Pull changes from the repository
  git fetch origin feature/multi-products
  git reset --hard FETCH_HEAD

  # Build the new image
  docker compose build app

  # Create the new container WITHOUT starting it
  docker compose up --no-start --no-deps --no-build --force-recreate app

  # Restore materials into the stopped container
  docker cp -a "$backup_dir/cases/." ai-tutor-app:/app/src/infrastructure/content/cases/ || true

  # var is already bind-mounted on the host, do not overwrite

  # Verify restored files before starting
  mkdir -p "$backup_dir/verify/cases"
  docker cp -a ai-tutor-app:/app/src/infrastructure/content/cases/. "$backup_dir/verify/cases/" || true

  if [ -f "$backup_dir/cases/products.json" ] && [ -f "$backup_dir/verify/cases/products.json" ]; then
    if ! cmp -s "$backup_dir/cases/products.json" "$backup_dir/verify/cases/products.json"; then
      echo "ERROR: products.json does not match after restore"
      exit 1
    fi
  fi

  # Start the new version
  docker compose start app
  sleep 5

  docker compose ps app
  docker compose logs --tail=50 app

  echo
  echo "✓ New version deployed. Please verify availability and functionality."
  echo "  Backup saved: $backup_dir"
  echo "  Remove it after verification: rm -rf $backup_dir"
)
```

---

### Documentation

| Document | Contents |
|---|---|
| [`docs/SCOPE.md`](docs/SCOPE.md) | What is and is **not** in the MVP |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Layers, dependency rules, control flow |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Slices 1–9 |
| [`docs/FSM_DESIGN.md`](docs/FSM_DESIGN.md) | Full map of states, events, transitions, Mermaid |
| [`docs/FSM_INVARIANTS.md`](docs/FSM_INVARIANTS.md) | Which event changes which context fields |
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | Deployment to a VPS (Docker, nginx, TLS) |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Architectural decisions log |
| `docs/adr/ADR-004…012` | Specific accepted decisions |

---

### Roadmap

| Slice | Purpose | Status |
|---|---|---|
| 1 | In-memory FSM core | ✅ |
| 2 | Persistence (Postgres + Alembic) | queued |
| 3 | LLM stub with effects | ✅ |
| 4 | Minimal HTTP API | ✅ |
| 5 | Simulator UI | ✅ |
| 6 | Real GigaChat | ✅ |
| 7 | Voice (TTS + STT) | ✅ |
| 8 | Prompts and cases admin | ✅ |
| 9 | Deployment to a VPS | ✅ |

---

### License

Released under the [MIT License](LICENSE).

You are free to use, modify, and distribute this code, including for commercial purposes, provided that the license text and copyright notice are preserved.

[⬆ Back to top](#ai-tutor)

---

<a id="-русская-версия"></a>

## 🇷🇺 Русская версия

### Содержание

- [Что это](#что-это)
- [Текущее состояние](#текущее-состояние)
- [Архитектура](#архитектура)
- [Стек](#стек)
- [Быстрый старт](#быстрый-старт)
- [Конфигурация](#конфигурация)
- [Структура репозитория](#структура-репозитория)
- [Кейсы и контент](#кейсы-и-контент)
- [Админка](#админка)
- [HTTP API](#http-api-1)
- [FSM: модель домена](#fsm-модель-домена)
- [Разработка](#разработка)
- [Тестирование](#тестирование)
- [Деплой](#деплой)
- [Документация](#документация)
- [Дорожная карта](#дорожная-карта)
- [Лицензия](#лицензия)

---

### Что это

AI-наставник для обучения клиентских менеджеров банка продажам банковских продуктов в формате интерактивного тренажёра.

Сотрудник банка тренируется продавать банковский продукт в режимах:

| Режим | Кто играет роль AI | Кто играет роль пользователя |
|---|---|---|
| **Обучение** (TRAINING) | Преподаватель | Ученик (отвечает на квиз) |
| **Пример** (EXAMPLE) | Сотрудник банка | Клиент |
| **Практика** (PRACTICE) | Клиент | Сотрудник банка (оценивается LLM) |
| **Знание** (KNOWLEDGE) | Преподаватель западающих зон | Ученик |

При неуспешной Практике запускается петля **Пример → Практика → Знание** до успеха. Подробнее — [`docs/SCOPE.md`](docs/SCOPE.md).

Тренажёр поддерживает несколько кейсов (продуктов/методик продаж) — см. [Кейсы и контент](#кейсы-и-контент).

---

### Текущее состояние

| Компонент | Состояние |
|---|---|
| Domain (states, events, transitions, context) | ✅ готов |
| Application (FSMService, SessionRunner, commands, effects, ports) | ✅ готов |
| Persistence (сессии) | ⚠️ in-memory (`InMemorySessionStore`); Postgres — в очереди |
| Хранилище промптов | ✅ файловый `PromptStore` (`var/prompts/templates.json`) |
| LLM | ✅ GigaChat-адаптеры (avatar, answer_checker, practice_evaluator, quiz_director, stage_director) + стабы для тестов/офлайна |
| TTS | ✅ SaluteSpeech + `NullTTS` (фолбэк), файловый кэш аудио |
| STT | ✅ SaluteSpeech (`/api/stt`) + Web Speech API как fallback |
| Контент кейсов | ✅ multi-case (`dialogues.md`, `facts.md`, `checklist.json`) + эталоны `default/` |
| Web UI | ✅ welcome + session (аватар, аудиоплеер, презентации PDF) |
| Web API | ✅ `/api/sessions/*`, `/api/audio/{key}`, `/api/stt` |
| Админка | ✅ промпты, режимы, квиз, stage_director, чек-листы, файлы кейса (upload/download/restore) |
| Деплой | ✅ Docker + docker-compose + nginx + certbot (Let's Encrypt) |

---

### Архитектура

Слоистая, dependency rule направлен внутрь:

```
infrastructure ──▶ application ──▶ domain
       │                │
       └── composition (DI/сборка)
```

**Ключевые правила:**

| Слой | Async? | I/O? | Может импортировать |
|---|---|---|---|
| `domain/` | нет | нет | — |
| `application/` | нет | нет (только эффекты) | `domain/` |
| `infrastructure/` | да | да | `domain/`, `application/` |
| `composition/` | да | да | всё |

**FSMService** — синхронная чистая функция: `(state, command, ctx) → (new_state, new_ctx, effects)`. Никаких вызовов LLM/БД из FSM, побочные действия выражаются эффектами и исполняются адаптерами.

**SessionRunner** — async-координатор: загружает снапшот, вызывает FSMService, исполняет эффекты (persist, LLM-вызовы через порты, TTS-синтез, кэш аудио), возвращает обогащённый результат.

**Порты** (`application/ports/`): `avatar`, `answer_checker`, `practice_evaluator`, `quiz_director`, `stage_director`, `session_store`, `tts_client`, `stt_client`. Для каждого — реальный (`gigachat_*` / `salute_speech`) и тестовый (`stub_*` / `null_*`) адаптеры.

Подробнее — [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

### Стек

| Назначение | Технология |
|---|---|
| Язык | Python **3.13** |
| Менеджер пакетов | Poetry |
| Web | FastAPI + Uvicorn |
| Шаблоны | Jinja2 |
| Валидация | Pydantic v2, pydantic-settings |
| HTTP-клиент | httpx |
| Формы (multipart) | python-multipart |
| LLM | GigaChat (`gigachat`) + стабы |
| TTS / STT | SaluteSpeech REST |
| Хранилище сессий | in-memory (план: PostgreSQL) |
| Хранилище промптов | файловый JSON (`var/prompts/`) |
| Тесты | pytest, pytest-asyncio, pytest-cov |
| Качество | ruff (lint+format), mypy strict, pre-commit |
| Деплой | Docker, docker-compose, nginx, certbot |

---

### Быстрый старт

#### Требования

- Python 3.13
- Poetry ≥ 2.0
- (опционально) ключи SaluteSpeech / GigaChat — без них UI работает в текстовом режиме на стабах

#### Установка

```bash
git clone <repo-url> ai-tutor
cd ai-tutor
poetry install
poetry run pre-commit install
cp .env.example .env
# отредактируй .env: ключи SaluteSpeech / GigaChat (или оставь пустыми)
```

#### Запуск dev-сервера

```bash
poetry run python -m src
```

Или через uvicorn:

```bash
poetry run uvicorn composition.app:create_app --factory --reload --app-dir src
```

Откроется на `http://127.0.0.1:8000/`.

---

### Конфигурация

Все настройки — через `.env` (см. `.env.example`). Приложение запускается даже без `.env`: TTS/STT/LLM деградируют к фолбэкам.

| Переменная | Назначение | Дефолт |
|---|---|---|
| `SALUTESPEECH_API_KEY` | Ключ авторизации (Basic) | пусто = TTS/STT off |
| `SALUTESPEECH_SCOPE` | OAuth scope | `SALUTE_SPEECH_PERS` |
| `SALUTESPEECH_VOICE` | Голос диктора | `Bys_24000` |
| `SALUTESPEECH_FORMAT` | Формат аудио | `wav16` |
| `SALUTESPEECH_CA_BUNDLE` | Путь к корневому CA Минцифры | `russian_trusted_root_ca.cer` |
| `SALUTESPEECH_ENABLED` | Глобальный выключатель TTS | `true` |
| `TTS_CACHE_DIR` | Директория файлового кэша аудио | `var/tts` |

> GigaChat-ключи и admin-доступ см. в `.env.example` и `infrastructure/config.py` / `infrastructure/web/security.py`.

Сертификат «Russian Trusted Root CA» нужен для обращения к `*.sberbank.ru` — лежит в корне репозитория.

---

### Структура репозитория

```
src/
├── domain/                  # FSM-ядро: states, events, transitions, context, types
├── application/             # FSMService, SessionRunner, commands, effects
│   └── ports/               # Protocol-интерфейсы адаптеров
├── infrastructure/
│   ├── config.py            # настройки (pydantic-settings)
│   ├── content/             # кейсы и чек-листы
│   │   ├── registry.py      # реестр доступных кейсов
│   │   ├── case_loader.py   # чтение/запись/restore файлов кейса
│   │   └── cases/<case>/    # dialogues.md, facts.md, checklist.json (+ default/)
│   ├── llm/                 # gigachat_* адаптеры + stub_* + prompt_store + content_render
│   ├── tts/                 # salute_speech, null_tts, audio_cache, cache_cleaner
│   ├── stt/                 # salute_speech, null_stt
│   ├── persistence/         # in_memory_session_store
│   └── web/                 # FastAPI-роуты, шаблоны, статика
│       ├── routes_api.py    # /api/*
│       ├── routes_ui.py     # / (welcome, session)
│       ├── routes_admin.py  # /admin/*
│       ├── command_mapper.py, schemas.py, serializers.py, security.py
│       ├── templates/       # welcome.html, session.html, admin_prompts.html
│       └── static/          # app.js, welcome.js, styles.css, admin.css, шрифты, PDF-презентации
└── composition/             # сборка приложения (DI)

tests/
├── unit/                    # domain, application, infrastructure (llm/tts/web/content)
├── integration/web/         # web API через httpx.AsyncClient
└── fakes/                   # тестовые двойники

deploy/                      # nginx, certbot, scripts (deploy.sh, init-letsencrypt.sh)
docs/                        # ARCHITECTURE, SCOPE, ROADMAP, FSM_*, DEPLOY, DECISIONS, adr/
scripts/                     # dump.sh
var/
├── prompts/templates.json   # файловое хранилище промптов
└── tts/                     # кэш синтезированного аудио (gitignore)
Dockerfile, docker-compose.yml
```

---

### Кейсы и контент

Доступные кейсы (`src/infrastructure/content/cases/`):

| case_id | Назначение |
|---|---|
| `cc_novichok` | Кредитная карта, новичок (базовый) |
| `aida` | Методика AIDA |
| `pusk` | Методика ПУСК |
| `spin` | Методика SPIN |
| `storytelling` | Сторителлинг |
| `xpv` | Методика ХПВ |

Каждый кейс содержит три редактируемых файла:

- `dialogues.md` — примеры диалогов;
- `facts.md` — факты о продукте/методике;
- `checklist.json` — чек-лист оценки практики по зонам (`needs`, `pitch`, `conditions`).

Эталонные версии хранятся в `<case>/default/` и используются для восстановления через админку. Чтение/запись/инвалидация кэша — `infrastructure/content/case_loader.py`; реестр кейсов — `registry.py`.

---

### Админка

Доступ — через `require_admin` (`infrastructure/web/security.py`). Шаблон — `admin_prompts.html`.

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/admin/prompts` | Редактор промптов/режимов/квиза/чек-листов (выбор кейса через query `case_id`) |
| `POST` | `/admin/prompts` | Сохранить system-промпт, шаблоны состояний, промпты режимов, квиз, stage_director |
| `GET` | `/admin/case/{case_id}/{file_key}` | Скачать файл кейса (`dialogues`/`facts`/`checklist`) |
| `POST` | `/admin/case/{case_id}/{file_key}` | Загрузить файл кейса (UTF-8, ≤ 1 МБ) |
| `POST` | `/admin/case/{case_id}/{file_key}/restore` | Восстановить файл из `default/` |
| `POST` | `/admin/case/{case_id}/checklist/edit` | Сохранить/добавить/удалить элементы чек-листа |
| `POST` | `/admin/prompts/{case_id}/mode/{mode_key}/restore` | Восстановить промпт режима по умолчанию |
| `POST` | `/admin/prompts/{case_id}/quiz/restore` | Восстановить промпт квиза по умолчанию |

Промпты хранятся в `var/prompts/templates.json` через `PromptStore` (`infrastructure/llm/prompt_store.py`). Дефолты — `infrastructure/llm/default_prompts.py`.

---

### HTTP API

Префикс — `/api`.

| Метод | Путь | Назначение |
|---|---|---|
| `POST` | `/api/sessions` | Создать сессию, получить первую реплику аватара |
| `GET` | `/api/sessions/{id}` | Получить текущее состояние сессии |
| `POST` | `/api/sessions/{id}/commands` | Отправить команду в FSM |
| `GET` | `/api/audio/{key}` | Получить кэшированное TTS-аудио |
| `POST` | `/api/stt` | Распознать речь (SaluteSpeech) |
| `GET` | `/` | UI тренажёра (welcome) |

**Формат команды:**

```json
{ "command": { "type": "SelectMode", "mode": "training" } }
```

Маппинг типов команд из API в `application.commands.*` — в `infrastructure/web/command_mapper.py`.

---

### FSM: модель домена

#### Состояния

`INIT`, `RESUME_PROMPT`, `MENU`, `WELCOME`, `SKIP_WARNING_1/2`, `TRAINING`, `TRAINING_QUIZ`, `TRAINING_EXPLAIN`, `TRAINING_DONE`, `EXAMPLE`, `EXAMPLE_DONE`, `PRACTICE`, `PRACTICE_EVAL`, `PRACTICE_PARTIAL`, `PRACTICE_SUCCESS`, `KNOWLEDGE`, `KNOWLEDGE_DONE`, `FINISH`.

#### Принципы

1. **Чистая таблица переходов.** `(state, event) → state` без чтения контекста (`domain/transitions.py`).
2. **Guards в FSMService.** Контекст влияет только на выбор события, не на исход перехода.
3. **LLM-вердикт как факт.** Команды несут готовое решение (`SubmitQuizAnswer(correct=bool)`, `PracticeEvaluated(weak_zones=...)`), а не сырой текст. См. [ADR-004](docs/adr/ADR-004-llm-verdict-as-fact.md).
4. **Динамический переход — спецслучай.** `RESUME_CONFIRMED` → `ctx.saved_state`; в таблицу не входит, обрабатывается явно.
5. **Без лимитов петли ремедиации.** `cycle_count` — наблюдатель, не контроллер. См. [ADR-005](docs/adr/ADR-005-no-cycle-limits.md).

Полная Mermaid-диаграмма и таблица переходов — в [`docs/FSM_DESIGN.md`](docs/FSM_DESIGN.md).

---

### Разработка

#### Линтер и формат

```bash
poetry run ruff check .
poetry run ruff format .
```

#### Типы

```bash
poetry run mypy
```

Строгий режим (`strict = true`); тесты — мягче (см. `[[tool.mypy.overrides]]` в `pyproject.toml`).

#### Pre-commit

```bash
poetry run pre-commit run --all-files
```

#### Соглашения по коду

- Строки до 100 символов.
- Кавычки — двойные.
- Импорты сортирует ruff (`I`-rules).
- Все публичные функции/классы — с docstring и type hints.
- В `domain/` и `application/` — никаких `async`, никаких внешних импортов кроме стандартной библиотеки и domain.

---

### Тестирование

```bash
poetry run pytest                       # все тесты
poetry run pytest tests/unit            # только юнит
poetry run pytest tests/integration     # только интеграционные
poetry run pytest --cov=src --cov-report=term-missing
```

Структура тестов:

- `tests/unit/domain/` — состояния, события, переходы, контекст;
- `tests/unit/application/` — FSMService (по группам команд), SessionRunner;
- `tests/unit/infrastructure/` — llm (avatar, checker, prompt_store, content_render), tts (cache, cleaner, null), web (routes_admin, схемы), content (кейсы, чек-листы);
- `tests/integration/web/` — web API через `httpx.AsyncClient`.

Маркеры:

| Маркер | Назначение |
|---|---|
| `unit` | Быстрые, без I/O |
| `integration` | Web API через `httpx.AsyncClient` |

---

### Деплой

Артефакты в `deploy/` + `Dockerfile` + `docker-compose.yml`.

- `deploy/nginx/` — конфиг реверс-прокси (`fppzo.ru.conf`, `nginx.conf`);
- `deploy/certbot/` — конфигурация Let's Encrypt;
- `deploy/scripts/deploy.sh` — деплой;
- `deploy/scripts/init-letsencrypt.sh` — первичная выдача TLS-сертификата.

Полная инструкция — [`docs/DEPLOY.md`](docs/DEPLOY.md).

#### Скрипт безопасного обновления

```bash
(
  set -Eeuo pipefail
  umask 077
  cd /root/ai-tutor

  exec 9>/root/ai-tutor-deploy.lock
  flock -n 9 || { echo "Другое обновление выполняется."; exit 1; }

  command -v python3 >/dev/null
  docker compose version >/dev/null
  docker inspect ai-tutor-app >/dev/null

  var_source=$(docker inspect ai-tutor-app --format '{{range .Mounts}}{{if eq .Destination "/app/var"}}{{.Source}}{{end}}{{end}}')
  test "$var_source" = "/root/ai-tutor/var" || { echo "ОШИБКА: неожиданное подключение /app/var: $var_source"; exit 1; }

  backup_dir=$(mktemp -d /root/ai-tutor-backup.XXXXXXXX)
  mkdir -p "$backup_dir/cases" "$backup_dir/var" "$backup_dir/verify"

  echo "Резервная копия: $backup_dir"

  trap '
    rc=$?
    echo "ОШИБКА: обновление прервано, код $rc. Бэкап: $backup_dir"
    echo "Проверьте: docker compose ps -a"
    exit "$rc"
  ' ERR

  # Останавливаем приложение перед синхронизацией
  docker compose stop app

  # Сохраняем текущие материалы и промпты
  docker cp -a ai-tutor-app:/app/src/infrastructure/content/cases/. "$backup_dir/cases/" || true
  docker cp -a ai-tutor-app:/app/var/. "$backup_dir/var/" || true

  # Проверяем наличие ключевых файлов
  test -f "$backup_dir/cases/products.json" || echo "Предупреждение: products.json не найден в бэкапе"
  test -f "$backup_dir/var/prompts/templates.json" || echo "Предупреждение: templates.json не найден в бэкапе"

  # Получаем изменения из репозитория
  git fetch origin feature/multi-products
  git reset --hard FETCH_HEAD

  # Собираем новый образ
  docker compose build app

  # Создаём новый контейнер БЕЗ запуска
  docker compose up --no-start --no-deps --no-build --force-recreate app

  # Восстанавливаем материалы в остановленный контейнер
  docker cp -a "$backup_dir/cases/." ai-tutor-app:/app/src/infrastructure/content/cases/ || true

  # var уже на хосте и подключён bind mount, не перезаписываем

  # Проверяем восстановленные файлы перед запуском
  mkdir -p "$backup_dir/verify/cases"
  docker cp -a ai-tutor-app:/app/src/infrastructure/content/cases/. "$backup_dir/verify/cases/" || true

  if [ -f "$backup_dir/cases/products.json" ] && [ -f "$backup_dir/verify/cases/products.json" ]; then
    if ! cmp -s "$backup_dir/cases/products.json" "$backup_dir/verify/cases/products.json"; then
      echo "ОШИБКА: products.json не совпадает после восстановления"
      exit 1
    fi
  fi

  # Запускаем новую версию
  docker compose start app
  sleep 5

  docker compose ps app
  docker compose logs --tail=50 app

  echo
  echo "✓ Новая версия развёрнута. Проверьте доступность и функциональность сервиса."
  echo "  Бэкап сохранён: $backup_dir"
  echo "  Удалите его после проверки: rm -rf $backup_dir"
)
```

---

### Документация

| Документ | Содержание |
|---|---|
| [`docs/SCOPE.md`](docs/SCOPE.md) | Что входит и что **не** входит в MVP |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Слои, правила зависимостей, поток управления |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Срезы 1–9 |
| [`docs/FSM_DESIGN.md`](docs/FSM_DESIGN.md) | Полная карта состояний, событий, переходов, Mermaid |
| [`docs/FSM_INVARIANTS.md`](docs/FSM_INVARIANTS.md) | Какое событие какие поля контекста меняет |
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | Деплой на VPS (Docker, nginx, TLS) |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Архитектурные решения (журнал) |
| `docs/adr/ADR-004…012` | Конкретные принятые решения |

---

### Дорожная карта

| Срез | Назначение | Статус |
|---|---|---|
| 1 | FSM-ядро в памяти | ✅ |
| 2 | Persistence (Postgres + Alembic) | в очереди |
| 3 | Заглушка LLM с эффектами | ✅ |
| 4 | Минимальный HTTP API | ✅ |
| 5 | UI тренажёра | ✅ |
| 6 | Реальный GigaChat | ✅ |
| 7 | Голос (TTS+STT) | ✅ |
| 8 | Админка промптов и кейсов | ✅ |
| 9 | Деплой на VPS | ✅ |

---

### Лицензия

Проект распространяется под лицензией [MIT](LICENSE).

Вы можете свободно использовать, изменять и распространять этот код, в том числе в коммерческих целях, при условии сохранения текста лицензии и уведомления об авторских правах.

[⬆ Наверх](#ai-tutor)
