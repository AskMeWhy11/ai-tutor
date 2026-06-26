# AI-Tutor

AI-наставник для обучения клиентских менеджеров банка продажам банковских продуктов в формате интерактивного тренажёра.

---

## Содержание

- [Что это](#что-это)
- [Текущее состояние](#текущее-состояние)
- [Архитектура](#архитектура)
- [Стек](#стек)
- [Быстрый старт](#быстрый-старт)
- [Конфигурация](#конфигурация)
- [Структура репозитория](#структура-репозитория)
- [Кейсы и контент](#кейсы-и-контент)
- [Админка](#админка)
- [HTTP API](#http-api)
- [FSM: модель домена](#fsm-модель-домена)
- [Разработка](#разработка)
- [Тестирование](#тестирование)
- [Деплой](#деплой)
- [Документация](#документация)
- [Дорожная карта](#дорожная-карта)

---

## Что это

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

## Текущее состояние

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

## Архитектура

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

## Стек

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

## Быстрый старт

### Требования

- Python 3.13
- Poetry ≥ 2.0
- (опционально) ключи SaluteSpeech / GigaChat — без них UI работает в текстовом режиме на стабах

### Установка

```bash
git clone <repo-url> ai-tutor
cd ai-tutor
poetry install
poetry run pre-commit install
cp .env.example .env
# отредактируй .env: ключи SaluteSpeech / GigaChat (или оставь пустыми)
```

### Запуск dev-сервера

```bash
poetry run python -m src
```
Или через uvicorn:
```bash
poetry run uvicorn composition.app:create_app --factory --reload --app-dir src
```

Откроется на `http://127.0.0.1:8000/`.

---

## Конфигурация

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

## Структура репозитория

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

## Кейсы и контент

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

## Админка

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

## HTTP API

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

## FSM: модель домена

### Состояния

`INIT`, `RESUME_PROMPT`, `MENU`, `WELCOME`, `SKIP_WARNING_1/2`, `TRAINING`, `TRAINING_QUIZ`, `TRAINING_EXPLAIN`, `TRAINING_DONE`, `EXAMPLE`, `EXAMPLE_DONE`, `PRACTICE`, `PRACTICE_EVAL`, `PRACTICE_PARTIAL`, `PRACTICE_SUCCESS`, `KNOWLEDGE`, `KNOWLEDGE_DONE`, `FINISH`.

### Принципы

1. **Чистая таблица переходов.** `(state, event) → state` без чтения контекста (`domain/transitions.py`).
2. **Guards в FSMService.** Контекст влияет только на выбор события, не на исход перехода.
3. **LLM-вердикт как факт.** Команды несут готовое решение (`SubmitQuizAnswer(correct=bool)`, `PracticeEvaluated(weak_zones=...)`), а не сырой текст. См. [ADR-004](docs/adr/ADR-004-llm-verdict-as-fact.md).
4. **Динамический переход — спецслучай.** `RESUME_CONFIRMED` → `ctx.saved_state`; в таблицу не входит, обрабатывается явно.
5. **Без лимитов петли ремедиации.** `cycle_count` — наблюдатель, не контроллер. См. [ADR-005](docs/adr/ADR-005-no-cycle-limits.md).

Полная Mermaid-диаграмма и таблица переходов — в [`docs/FSM_DESIGN.md`](docs/FSM_DESIGN.md).

---

## Разработка

### Линтер и формат

```bash
poetry run ruff check .
poetry run ruff format .
```

### Типы

```bash
poetry run mypy
```

Строгий режим (`strict = true`); тесты — мягче (см. `[[tool.mypy.overrides]]` в `pyproject.toml`).

### Pre-commit

```bash
poetry run pre-commit run --all-files
```

### Соглашения по коду

- Строки до 100 символов.
- Кавычки — двойные.
- Импорты сортирует ruff (`I`-rules).
- Все публичные функции/классы — с docstring и type hints.
- В `domain/` и `application/` — никаких `async`, никаких внешних импортов кроме стандартной библиотеки и domain.

---

## Тестирование

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

## Деплой

Артефакты в `deploy/` + `Dockerfile` + `docker-compose.yml`.

- `deploy/nginx/` — конфиг реверс-прокси (`fppzo.ru.conf`, `nginx.conf`);
- `deploy/certbot/` — конфигурация Let's Encrypt;
- `deploy/scripts/deploy.sh` — деплой;
- `deploy/scripts/init-letsencrypt.sh` — первичная выдача TLS-сертификата.

Полная инструкция — [`docs/DEPLOY.md`](docs/DEPLOY.md).

---

## Документация

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

## Дорожная карта

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

## Лицензия

Внутренний проект. Лицензия не определена.
