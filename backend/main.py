"""
BFSI Loan & EMI Voice Assistant — FastAPI Backend
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes import voice, loan, customer, apply, livekit, realtime

# The root logger defaults to WARNING, which silently drops the [LIVEKIT]/[STT]/
# [AGENT]/[TOOL]/[TTS] diagnostic logger.info(...) calls used throughout the voice
# pipeline. Raise it so those are actually visible to developers.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="BFSI Voice Assistant API",
    description="Conversational voice assistant for loan & EMI queries in the BFSI domain.",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# CORS — allow the Streamlit frontend (and any dev tool) to call the API
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Register routers
# ---------------------------------------------------------------------------
app.include_router(voice.router, prefix="/api/voice", tags=["Voice"])
app.include_router(loan.router, prefix="/api/loan", tags=["Loan"])
app.include_router(apply.router, prefix="/api/apply", tags=["Apply"])
app.include_router(customer.router, prefix="/api/customer", tags=["Customer"])
app.include_router(livekit.router, prefix="/api/livekit", tags=["LiveKit"])
app.include_router(realtime.router, prefix="/api/realtime", tags=["Realtime"])


# ---------------------------------------------------------------------------
# Health-check
# ---------------------------------------------------------------------------
@app.get("/health", tags=["System"])
async def health_check():
    """Simple liveness probe."""
    return {"status": "ok", "service": "bfsi-voice-assistant"}
