from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class PasscodeVerifier(Protocol):
    """Порт проверки одноразового кода для Identity & Access."""

    async def verify(self, code: str) -> Optional[int]:
        ...