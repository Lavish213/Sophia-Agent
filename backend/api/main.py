from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from backend.api.routes import (
    calls,
    comps,
    discovery,
    dispo,
    health,
    intake,
    leads,
    offers,
    properties,
    sms_webhook,
    workers,
)
from backend.voice.webhook import router as voice_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("sophia_agent_api_starting")
    yield


app = FastAPI(title="Sophia Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(properties.router, prefix="/api")
app.include_router(leads.router, prefix="/api")
app.include_router(comps.router, prefix="/api")
app.include_router(offers.router, prefix="/api")
app.include_router(calls.router, prefix="/api")
app.include_router(voice_router, prefix="/api")
app.include_router(sms_webhook.router, prefix="/api")
app.include_router(discovery.router, prefix="/api")
app.include_router(intake.router, prefix="/api")
app.include_router(dispo.router, prefix="/api")
app.include_router(workers.router, prefix="/api")
