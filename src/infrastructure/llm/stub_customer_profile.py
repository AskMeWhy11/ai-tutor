"""Детерминированный генератор профиля клиента (без LLM)."""

from __future__ import annotations

import itertools
from typing import ClassVar

from application.ports.customer_profile import CustomerProfile

__all__ = ["StubCustomerProfileGenerator"]

_PROFILES: tuple[CustomerProfile, ...] = (
    CustomerProfile(
        client_name="Мария",
        client_age=34,
        client_gender="ж",
        client_character="доброжелательная, но осторожная",
        base_require="Планирует крупную покупку бытовой техники, не хочет трогать накопления.",
    ),
    CustomerProfile(
        client_name="Сергей",
        client_age=45,
        client_gender="м",
        client_character="скептичный, считает деньги",
        base_require="Часто ездит в командировки, нужен запас на непредвиденные расходы.",
    ),
    CustomerProfile(
        client_name="Анна",
        client_age=27,
        client_gender="ж",
        client_character="торопливая, отвечает коротко",
        base_require="Собирается в отпуск, не хватает суммы до зарплаты.",
    ),
)


class StubCustomerProfileGenerator:
    """Циклически выдаёт профили из фиксированного набора."""

    _counter: ClassVar[itertools.count[int]] = itertools.count()

    async def generate(self, *, case_id: str | None = None) -> CustomerProfile:
        idx = next(self._counter) % len(_PROFILES)
        return _PROFILES[idx]
