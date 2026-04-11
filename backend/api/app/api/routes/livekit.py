import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from livekit import api
from app.api.deps import get_optional_current_user
from app.core.config import settings
from app.models.user import User
from app.schemas.livekit import LiveKitTokenRequest, LiveKitTokenResponse

router = APIRouter(prefix="/livekit", tags=["livekit"])


def _livekit_configured() -> bool:
    return bool(
        (settings.livekit_url or "").strip()
        and (settings.livekit_api_key or "").strip()
        and (settings.livekit_api_secret or "").strip()
    )


@router.post("/token", response_model=LiveKitTokenResponse)
def issue_livekit_token(
    payload: LiveKitTokenRequest | None = None,
    current_user: User | None = Depends(get_optional_current_user),
):
    """Mint a participant token for the browser; embeds agent dispatch for `livekit_agent_name`."""
    if not _livekit_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LiveKit is not configured on the server",
        )

    body = payload or LiveKitTokenRequest()
    room_name = (body.room_name or "").strip()
    if not room_name:
        room_name = f"hospital-{uuid.uuid4().hex[:12]}"

    if current_user:
        identity = f"user-{current_user.id}"
        display_name = current_user.name
    else:
        identity = f"guest-{uuid.uuid4().hex[:12]}"
        display_name = "Guest"

    grant = api.VideoGrants(
        room_join=True,
        room=room_name,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=True,
    )

    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_name(display_name)
        .with_grants(grant)
        .with_room_config(
            api.RoomConfiguration(
                agents=[
                    api.RoomAgentDispatch(agent_name=settings.livekit_agent_name),
                ],
            ),
        )
        .to_jwt()
    )

    server_url = settings.livekit_url.strip()
    return LiveKitTokenResponse(
        server_url=server_url,
        room_name=room_name,
        token=token,
        participant_identity=identity,
    )
