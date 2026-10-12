from typing import Protocol, runtime_checkable


@runtime_checkable
class PasscodeIssuer(Protocol):
    """Порт выпуска одноразового кода со стороны OTP-контекста."""

    async def issue(self, telegram_user_id: int) -> str:
        ...