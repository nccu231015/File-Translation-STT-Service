"""
factory_redis.py
------------------
Manages factory chat session storage using Redis.
- Each session has a unique ID (UUID), a title (from the first user message),
  a list of messages, and a creation timestamp.
- Session TTL: 24 hours (86400 seconds).
- Requires a Redis instance running on localhost:6379 (or REDIS_URL env var).
"""

import os
import json
import uuid
from datetime import datetime
from typing import List, Optional

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
SESSION_TTL = 86400  # 24 hours
SESSION_INDEX_KEY = "factory:sessions:index"


def _session_key(session_id: str) -> str:
    return f"factory:session:{session_id}"


class FactoryRedisStore:
    """
    Async Redis-backed session store for factory chat.
    Falls back to in-memory dict if Redis is unavailable.
    """

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None
        self._in_memory: dict = {}   # fallback
        self._index_memory: list = []  # fallback index
        self._use_redis = REDIS_AVAILABLE

    async def connect(self):
        if not self._use_redis:
            print("[FactoryRedis] redis package not installed, using in-memory fallback.")
            return
        try:
            self._redis = aioredis.from_url(REDIS_URL, decode_responses=True)
            await self._redis.ping()
            print(f"[FactoryRedis] ✓ Connected to Redis at {REDIS_URL}")
        except Exception as e:
            print(f"[FactoryRedis] ✗ Redis unavailable ({e}), switching to in-memory store.")
            self._use_redis = False
            self._redis = None

    # ── Session CRUD ─────────────────────────────────────────────────────────

    async def create_session(self, first_message: str) -> dict:
        """Create a new session with the first user message as the title."""
        session_id = str(uuid.uuid4())
        title = first_message[:40] + ("..." if len(first_message) > 40 else "")
        now = datetime.utcnow().isoformat()

        session = {
            "session_id": session_id,
            "title": title,
            "messages": [],
            "created_at": now,
            "updated_at": now,
        }

        await self._save_session(session)
        await self._add_to_index(session_id, title, now)
        return session

    async def get_session(self, session_id: str) -> Optional[dict]:
        """Retrieve a session by ID."""
        if self._use_redis and self._redis:
            raw = await self._redis.get(_session_key(session_id))
            if raw:
                return json.loads(raw)
            return None
        return self._in_memory.get(session_id)

    async def append_messages(self, session_id: str, user_msg: str, ai_msg: str) -> bool:
        """Append a user/assistant message pair to a session."""
        session = await self.get_session(session_id)
        if not session:
            return False

        now = datetime.utcnow().isoformat()
        session["messages"].append({"role": "user", "content": user_msg, "ts": now})
        session["messages"].append({"role": "assistant", "content": ai_msg, "ts": now})
        session["updated_at"] = now

        await self._save_session(session)
        return True

    async def list_sessions(self) -> List[dict]:
        """Return a summary list of all sessions, newest first."""
        if self._use_redis and self._redis:
            raw = await self._redis.get(SESSION_INDEX_KEY)
            if not raw:
                return []
            index: list = json.loads(raw)
        else:
            index = self._index_memory

        # Filter out expired in-memory sessions
        result = []
        for entry in reversed(index):  # newest first
            sid = entry["session_id"]
            session = await self.get_session(sid)
            if session:
                result.append({
                    "session_id": sid,
                    "title": entry["title"],
                    "created_at": entry["created_at"],
                    "updated_at": session.get("updated_at", entry["created_at"]),
                    "message_count": len(session.get("messages", [])),
                })
        return result

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session by ID."""
        if self._use_redis and self._redis:
            deleted = await self._redis.delete(_session_key(session_id))
            # Remove from index
            raw = await self._redis.get(SESSION_INDEX_KEY)
            if raw:
                index = [e for e in json.loads(raw) if e["session_id"] != session_id]
                await self._redis.set(SESSION_INDEX_KEY, json.dumps(index), ex=SESSION_TTL)
            return bool(deleted)
        else:
            existed = session_id in self._in_memory
            self._in_memory.pop(session_id, None)
            self._index_memory = [e for e in self._index_memory if e["session_id"] != session_id]
            return existed

    # ── Internal Helpers ─────────────────────────────────────────────────────

    async def _save_session(self, session: dict):
        sid = session["session_id"]
        if self._use_redis and self._redis:
            await self._redis.set(_session_key(sid), json.dumps(session, ensure_ascii=False), ex=SESSION_TTL)
        else:
            self._in_memory[sid] = session

    async def _add_to_index(self, session_id: str, title: str, created_at: str):
        entry = {"session_id": session_id, "title": title, "created_at": created_at}
        if self._use_redis and self._redis:
            raw = await self._redis.get(SESSION_INDEX_KEY)
            index = json.loads(raw) if raw else []
            index.append(entry)
            await self._redis.set(SESSION_INDEX_KEY, json.dumps(index), ex=SESSION_TTL)
        else:
            self._index_memory.append(entry)


# Global singleton
factory_store = FactoryRedisStore()
