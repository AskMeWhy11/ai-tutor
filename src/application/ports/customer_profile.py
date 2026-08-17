"""Порт генерации профиля клиента для практики (эталон: create-customer-profile)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

__all__ = ["CustomerProfile", "CustomerProfileGenerator"]


@dataclass(frozen=True, slots=True)
class CustomerProfile:
    """Профиль клиента, которого отыгрывает аватар в режиме «Практика».

    Поля соответствуют эталонным переменным CLIENT_NAME / CLIENT_AGE /
    CLIENT_GENDER / CLIENT_CHARACTER / BASE_REQUIRE.
    """

    client_name: str
    client_age: int
    client_gender: str
    client_character: str
    base_require: str

    def as_placeholders(self) -> dict[str, str]:
        """Значения для подстановки в промпты по эталонному неймингу."""
        return {
            "CLIENT_NAME": self.client_name,
            "CLIENT_AGE": str(self.client_age),
            "CLIENT_GENDER": self.client_gender,
            "CLIENT_CHARACTER": self.client_character,
            "BASE_REQUIRE": self.base_require,
        }


class CustomerProfileGenerator(Protocol):
    async def generate(self, *, case_id: str | None = None) -> CustomerProfile:
        """Сгенерировать профиль клиента для кейса."""
        ...
