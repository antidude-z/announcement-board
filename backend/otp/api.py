import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from m2m import require_internal_token
from otp.core import SqlOtpIssuer

logger = logging.getLogger("legacy-backend.otp")


class IssueRequest(BaseModel):
    telegram_user_id: int


def create_otp_router(issuer: SqlOtpIssuer) -> APIRouter:
    router = APIRouter(tags=["internal-otp"])

    @router.post("/internal/otp/issue", dependencies=[Depends(require_internal_token)])
    async def issue_otp(payload: IssueRequest):
        logger.info("internal otp issue for tg=%s", payload.telegram_user_id)
        code = await issuer.issue(payload.telegram_user_id)
        return {"code": code}

    return router