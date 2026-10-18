from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from smarthive.api.deps import CurrentUser

router = APIRouter(prefix="/api/v1", tags=["me"])


class Me(BaseModel):
    id: UUID
    email: str
    display_name: str
    role: str
    notify_email: bool
    ntfy_topic: str | None


@router.get("/me", response_model=Me, summary="The signed-in user")
async def me(user: CurrentUser) -> Me:
    return Me(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        notify_email=user.notify_email,
        ntfy_topic=user.ntfy_topic,
    )
