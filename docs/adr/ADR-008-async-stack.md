# ADR-008: Async-стек для I/O

* **Статус:** Принято
* **Дата:** 2025-XX-XX
* **Контекст:** Срез 2, выбор технологий персистентности.

## Контекст

В Срезе 4 HTTP-слой будет на FastAPI (async). В Срезе 6 LLM-клиент
будет делать сетевые вызовы к GigaChat (естественно async).
В Срезе 7 — SaluteSpeech (тоже сетевой I/O).

Выбор для Среза 2: писать `SessionStore` sync (с обёрткой через
`run_in_threadpool` в HTTP) или async с самого начала.

## Решение

Весь I/O — async с самого начала.

* SQLAlchemy 2.x async API (`AsyncEngine`, `AsyncConnection`).
* Драйвер: `asyncpg`.
* `SessionStore.save / load` — `async def`.
* `SessionRunner.dispatch` — `async def`.
* Тесты I/O-кода — через `pytest-asyncio`.

FSM (`domain/`, `application/fsm_service.py`, `application/commands.py`,
`application/effects.py`) остаётся **синхронным**. Это чистая логика
без I/O.

## Обоснование

1. **Единый стиль на весь проект.** Учить два API параллельно (sync
   для сессий, async для всего остального) дороже, чем сразу async.
2. **SQLAlchemy 2.x async — стабильное API.** Документация
   качественная, паттерны устоявшиеся.
3. **FastAPI работает с async-кодом нативно.** Не нужно
   `run_in_threadpool` для каждого запроса в БД.
4. **Без преждевременной оптимизации.** Async выбран не ради
   производительности, а ради единообразия с будущими слоями.
   Производительность Postgres-доступа в Срезе 2 нерелевантна.

## Последствия

* Зависимости (Коммит 6): `sqlalchemy[asyncio]`, `asyncpg`,
  `pytest-asyncio`, `alembic`.
* Все интеграционные тесты помечены `@pytest.mark.asyncio` или
  через `asyncio_mode = "auto"` в конфиге pytest.
* Доменные тесты (Срез 1) **остаются синхронными**. Маркер
  `pytest-asyncio` к ним не применяется.
* Координатор (Коммит 8) — async. Если в будущем понадобится
  вызывать его из sync-контекста — оборачиваем `asyncio.run()` на
  стороне вызывающего.

## Альтернативы

**Sync SessionStore + run_in_threadpool в HTTP.** Отвергнут: создаёт
два параллельных I/O-стиля и долг переписывания при подключении
LLM/Speech.

**Pure asyncio без SQLAlchemy (только asyncpg + ручной SQL).**
Отвергнут: к Срезу 8 (промпты, продукты, пользователи) ORM или
SQL-builder всё равно понадобится. Лучше один движок с самого начала.
