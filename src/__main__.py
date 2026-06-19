"""Точка входа: `python -m src` запускает dev-сервер uvicorn.

Приложение создаётся напрямую (без import-by-string), чтобы не зависеть
от наличия `src/` в PYTHONPATH дочернего процесса uvicorn. Тесты
используют composition.app:create_app через pytest pythonpath.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Гарантируем, что `src/` в sys.path при запуске `python -m src` из корня репо.
_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import uvicorn  # noqa: E402

from composition.app import create_app  # noqa: E402


def main() -> None:
    app = create_app()
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
    )


if __name__ == "__main__":
    main()
