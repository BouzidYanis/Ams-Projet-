import uuid
import time
from typing import Dict, Any

# Simple in-memory session store with TTL. For production, utiliser Redis or DB.
class SessionStore:
    def __init__(self, ttl_seconds: int = 3600):
        self.ttl = ttl_seconds
        self._store: Dict[str, Dict[str, Any]] = {}
        self._meta: Dict[str, float] = {}

    def create_session(self) -> str:
        sid = str(uuid.uuid4())
        self._store[sid] = {"created_at": time.time(), "last_intent": None, "fallbacks": 0}
        self._meta[sid] = time.time()
        return sid

    def get(self, session_id: str) -> Dict[str, Any]:
        if session_id not in self._store:
            # create one to be permissive
            self._store[session_id] = {"created_at": time.time(), "last_intent": None, "fallbacks": 0}
        self._meta[session_id] = time.time()
        return self._store[session_id]

    def update(self, session_id: str, data: Dict[str, Any]) -> None:
        self._store[session_id] = data
        self._meta[session_id] = time.time()

    def reset(self, session_id: str) -> bool:
        if session_id in self._store:
            self._store[session_id] = {"created_at": time.time(), "last_intent": None, "fallbacks": 0}
            self._meta[session_id] = time.time()
            return True
        return False

    def cleanup(self):
        now = time.time()
        for sid, touched in list(self._meta.items()):
            if now - touched > self.ttl:
                del self._meta[sid]
                del self._store[sid]