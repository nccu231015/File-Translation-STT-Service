"""
doc_redis.py
------------------
Manages document KM chat session storage using Redis.
- Each session has a unique ID (UUID), a title (from the first user message),
  a list of messages, and a creation timestamp.
- Ingested PDF file metadata is stored per session (key doc:sessionfiles:{session_id})
  for the UI; vector storage may still use a single Chroma collection.
- Session TTL: 7 days (604800 seconds) — longer than factory sessions.
- Reuses the same Redis instance; key prefix: "doc:session:"
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
SESSION_TTL = 604800  # 7 days
SESSION_INDEX_KEY = "doc:sessions:index"
# Per-session uploaded file metadata (UI list); legacy global key: doc:files:index (no longer read)
FILE_PREFIX = "doc:sessionfiles:"


def _session_key(session_id: str) -> str:
    return f"doc:session:{session_id}"


def _session_files_key(session_id: str) -> str:
    return f"{FILE_PREFIX}{session_id}"


class DocRedisStore:
    """
    Async Redis-backed session store for document KM chat.
    Falls back to in-memory dict if Redis is unavailable.
    """

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None
        self._in_memory: dict = {}
        self._index_memory: list = []
        # session_id -> list of file entry dicts (in-memory fallback for per-session file index)
        self._files_by_session: dict = {}
        self._use_redis = REDIS_AVAILABLE

    async def connect(self):
        if not self._use_redis:
            print("[DocRedis] redis package not installed, using in-memory fallback.")
            return
        try:
            self._redis = aioredis.from_url(REDIS_URL, decode_responses=True)
            await self._redis.ping()
            print(f"[DocRedis] ✓ Connected to Redis at {REDIS_URL}")
        except Exception as e:
            print(f"[DocRedis] ✗ Redis unavailable ({e}), switching to in-memory store.")
            self._use_redis = False
            self._redis = None

    # ── Session CRUD ─────────────────────────────────────────────────────────

    async def create_empty_session(self, title: str = "新對話") -> dict:
        """Create a session with no messages (e.g. first action is file upload)."""
        session_id = str(uuid.uuid4())
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
        try:
            if self._use_redis and self._redis:
                raw = await self._redis.get(SESSION_INDEX_KEY)
                if not raw:
                    return []
                index: list = json.loads(raw)
            else:
                index = self._index_memory

            result = []
            for entry in reversed(index):  # newest first
                try:
                    sid = entry.get("session_id")
                    if not sid:
                        continue
                    session = await self.get_session(sid)
                    if session:
                        result.append({
                            "session_id": sid,
                            "title": entry.get("title", "無標題"),
                            "created_at": entry.get("created_at", session.get("created_at")),
                            "updated_at": session.get("updated_at", entry.get("created_at")),
                            "message_count": len(session.get("messages", [])),
                        })
                except Exception as entry_e:
                    print(f"[DocRedis] Skip corrupted entry {entry}: {entry_e}")
                    continue
            return result
        except Exception as e:
            print(f"[DocRedis] list_sessions failed: {e}")
            return []

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session by ID and its per-session file index."""
        if self._use_redis and self._redis:
            await self._redis.delete(_session_files_key(session_id))
            deleted = await self._redis.delete(_session_key(session_id))
            raw = await self._redis.get(SESSION_INDEX_KEY)
            if raw:
                index = [e for e in json.loads(raw) if e["session_id"] != session_id]
                await self._redis.set(SESSION_INDEX_KEY, json.dumps(index), ex=SESSION_TTL)
            return bool(deleted)
        else:
            existed = session_id in self._in_memory
            self._in_memory.pop(session_id, None)
            self._index_memory = [e for e in self._index_memory if e["session_id"] != session_id]
            self._files_by_session.pop(session_id, None)
            return existed

    # ── Internal Helpers ─────────────────────────────────────────────────────

    async def _save_session(self, session: dict):
        sid = session["session_id"]
        if self._use_redis and self._redis:
            await self._redis.set(
                _session_key(sid),
                json.dumps(session, ensure_ascii=False),
                ex=SESSION_TTL,
            )
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

    # ── Per-session file metadata (UI only; Chroma may still use one collection) ──

    async def add_file(self, session_id: str, filename: str, size: int) -> dict:
        """Record an ingested file under a chat session's file list."""
        now = datetime.utcnow().isoformat()
        entry = {"filename": filename, "size": size, "uploaded_at": now}
        if self._use_redis and self._redis:
            key = _session_files_key(session_id)
            raw = await self._redis.get(key)
            files: list = json.loads(raw) if raw else []
            files = [f for f in files if f.get("filename") != filename]
            files.append(entry)
            await self._redis.set(
                key, json.dumps(files, ensure_ascii=False), ex=SESSION_TTL
            )
        else:
            lst = self._files_by_session.setdefault(session_id, [])
            self._files_by_session[session_id] = [f for f in lst if f.get("filename") != filename]
            self._files_by_session[session_id].append(entry)
        return entry

    async def list_files(self, session_id: str) -> List[dict]:
        """Return files uploaded for a session, newest first in the list UI."""
        if not session_id:
            return []
        if self._use_redis and self._redis:
            raw = await self._redis.get(_session_files_key(session_id))
            files = json.loads(raw) if raw else []
        else:
            files = self._files_by_session.get(session_id, [])
        return list(reversed(files))

    async def delete_file(self, session_id: str, filename: str) -> bool:
        """Remove a file record from a session's list (does not remove Chroma entries)."""
        if not session_id:
            return False
        if self._use_redis and self._redis:
            key = _session_files_key(session_id)
            raw = await self._redis.get(key)
            if not raw:
                return False
            files = json.loads(raw)
            new_files = [f for f in files if f.get("filename") != filename]
            existed = len(new_files) < len(files)
            await self._redis.set(
                key, json.dumps(new_files, ensure_ascii=False), ex=SESSION_TTL
            )
            return existed
        else:
            files = self._files_by_session.get(session_id, [])
            new_files = [f for f in files if f.get("filename") != filename]
            existed = len(new_files) < len(files)
            self._files_by_session[session_id] = new_files
            return existed


# Global singleton
doc_store = DocRedisStore()
