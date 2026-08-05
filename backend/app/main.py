"""
FastAPI entrypoint. Run locally with:
    uvicorn app.main:app --reload
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

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


class ConnectionCloseMiddleware(BaseHTTPMiddleware):
    """Force every response to include 'Connection: close'.

    This tells HTTP clients (including Vapi's Node.js HTTP client) not to
    pool or reuse this connection. Without this, Vapi reuses keep-alive
    connections that Railway's infrastructure has already silently closed
    at the load balancer level, causing ECONNRESET errors on subsequent
    tool calls within the same call session. The --timeout-keep-alive
    uvicorn flag only controls uvicorn's own idle timeout, not Railway's
    infrastructure layer -- so the only reliable fix is to prevent
    connection reuse entirely by telling clients to close after each
    request.

    This trades the marginal efficiency gain of connection reuse (which
    doesn't matter for low-frequency voice tool calls) for complete
    elimination of the ECONNRESET class of errors.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Connection"] = "close"
        return response


app.add_middleware(ConnectionCloseMiddleware)
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
