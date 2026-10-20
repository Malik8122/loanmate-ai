"""
Tracks the lifecycle of the per-room LiveKit voice agent.

The voice agent (backend/voice_agent/agent.py) is a long-running asyncio task
that joins a LiveKit room as a participant and runs STT -> LLM -> TTS on the
caller's audio. This manager starts one such task per room (keyed by room
name) and makes sure a second "Call Assistant" click doesn't spawn a
duplicate agent in the same room.
"""

from __future__ import annotations

import asyncio
import logging

from backend.voice_agent.agent import run_voice_agent

logger = logging.getLogger(__name__)


class AgentManager:
    def __init__(self):
        self._tasks: dict[str, asyncio.Task] = {}

    def is_running(self, room_name: str) -> bool:
        task = self._tasks.get(room_name)
        return task is not None and not task.done()

    def start(
        self,
        room_name: str,
        customer_id: str,
        session_id: str,
        call_direction: str = "inbound",
        outbound_reason: str | None = None,
    ) -> bool:
        """Start the voice agent for a room. Returns False if already running."""
        if self.is_running(room_name):
            return False

        task = asyncio.create_task(run_voice_agent(room_name, customer_id, session_id, call_direction, outbound_reason))
        self._tasks[room_name] = task

        def _on_done(t: asyncio.Task, _room=room_name):
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                logger.error("Voice agent for room %s crashed: %s", _room, exc)

        task.add_done_callback(_on_done)
        return True

    def stop(self, room_name: str) -> bool:
        """Stop the voice agent for a room. Returns False if it wasn't running."""
        task = self._tasks.pop(room_name, None)
        if task is None or task.done():
            return False
        task.cancel()
        return True


agent_manager = AgentManager()
