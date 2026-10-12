"""Антикоррупционный слой для Telegram Allowlist (bot-service)."""

from integrations.telegram_allowlist.dto import TelegramAllowlistEntry
from integrations.telegram_allowlist.http_gateway import HttpTelegramAllowlistGateway
from integrations.telegram_allowlist.ports import TelegramAllowlistGateway

__all__ = [
    "HttpTelegramAllowlistGateway",
    "TelegramAllowlistEntry",
    "TelegramAllowlistGateway",
]