"""
In-memory transcript buffer for LiveKit voice calls.

The voice agent (backend/voice_agent/agent.py) runs in its own asyncio
task with no direct link to the Streamlit session that started the
call. This store is the bridge: the agent appends each turn as it
happens, and the frontend fetches (and clears) the buffer once the
user hangs up, so the voice conversation becomes part of the visible
chat history instead of disappearing when the call ends.
"""

from __future__ import annotations

from typing import Any

_transcripts: dict[str, list[dict[str, Any]]] = {}


class CallTranscriptStore:
    @staticmethod
    def append(session_id: str, role: str, text: str) -> None:
        _transcripts.setdefault(session_id, []).append({"role": role, "text": text})

    @staticmethod
    def get_and_clear(session_id: str) -> list[dict[str, Any]]:
        return _transcripts.pop(session_id, [])

    @staticmethod
    def peek(session_id: str, since_index: int = 0) -> list[dict[str, Any]]:
        """Read entries from `since_index` onward without clearing — used by the
        live in-call transcript, which polls repeatedly while the call is active.
        """
        return _transcripts.get(session_id, [])[since_index:]
