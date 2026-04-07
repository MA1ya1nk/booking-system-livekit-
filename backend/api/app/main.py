from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.appointments import router as appointments_router
from app.api.routes.auth import router as auth_router
from app.api.routes.services import router as services_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.models import appointment, service, user  # noqa: F401

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(services_router, prefix=settings.api_v1_prefix)
app.include_router(appointments_router, prefix=settings.api_v1_prefix)
