"""Адаптеры персистентности.

InMemorySessionStore используется в Срезе 2 как production-реализация
до прихода Postgres (Срез 4 / отдельный коммит). Фейк для unit-тестов
живёт отдельно — в tests/fakes/in_memory_session_store.py.
"""
