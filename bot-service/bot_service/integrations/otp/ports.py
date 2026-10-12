from typing import Protocol, runtime_checkable


@runtime_checkable
class PasscodeIssuer(Protocol):
    """Потребительский порт выпуска одноразового кода со стороны bot-service."""

    async def issue(self, telegram_user_id: int) -> str:
        ...