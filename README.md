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
- [HTTP API](#http-api)
- [FSM: модель домена](#fsm-модель-домена)
- [Разработка](#разработка)
- [Тестирование](#тестирование)
- [Документация](#документация)
- [Дорожная карта](#дорожная-карта)

---

## Что это

Сотрудник банка тренируется продавать банковский продукт (на старте — «Кредитная карта, новичок») в режимах:

| Режим | Кто играет роль AI | Кто играет роль пользователя |
|---|---|---|
| **Обучение** | Преподаватель | Ученик (отвечает на квиз) |
| **Пример** | Сотрудник банка | Клиент |
| **Практика** | Клиент | Сотрудник банка (оценивается LLM) |
| **Знание** | Преподаватель западающих зон | Ученик |

При неуспешной Практике запускается петля **Пример → Практика → Знание** до успеха. Подробнее — [`docs/SCOPE.md`](docs/SCOPE.md).

---

## Текущее состояние

| Компонент | Состояние |
|---|---|
| Domain (states, events, transitions, context) | ✅ готов |
| Application (FSMService, SessionRunner, commands, effects, ports) | ✅ готов для всех команд Среза 1 |
| Persistence | ⚠️ только in-memory (`InMemorySessionStore`); Postgres — Срез 2 |
| LLM | ⚠️ заглушка (`StubAvatar`, `StubAnswerChecker`); GigaChat — Срез 6 |
| TTS | ✅ SaluteSpeech (продакшен) + `NullTTS` (фолбэк) |
| STT | ✅ SaluteSpeech (`/api/stt`) + Web Speech API как fallback |
| Web UI | ⚠️ минимальный (статика + SVG-аватар + аудиоплеер) |
| Web API | ✅ `/api/sessions/*`, `/api/audio/{key}` |
| Админка промптов | ❌ Срез 8 |
| Деплой | ❌ Срез 9 |

Возврат в WELCOME (`BACK_TO_WELCOME` + 5 EXIT_WARNING-состояний из [ADR-006](docs/adr/ADR-006-back-to-welcome.md)) описан в дизайне, но **в коде пока нет** — это Коммит 2.

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

**SessionRunner** — async-координатор: загружает снапшот, вызывает FSMService, исполняет эффекты (persist, TTS-синтез, кэш аудио), возвращает обогащённый результат.

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
| LLM | GigaChat (план); сейчас — стабы |
| TTS | SaluteSpeech REST |
| Хранилище | in-memory (план: PostgreSQL + SQLAlchemy + Alembic) |
| Тесты | pytest, pytest-asyncio, pytest-cov |
| Качество | ruff (lint+format), mypy strict, pre-commit |

---

## Быстрый старт

### Требования

- Python 3.13
- Poetry ≥ 2.0
- (опционально) API-ключ SaluteSpeech — без него UI работает в текстовом режиме без озвучки

### Установка

```bash
git clone <repo-url> ai-tutor
cd ai-tutor
poetry install
poetry run pre-commit install
cp .env.example .env
# отредактируй .env: вставь SALUTESPEECH_API_KEY (или оставь пустым)
```

### Запуск dev-сервера

```bash
poetry run python -m src
```
Или так:
```bash
poetry run uvicorn composition.app:create_app --factory --reload --app-dir src
```

Откроется на `http://127.0.0.1:8000/`.

### Альтернативно — через uvicorn

```bash
poetry run uvicorn --factory composition.app:create_app --reload --app-dir src
```

---

## Конфигурация

Все настройки — через `.env` (см. `.env.example`). Приложение запускается даже без `.env`: TTS просто отключится.

| Переменная | Назначение | Дефолт |
|---|---|---|
| `SALUTESPEECH_API_KEY` | Ключ авторизации (Basic) | пусто = TTS off |
| `SALUTESPEECH_SCOPE` | OAuth scope | `SALUTE_SPEECH_PERS` |
| `SALUTESPEECH_VOICE` | Голос диктора | `Bys_24000` |
| `SALUTESPEECH_FORMAT` | Формат аудио | `wav16` |
| `SALUTESPEECH_CA_BUNDLE` | Путь к корневому CA Минцифры | `russian_trusted_root_ca.cer` |
| `SALUTESPEECH_ENABLED` | Глобальный выключатель TTS | `true` |
| `TTS_CACHE_DIR` | Директория файлового кэша аудио | `var/tts` |

Сертификат «Russian Trusted Root CA» нужен для обращения к `*.sberbank.ru` — он лежит в корне репозитория.

---

## Структура репозитория

```
src/
├── domain/            # FSM-ядро: states, events, transitions, context
├── application/       # FSMService, SessionRunner, commands, effects
│   └── ports/         # Protocol-интерфейсы для адаптеров
├── infrastructure/    # Адаптеры: web, tts, llm (стабы), persistence, content
│   └── web/           # FastAPI-роуты, шаблоны, статика
└── composition/       # Сборка приложения (DI)

tests/
├── unit/              # Юнит-тесты domain + application
├── integration/       # Интеграционные тесты web API
└── fakes/             # Тестовые двойники

docs/                  # ARCHITECTURE, SCOPE, ROADMAP, FSM_DESIGN, ADR
content/               # Заготовки для будущих кейсов и чек-листов
scripts/               # dump.sh и пр.
var/tts/               # Кэш синтезированного аудио (gitignore)
```

---

## HTTP API

Префикс — `/api`. Полный контракт оформится в `docs/API.md` на Срезе 4.

| Метод | Путь | Назначение |
|---|---|---|
| `POST` | `/api/sessions` | Создать сессию, получить первую реплику аватара |
| `GET` | `/api/sessions/{id}` | Получить текущее состояние сессии |
| `POST` | `/api/sessions/{id}/commands` | Отправить команду в FSM |
| `GET` | `/api/audio/{key}` | Получить кэшированное TTS-аудио |
| `GET` | `/` | UI тренажёра |

**Формат команды:**
```json
{ "command": { "type": "SelectMode", "mode": "training" } }
```

Маппинг типов команд из API в `application.commands.*` — в `infrastructure/web/command_mapper.py`.

---

## FSM: модель домена

### Состояния (20 в Срезе 1)

`INIT`, `RESUME_PROMPT`, `MENU`, `WELCOME`, `SKIP_WARNING_1/2`, `TRAINING`, `TRAINING_QUIZ`, `TRAINING_EXPLAIN`, `TRAINING_DONE`, `EXAMPLE`, `EXAMPLE_DONE`, `PRACTICE`, `PRACTICE_EVAL`, `PRACTICE_PARTIAL`, `PRACTICE_SUCCESS`, `KNOWLEDGE`, `KNOWLEDGE_DONE`, `FINISH`.

### Принципы

1. **Чистая таблица переходов.** `(state, event) → state` без чтения контекста (см. `domain/transitions.py`).
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

Строгий режим: `strict = true`, `disallow_untyped_defs`, `warn_unused_ignores` (тесты — мягче).

### Pre-commit

Настроены: `ruff` (с автофиксом), `ruff-format`, `mypy`, базовые проверки файлов (yaml/toml/json, EOL, размер). Запуск вручную:

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
# Все тесты с покрытием
poetry run pytest

# Только юнит
poetry run pytest tests/unit

# Только интеграционные
poetry run pytest tests/integration

# С отчётом покрытия
poetry run pytest --cov=src --cov-report=term-missing
```

**Цель покрытия:** 100% переходов FSM (Срез 1). Текущая структура тестов — по одному файлу на группу команд (`test_fsm_service_<group>.py`).

Маркеры:

| Маркер | Назначение |
|---|---|
| `unit` | Быстрые, без I/O |
| `integration` | Web API через `httpx.AsyncClient` |

---

## Документация

| Документ | Содержание |
|---|---|
| [`docs/SCOPE.md`](docs/SCOPE.md) | Что входит и что **не** входит в MVP |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Слои, правила зависимостей, поток управления |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Срезы 1–9 |
| [`docs/FSM_DESIGN.md`](docs/FSM_DESIGN.md) | Полная карта состояний, событий, переходов, Mermaid |
| [`docs/FSM_INVARIANTS.md`](docs/FSM_INVARIANTS.md) | Какое событие какие поля контекста меняет |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Архитектурные решения (журнал) |
| `docs/adr/ADR-004…012` | Конкретные принятые решения |

Любое нетривиальное решение — фиксируется ADR в `docs/adr/`.

---

## Дорожная карта

| Срез | Назначение | Статус |
|---|---|---|
| 1 | FSM-ядро в памяти | ✅ |
| 2 | Persistence (Postgres + Alembic) | в очереди |
| 3 | Заглушка LLM с эффектами | частично (стабы) |
| 4 | Минимальный HTTP API | ✅ (без админки) |
| 5 | Минимальный UI тренажёра | ✅ (без TTS/STT-захвата с фронта) |
| 6 | Реальный GigaChat | — |
| 7 | Голос (TTS+STT) | TTS ✅, STT ✅ |
| 8 | Админка промптов | — |
| 9 | Деплой на VPS | — |

Подробно — [`docs/ROADMAP.md`](docs/ROADMAP.md).

---

## Лицензия

Внутренний проект. Лицензия не определена.
