import json
import logging
import os
import re
from datetime import date, datetime, timedelta

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
from livekit.agents.inference.tts import CartesiaOptions
from livekit.plugins import noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")

load_dotenv(".env.local")
HOSPITAL_API_BASE_URL = os.getenv("HOSPITAL_API_BASE_URL", "http://127.0.0.1:8000/api/v1")


def _voice_headers() -> dict[str, str] | None:
    key = os.getenv("HOSPITAL_AGENT_API_KEY", "").strip()
    if not key:
        return None
    return {"X-Agent-Key": key}


async def _http_error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
        detail = body.get("detail")
        if isinstance(detail, str):
            return detail
        if isinstance(detail, list):
            return "; ".join(
                str(item.get("msg", item)) if isinstance(item, dict) else str(item)
                for item in detail
            )
        return response.text[:800]
    except (json.JSONDecodeError, TypeError):
        return response.text[:800]


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are a hospital voice assistant. Users speak to you by voice.
            You can list services, give prices and slot rules, and help registered users book or cancel appointments.

            Booking flow (when the user wants to book):
            1) Confirm which service (name). Use resolve_service_by_name to get service_id.
            2) Ask which date and what time they want. Use resolve_appointment_time to convert natural language
               such as "tomorrow at 10 am" into a local ISO datetime string (YYYY-MM-DDTHH:MM:00).
            3) Call check_voice_slot_available with service_id and that ISO string. If not available, say why and ask for another time.
            4) Ask for the email they used when registering on the website. Call verify_registered_email. If no account exists, say they must register on the website first; do not book.
            5) Call book_voice_appointment with the same email, service_id, and appointment time. Confirm success clearly.

            Cancel flow (when the user wants to cancel):
            1) Ask for their registered email. Call verify_registered_email if unsure the account exists.
            2) Call list_voice_upcoming_appointments with that email. Read back each booking with its appointment id, service, and time.
            3) Ask which booking to cancel (match by what they say to an appointment_id from the list).
            4) Call cancel_voice_appointment with email and appointment_id. Confirm cancellation clearly.

            If asked for "available services", provide only service names unless the user asks for more details.
            Keep answers short, plain text, no markdown or bullet symbols. Never ask for passwords.
            If voice booking tools say the agent key is not configured, tell the user booking is temporarily unavailable.""",
        )

    async def _fetch_services(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{HOSPITAL_API_BASE_URL}/services")
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, list) else []

    @function_tool
    async def list_hospital_services(self, context: RunContext) -> str:
        """List all available hospital service names only."""
        services = await self._fetch_services()
        if not services:
            return "No services are available right now."

        names = [service["name"] for service in services]
        return "Available services are: " + ", ".join(names)

    @function_tool
    async def resolve_service_by_name(self, context: RunContext, service_name: str) -> str:
        """Look up a service by name and return its id and slot rules. Use before booking."""
        services = await self._fetch_services()
        target = service_name.strip().lower()
        matched = [item for item in services if target in item["name"].lower()]
        if not matched:
            return f"No service matching '{service_name}'. Ask the user to pick from the listed services."
        s = matched[0]
        return (
            f"service_id={s['id']}, name={s['name']}, price Rs {s['price']}, "
            f"slot every {s['slot_duration_minutes']} minutes, "
            f"hours {s['slot_start_time']} to {s['slot_end_time']}. "
            f"Choose a time on a valid slot boundary within those hours."
        )

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
    async def resolve_appointment_time(
        self,
        context: RunContext,
        when_text: str,
        time_text: str | None = None,
    ) -> str:
        """Convert natural phrases like 'tomorrow at 10 am' to local ISO datetime YYYY-MM-DDTHH:MM:00."""
        text = " ".join(part.strip() for part in [when_text or "", time_text or ""] if part).lower()
        if not text:
            return "Could not resolve date/time: empty input"

        base_day = date.today()
        if "day after tomorrow" in text:
            target_day = base_day + timedelta(days=2)
        elif "tomorrow" in text:
            target_day = base_day + timedelta(days=1)
        elif "today" in text:
            target_day = base_day
        else:
            # Absolute date forms expected from LLM/user
            date_match = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text)
            if not date_match:
                return (
                    "Could not resolve date. Ask user for date like YYYY-MM-DD or say today/tomorrow."
                )
            try:
                year, month, day = map(int, date_match.groups())
                target_day = date(year, month, day)
            except ValueError:
                return "Could not resolve date: invalid calendar date."

        # Time patterns: 10, 10:30, 10 am, 10:30 pm
        time_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", text)
        if not time_match:
            return "Could not resolve time. Ask user for time like 10:00 or 10 am."
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        meridiem = time_match.group(3)

        if meridiem:
            if hour < 1 or hour > 12:
                return "Could not resolve time: hour must be 1-12 with am/pm."
            if meridiem == "am":
                hour = 0 if hour == 12 else hour
            else:
                hour = 12 if hour == 12 else hour + 12
        else:
            if hour > 23:
                return "Could not resolve time: hour must be 0-23."

        if minute > 59:
            return "Could not resolve time: minute must be 0-59."

        resolved = datetime(
            target_day.year,
            target_day.month,
            target_day.day,
            hour,
            minute,
            0,
        )
        return resolved.isoformat(timespec="seconds")

    @function_tool
    async def verify_registered_email(self, context: RunContext, email: str) -> str:
        """Check whether an email is registered before booking. Requires HOSPITAL_AGENT_API_KEY on the agent."""
        headers = _voice_headers()
        if not headers:
            return (
                "Voice booking is not configured: missing HOSPITAL_AGENT_API_KEY in the agent environment."
            )
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{HOSPITAL_API_BASE_URL}/agent/verify-email",
                json={"email": email.strip()},
                headers=headers,
            )
        if r.status_code == 200:
            data = r.json()
            exists = data.get("exists", False)
            return (
                "That email is registered. You can proceed to book."
                if exists
                else "No account exists with that email. The user must register on the website before booking."
            )
        if r.status_code in (401, 503):
            return f"Could not verify email (server): {await _http_error_detail(r)}"
        return f"Could not verify email: {await _http_error_detail(r)}"

    @function_tool
    async def check_voice_slot_available(
        self, context: RunContext, service_id: int, appointment_time_iso: str
    ) -> str:
        """Check if a slot is valid and still free. appointment_time_iso like 2026-04-08T10:30:00 (local, no timezone)."""
        headers = _voice_headers()
        if not headers:
            return (
                "Voice booking is not configured: missing HOSPITAL_AGENT_API_KEY in the agent environment."
            )
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"{HOSPITAL_API_BASE_URL}/agent/slot-available",
                params={"service_id": service_id, "appointment_time": appointment_time_iso},
                headers=headers,
            )
        if r.status_code != 200:
            return f"Could not check slot: {await _http_error_detail(r)}"
        data = r.json()
        if data.get("available"):
            return "The slot is available. You can continue with email verification and booking."
        reason = data.get("reason") or "unknown"
        return f"The slot is not available: {reason}"

    @function_tool
    async def book_voice_appointment(
        self,
        context: RunContext,
        email: str,
        service_id: int,
        appointment_time_iso: str,
        note: str | None = None,
    ) -> str:
        """Book the appointment for a registered email. Only call after verify_registered_email and slot check."""
        headers = _voice_headers()
        if not headers:
            return (
                "Voice booking is not configured: missing HOSPITAL_AGENT_API_KEY in the agent environment."
            )
        payload = {
            "email": email.strip(),
            "service_id": service_id,
            "appointment_time": appointment_time_iso,
            "note": (note.strip() if note and note.strip() else None),
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{HOSPITAL_API_BASE_URL}/agent/appointments",
                json=payload,
                headers=headers,
            )
        if r.status_code == 200:
            data = r.json()
            when = data.get("appointment_time", appointment_time_iso)
            svc = data.get("service") or {}
            svc_name = svc.get("name", "the service")
            return f"Booked successfully for {svc_name} at {when}."
        return f"Booking failed: {await _http_error_detail(r)}"

    @function_tool
    async def list_voice_upcoming_appointments(self, context: RunContext, email: str) -> str:
        """List this user's future booked appointments (appointment id, service, time). Use before cancel."""
        headers = _voice_headers()
        if not headers:
            return (
                "Voice booking is not configured: missing HOSPITAL_AGENT_API_KEY in the agent environment."
            )
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"{HOSPITAL_API_BASE_URL}/agent/my-appointments",
                params={"email": email.strip()},
                headers=headers,
            )
        if r.status_code == 200:
            data = r.json()
            items = data.get("appointments") or []
            if not items:
                return "No upcoming bookings found for that email."
            lines = []
            for a in items:
                lines.append(
                    f"id {a['appointment_id']}: {a['service_name']} at {a['appointment_time']}"
                )
            return "Upcoming bookings: " + " | ".join(lines)
        if r.status_code == 404:
            return "No registered account with that email."
        return f"Could not list appointments: {await _http_error_detail(r)}"

    @function_tool
    async def cancel_voice_appointment(
        self, context: RunContext, email: str, appointment_id: int
    ) -> str:
        """Cancel a booking. Use appointment_id from list_voice_upcoming_appointments."""
        headers = _voice_headers()
        if not headers:
            return (
                "Voice booking is not configured: missing HOSPITAL_AGENT_API_KEY in the agent environment."
            )
        payload = {"email": email.strip(), "appointment_id": appointment_id}
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{HOSPITAL_API_BASE_URL}/agent/appointments/cancel",
                json=payload,
                headers=headers,
            )
        if r.status_code == 200:
            data = r.json()
            when = data.get("appointment_time", "")
            svc = data.get("service") or {}
            svc_name = svc.get("name", "the service")
            return f"Cancelled: {svc_name} at {when}."
        return f"Cancellation failed: {await _http_error_detail(r)}"


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
            model="cartesia/sonic-3",
            voice="9626c31c-bec5-4cca-baa8-f8ba9e84c8bc",
            extra_kwargs=CartesiaOptions(speed="normal"),
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
