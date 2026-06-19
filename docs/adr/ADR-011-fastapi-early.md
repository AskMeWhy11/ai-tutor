# ADR-011 — Сдвиг FastAPI/Jinja2 в Срез 2 ради раннего HTML-UI

**Статус:** Принят
**Дата:** 2025
**Связанные ADR:** ADR-007 (effect-pipeline), ADR-008 (async stack)

## Контекст

По исходному ROADMAP FastAPI и шаблонизатор должны были появиться в
Срезе 4 (HTTP-слой и UI). На практике после Срезов 1–2 у нас уже есть:

- стабильная FSM с дискриминированным набором команд;
- SessionRunner с эффект-пайплайном (ADR-007);
- async-контракты (ADR-008);
- in-memory SessionStore (Срез 2 в варианте без Postgres).

Команда заинтересована в **раннем видимом прогрессе**: кликабельный
тренажёр позволяет тестировать FSM руками и быстрее ловить дыры
в UX-логике, чем тесты pytest.

## Решение

Подключить `fastapi`, `uvicorn[standard]`, `jinja2`, `pydantic` в
production-зависимости уже сейчас. Поднять минимальное HTTP API
(`/api/sessions`, `/api/sessions/{id}/commands`) и одну HTML-страницу
с vanilla JS. Persistence остаётся in-memory; Postgres
подключается отдельным коммитом по плану.

## Альтернативы

1. **Ждать Срез 4** — отвергнуто. Блокирует обратную связь по UX.
2. **CLI-тренажёр вместо HTTP** — отвергнуто. Дешевле по коду, но
   не приближает целевую архитектуру.
3. **SSE/WebSocket с самого начала** — отвергнуто. Преждевременно;
   текущий effect-pipeline синхронный по реквесту, этого достаточно.

## Последствия

- `pyproject.toml` обогащается production-зависимостями раньше плана.
- Появляется слой `infrastructure/web/` и пакет `composition/`.
- ROADMAP корректируется: HTTP-вехи Среза 4 частично выполнены.
- `available_commands` дублирует знание о валидных переходах FSM
  (на стороне `command_mapper`). Признано допустимым; синхронность
  гарантируется интеграционными тестами.
- Postgres-store по-прежнему отдельная задача; in-memory store
  переехал из `tests/fakes/` в `infrastructure/persistence/`
  как production-реализация Среза 2 (тестовый фейк остался в `tests/fakes/`
  для unit-тестов, без конкуренции реализаций).

## Команды проверки

```bash
poetry install
poetry run pytest -m integration
poetry run python -m src   # http://127.0.0.1:8000
```
