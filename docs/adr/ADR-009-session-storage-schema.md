# ADR-009: Схема таблицы sessions — JSONB для ctx, колонки для метаданных

* **Статус:** Принято
* **Дата:** 2025-XX-XX
* **Контекст:** Срез 2, проектирование схемы БД.

## Контекст

`SessionContext` — это dataclass с несколькими полями
(`completed_modes: frozenset[Mode]`, `weak_zones_remaining: tuple[str,
...]`, `cycle_count: int` и потенциально новые поля в будущем).
`FSMState` — enum.

Варианты хранения:

1. **JSONB на всё.** Колонки: `session_id`, `data JSONB`, `created_at`,
   `last_activity_at`. В `data` лежит и state, и ctx.
2. **JSONB только для ctx.** Колонки: `session_id`, `state TEXT`,
   `ctx JSONB`, `created_at`, `last_activity_at`.
3. **Колонки на всё.** Каждое поле ctx — отдельная колонка. Любое
   изменение модели → миграция Alembic.

## Решение

Принят **вариант 2**: JSONB для ctx, отдельные колонки для метаданных
и state.

```sql
CREATE TABLE sessions (
    session_id        UUID        PRIMARY KEY,
    state             TEXT        NOT NULL,
    ctx               JSONB       NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_activity_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## Обоснование

1. **state индексируется тривиально.** Запросы вроде «сколько сессий
   сейчас в TRAINING_QUIZ» — обычный `WHERE state = 'TRAINING_QUIZ'`
   с возможностью добавить индекс. Делать это через JSONB
   (`data->>'state'`) — медленнее и менее читаемо.
2. **ctx как JSONB — правильный уровень абстракции.** ctx — это
   агрегат состояния FSM. Его внутренняя структура — внутреннее дело
   домена, не БД. Добавление поля в `SessionContext` не должно
   требовать миграции.
3. **last_activity_at нужен для TTL (48 ч).** Это операционное поле,
   а не доменное. Логично держать его на уровне БД, а не внутри ctx.
4. **created_at — для аналитики и отладки.** Дёшево и полезно.

## Последствия

* Сериализация ctx ↔ JSONB — задача `PostgresSessionStore` (Коммит 7).
  Преобразования: `frozenset[Mode]` → отсортированный `list[str]`,
  `tuple[str, ...]` → `list[str]`, `Mode` → `mode.value`.
* `state` хранится как `state.value` (строка из enum).
* Альтернативы JSONB (Postgres-специфичный JSONB vs кросс-СУБД JSON)
  не рассматриваются: Postgres зафиксирован в ROADMAP.
* TTL-логика (48 ч) сравнивает `last_activity_at` с текущим временем.
  Реализуется в Срезе 2.5 / 3 (Resume / SessionExpired команды).
* Индекс по `last_activity_at` понадобится для cleanup-задач —
  добавим, когда появится cleanup. Сейчас — без него.

## Альтернативы

**Вариант 1 (всё в JSONB).** Отвергнут: state — операционное поле,
запросы по нему частые, индекс на JSONB-выражение хуже обычного
индекса.

**Вариант 3 (всё в колонках).** Отвергнут: каждое поле ctx — миграция.
Учитывая, что модель ещё нестабильна (см. ADR-006 о пересмотре
квиза), это неприемлемо.
```

**`docs/adr/ADR-010-effects-execution-order.md`**
```markdown
# ADR-010: Порядок исполнения эффектов в SessionRunner

* **Статус:** Принято
* **Дата:** 2025-XX-XX
* **Контекст:** Срез 2, проектирование SessionRunner.

## Контекст

`FSMResult.effects` — кортеж эффектов, эмитированных переходом FSM.
В Срезе 1 это всегда `(PersistSession(),)` или `()`. В Срезе 3
появятся эффекты `EvaluateDialog`, `GenerateReply`, `SendMessage` и
т. п. — в одном результате может быть несколько эффектов разных
типов.

Вопрос: в каком порядке `SessionRunner` их исполняет?

## Решение

`PersistSession` исполняется **первым**. Остальные эффекты — после, в
порядке их следования в `result.effects`.

```python
async def dispatch(self, session_id, command):
    snapshot = await self.store.load(session_id)
    result = self.fsm.handle(snapshot.state, command, snapshot.ctx)

    # 1. Persist first.
    if any(isinstance(e, PersistSession) for e in result.effects):
        await self.store.save(
            session_id, result.new_state, result.new_ctx
        )

    # 2. Other effects after persist.
    for effect in result.effects:
        if isinstance(effect, PersistSession):
            continue
        await self._execute(effect)

    return result
```

## Обоснование

1. **Состояние FSM — источник истины.** Если упадёт исполнение
   эффекта *после* персиста — система при следующем вызове продолжит
   с записанного состояния. Это безопасный режим деградации.
2. **Альтернатива опаснее.** Если персистить *последним* и до этого
   успеть отправить пользователю сообщение — при падении персиста
   при ретрае пользователь получит сообщение дважды (или, наоборот,
   поведение разойдётся с записанным состоянием).
3. **Идемпотентность исполнителей — отдельная задача.** В Срезе 2 у
   нас один эффект (`PersistSession`), и он по природе идемпотентен
   (upsert). В Срезе 3 для не-идемпотентных эффектов
   (`SendMessage`) понадобится outbox-паттерн или аналог. До этого
   момента дисциплина «персист первым» закрывает базовый случай.

## Последствия

* `SessionRunner.dispatch` всегда сначала пишет в БД, потом исполняет
  остальное.
* В Срезе 3 добавятся ветки для новых типов эффектов; правило
  «PersistSession первым» сохраняется.
* Если в `result.effects` будет несколько `PersistSession()` (что не
  должно происходить, но защитная логика) — `save()` вызывается один
  раз; результат тот же благодаря upsert.
* Outbox-паттерн для не-идемпотентных эффектов — за рамками MVP, но
  упомянут как известный долг.

## См. также

* ADR-007: SessionRunner и эффекты как намерения.
