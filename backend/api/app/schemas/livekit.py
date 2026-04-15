from pydantic import BaseModel, Field


class LiveKitTokenRequest(BaseModel):
    """Optional room name; server generates one if omitted."""

    room_name: str | None = Field(default=None, max_length=128)


class LiveKitTokenResponse(BaseModel):
    server_url: str = Field(description="WebSocket URL for livekit-client Room.connect")
    room_name: str
    token: str
    participant_identity: str
