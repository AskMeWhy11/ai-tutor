# Инварианты FSM и контекста

Документ описывает **правила мутации `SessionContext`** — что именно
меняется в контексте при каждом переходе FSM. Это контракт между
доменом (TRANSITIONS) и оркестратором (FSMService).

> Источник истины: этот документ + `src/domain/transitions.py`.
> Если код расходится с документом — баг в коде или в документе,
> в любом случае нужно синхронизировать.

## Принципы

1. **FSM — чистая таблица.** Целевое состояние получается из
   `(state, event)` без чтения контекста. Контекст влияет только на
   выбор события (guards в `FSMService`), не на исход перехода.
2. **Контекст мутируется только в `FSMService`.** Домен не знает про
   контекст. Мутации привязаны к конкретным событиям и описаны ниже.
3. **Мутации идемпотентны.** `frozenset.union` не дублирует элементы;
   повторное добавление `Mode.TRAINING` в `completed_modes` ничего
   не меняет.
4. **Сторона, проводящая оценку, передаёт результат в команде.**
   FSM не вычисляет «провалил/прошёл» — это решение приходит из LLM
   через команду (см. ADR-004).

## Таблица мутаций

| Событие | Переход | Мутация `SessionContext` |
|---|---|---|
| `ALL_CORRECT` | `TRAINING_QUIZ → TRAINING_DONE` | `completed_modes ∪= {Mode.TRAINING}` |
| `MAX_ATTEMPTS` | `TRAINING_QUIZ → TRAINING_DONE` | `completed_modes ∪= {Mode.TRAINING}` |
| `SCENARIO_DONE` | `EXAMPLE → EXAMPLE_DONE` | `completed_modes ∪= {Mode.EXAMPLE}` |
| `ALL_ZONES_OK` | `PRACTICE_EVAL → PRACTICE_SUCCESS` | `completed_modes ∪= {Mode.PRACTICE}`, `weak_zones_remaining = ()` |
| `HAS_FAILURES` | `PRACTICE_EVAL → PRACTICE_PARTIAL` | `weak_zones_remaining = <список из команды PracticeEvaluated>` |
| `ZONES_DONE` | `KNOWLEDGE → KNOWLEDGE_DONE` | `completed_modes ∪= {Mode.KNOWLEDGE}` |
| `REPEAT_CYCLE` | `KNOWLEDGE_DONE → EXAMPLE` | `cycle_count += 1` |
| `EXIT_CONFIRMED` | `EXIT_WARNING_QUIZ → WELCOME` | `quiz_question_index = 0`, `last_answer_correct = None` |
| `EXIT_CONFIRMED` | прочие `EXIT_WARNING_* → WELCOME` | без мутаций |
| (прочие переходы) | — | без мутаций |

## Производные предикаты

`SessionContext.knowledge_unlocked` — True, если выбор `MODE_KNOWLEDGE`
в WELCOME ведёт к KNOWLEDGE без блокировки.

```python
@property
def knowledge_unlocked(self) -> bool:
    return Mode.KNOWLEDGE in self.completed_modes and bool(self.weak_zones_remaining)
```

Обоснование условия: пользователь видит «Знания» в WELCOME как живой
вариант только если уже один раз был в KNOWLEDGE (через основной поток
PRACTICE_PARTIAL → KNOWLEDGE) и зоны ещё не зачищены успешной практикой.
Если зоны зачищены (`ALL_ZONES_OK`) — `weak_zones_remaining = ()`,
кнопка становится неактивной.

## Что **не** мутируется в FSM

* **Прогресс внутри блока** (текущий вопрос квиза, реплика диалога).
  Это уровень LLM/контента, FSM знает только границы блоков.
* **Имя сотрудника, продукт, бизнес-контекст.** Это атрибуты сессии,
  устанавливаются при её создании контроллером, FSM их не трогает.
* **Тексты сообщений, история чата.** Хранятся в репозитории сообщений,
  не в контексте FSM.

## Связанные документы

* `docs/FSM_DESIGN.md` — общая структура FSM, состояния, события.
* `docs/adr/ADR-004-llm-verdict-as-fact.md` — почему LLM-оценка
  попадает в FSM как факт, а не как сырой ответ.
* `docs/adr/ADR-005-no-cycle-limits.md` — почему `cycle_count`
  растёт, но не используется для блокировки.
* `docs/adr/ADR-006-back-to-welcome.md` — возврат в WELCOME через
  EXIT_WARNING-состояния.
