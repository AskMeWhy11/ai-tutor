"""TTSClient port — синтез речи.

`synthesize` возвращает bytes (готовое аудио в формате, заявленном
конкретной реализацией) либо None — это сигнал «озвучка недоступна»
(нет креденшелов, сетевая ошибка, отключено настройкой). В этом случае
SessionRunner не эмитит PlayAudio, но EmitText всё равно отдаётся.
"""

from __future__ import annotations

from typing import Protocol


class TTSClient(Protocol):
    async def synthesize(self, text: str) -> bytes | None:
        """Синтезировать речь. None = недоступно."""
        ...

    @property
    def mime(self) -> str:
        """MIME-тип возвращаемого аудио, например 'audio/wav'."""
        ...

    @property
    def extension(self) -> str:
        """Расширение файла без точки, например 'wav'."""
        ...
