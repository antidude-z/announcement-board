import logging

from fastapi import APIRouter
from pydantic import BaseModel

from otp.core import SqlOtpIssuer

logger = logging.getLogger("legacy-backend.otp")


class IssueRequest(BaseModel):
    telegram_user_id: int


def create_otp_router(issuer: SqlOtpIssuer) -> APIRouter:
    router = APIRouter(tags=["internal-otp"])

    @router.post("/internal/otp/issue")
    async def issue_otp(payload: IssueRequest):
        logger.info("internal otp issue for tg=%s", payload.telegram_user_id)
        code = await issuer.issue(payload.telegram_user_id)
        return {"code": code}

    return router