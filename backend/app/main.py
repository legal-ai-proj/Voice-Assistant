"""
FastAPI entrypoint. Run locally with:
    uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import inbound, voice_tools
from app.core.config import settings

app = FastAPI(
    title="AI Receptionist SaaS - Booking Service",
    description="Single source of truth for all booking logic -- shared by the website, "
    "admin dashboard, and the Vapi voice agent. No client (including the AI) touches "
    "the database directly; everything goes through this API.",
    version="0.1.0",
    docs_url="/docs",
)

# Loosen for local dev; replace with the actual Vercel domain(s) in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.ENVIRONMENT == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(voice_tools.router)
app.include_router(inbound.router)


@app.get("/health", tags=["meta"])
async def health_check() -> dict[str, str]:
    return {"status": "ok", "environment": settings.ENVIRONMENT}
