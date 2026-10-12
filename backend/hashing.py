from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_ph = PasswordHasher(type=Type.ID)


def hash_secret(secret: str) -> str:
    return _ph.hash(secret)


def verify_secret(secret_hash: str, secret: str) -> bool:
    try:
        return _ph.verify(secret_hash, secret)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(secret_hash: str) -> bool:
    return _ph.check_needs_rehash(secret_hash)