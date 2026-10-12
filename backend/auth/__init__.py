"""Bounded context: Identity & Access (сессии, admin-логин, вход по OTP)."""

from auth.api import create_auth_router
from auth.dependencies import optional_principal, require_authenticated, require_admin
from auth.models import Base as AuthBase
from auth.repository import SqlAdminCredentialRepository
from auth.sessions import SESSION_REGISTRY, SessionRegistry, create_session_token
from auth.tokens import SessionPrincipal

__all__ = [
    "AuthBase",
    "SESSION_REGISTRY",
    "SessionPrincipal",
    "SessionRegistry",
    "SqlAdminCredentialRepository",
    "create_auth_router",
    "create_session_token",
    "optional_principal",
    "require_authenticated",
    "require_admin",
]