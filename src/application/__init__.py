"""Слой приложения: оркестратор FSM (FSMService) и его контракты.

Синхронный код в FSMService — все побочные действия возвращаются
наружу как Effect-объекты. Исполнение эффектов — задача SessionRunner
(async), который связывает FSMService с SessionStore.

Структура:
    commands.py        — команды от внешнего мира (UI, контроллер)
    effects.py         — побочные эффекты, которые FSMService просит исполнить
    fsm_service.py     — оркестратор: команда + контекст + состояние → результат
    session_runner.py  — async-координатор: load → handle → persist → effects
    ports/             — Protocol-интерфейсы к инфраструктуре (SessionStore, ...)
"""
