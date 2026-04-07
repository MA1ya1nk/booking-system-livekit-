import logging
import os

import httpx
from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    cli,
    function_tool,
    inference,
    room_io,
)
from livekit.plugins import noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")

load_dotenv(".env.local")
HOSPITAL_API_BASE_URL = os.getenv("HOSPITAL_API_BASE_URL", "http://127.0.0.1:8000/api/v1")


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are a hospital voice assistant. The user is interacting with you via voice.
            Use tools to answer hospital service questions such as available services, price, slot duration and service timings.
            Keep responses concise, clear, and plain text without special formatting.
            Important: Appointment booking is not enabled yet. If asked to book, clearly say booking via voice is coming soon.""",
        )

    async def _fetch_services(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{HOSPITAL_API_BASE_URL}/services")
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, list) else []

    @function_tool
    async def list_hospital_services(self, context: RunContext) -> str:
        """List all available hospital services with basic details."""
        services = await self._fetch_services()
        if not services:
            return "No services are available right now."

        lines = []
        for service in services:
            lines.append(
                f"{service['name']}: price Rs {service['price']}, "
                f"duration {service['slot_duration_minutes']} minutes, "
                f"time {service['slot_start_time']} to {service['slot_end_time']}"
            )
        return "Available services are: " + " | ".join(lines)

    @function_tool
    async def get_service_details(self, context: RunContext, service_name: str) -> str:
        """Get detailed information about one hospital service by name."""
        services = await self._fetch_services()
        target = service_name.strip().lower()
        matched = [item for item in services if target in item["name"].lower()]
        if not matched:
            return f"I could not find a service named {service_name}."

        service = matched[0]
        return (
            f"{service['name']} costs Rs {service['price']}. "
            f"Slot duration is {service['slot_duration_minutes']} minutes. "
            f"Available timing is {service['slot_start_time']} to {service['slot_end_time']}."
        )

    @function_tool
    async def explain_voice_booking_status(self, context: RunContext) -> str:
        """Explain whether appointment booking through voice is currently enabled."""
        return (
            "Voice booking is not enabled yet. "
            "I can currently provide service information like prices, slot duration and timings."
        )


server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext):
    # Logging setup
    # Add any other context you want in all log entries here
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # Set up a voice AI pipeline using OpenAI, Cartesia, Deepgram, and the LiveKit turn detector
    session = AgentSession(
        # Speech-to-text (STT) is your agent's ears, turning the user's speech into text that the LLM can understand
        # See all available models at https://docs.livekit.io/agents/models/stt/
        stt=inference.STT(model="deepgram/nova-3", language="multi"),
        # A Large Language Model (LLM) is your agent's brain, processing user input and generating a response
        # See all available models at https://docs.livekit.io/agents/models/llm/
        llm=inference.LLM(model="openai/gpt-4.1-mini"),
        # Text-to-speech (TTS) is your agent's voice, turning the LLM's text into speech that the user can hear
        # See all available models as well as voice selections at https://docs.livekit.io/agents/models/tts/
        tts=inference.TTS(
            model="cartesia/sonic-3", voice="9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"
        ),
        # VAD and turn detection are used to determine when the user is speaking and when the agent should respond
        # See more at https://docs.livekit.io/agents/build/turns
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        # allow the LLM to generate a response while waiting for the end of turn
        # See more at https://docs.livekit.io/agents/build/audio/#preemptive-generation
        preemptive_generation=True,
    )

    # To use a realtime model instead of a voice pipeline, use the following session setup instead.
    # (Note: This is for the OpenAI Realtime API. For other providers, see https://docs.livekit.io/agents/models/realtime/))
    # 1. Install livekit-agents[openai]
    # 2. Set OPENAI_API_KEY in .env.local
    # 3. Add `from livekit.plugins import openai` to the top of this file
    # 4. Use the following session setup instead of the version above
    # session = AgentSession(
    #     llm=openai.realtime.RealtimeModel(voice="marin")
    # )

    # # Add a virtual avatar to the session, if desired
    # # For other providers, see https://docs.livekit.io/agents/models/avatar/
    # avatar = hedra.AvatarSession(
    #   avatar_id="...",  # See https://docs.livekit.io/agents/models/avatar/plugins/hedra
    # )
    # # Start the avatar and wait for it to join
    # await avatar.start(session, room=ctx.room)

    # Start the session, which initializes the voice pipeline and warms up the models
    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: (
                    noise_cancellation.BVCTelephony()
                    if params.participant.kind
                    == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                    else noise_cancellation.BVC()
                ),
            ),
        ),
    )

    # Join the room and connect to the user
    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(server)
