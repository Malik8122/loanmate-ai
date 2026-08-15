"""
In-memory session store for conversation context.
"""

from __future__ import annotations

from typing import Any

# Simple in-memory dict keyed by session_id
_sessions: dict[str, list[dict[str, Any]]] = {}


class SessionStore:
    @staticmethod
    def get_or_create(session_id: str) -> list[dict[str, Any]]:
        """Retrieve conversation history for a session, creating it if necessary."""
        if session_id not in _sessions:
            _sessions[session_id] = []
        return _sessions[session_id]

    @staticmethod
    def clear(session_id: str) -> None:
        """Clear conversation history for a session."""
        if session_id in _sessions:
            _sessions[session_id] = []
