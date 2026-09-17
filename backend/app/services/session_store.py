"""In-memory session store.

Holds processed datasets in RAM (never written to persistent disk),
separately retaining the raw null profile and the imputed modeling data.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional
import pandas as pd

from app.config import settings
from app.models.schemas import ColumnNullProfile, DetectedFileKind, DetectedFormat


@dataclass
class IngestedSession:
    file_id: str
    file_name: str
    file_size_bytes: int
    detected_kind: DetectedFileKind
    detected_format: DetectedFormat
    raw_dataframe: Optional[pd.DataFrame] = None
    raw_null_profile: Optional[Dict[str, ColumnNullProfile]] = None
    imputed_modeling_data: Optional[pd.DataFrame] = None
    document_text: Optional[str] = None
    created_at: float = field(default_factory=time.time)


class InMemorySessionStore:
    """Thread-safe in-memory session cache."""

    def __init__(self):
        self._lock = threading.Lock()
        self._sessions: Dict[str, IngestedSession] = {}

    def save_session(self, session: IngestedSession) -> None:
        with self._lock:
            self._prune_expired_locked()
            self._sessions[session.file_id] = session

    def get_session(self, file_id: str) -> Optional[IngestedSession]:
        with self._lock:
            session = self._sessions.get(file_id)
            if not session:
                return None
            # Check TTL expiration
            if time.time() - session.created_at > settings.SESSION_TTL_SECONDS:
                del self._sessions[file_id]
                return None
            return session

    def delete_session(self, file_id: str) -> bool:
        with self._lock:
            if file_id in self._sessions:
                del self._sessions[file_id]
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()

    def _prune_expired_locked(self) -> None:
        now = time.time()
        expired = [
            fid
            for fid, s in self._sessions.items()
            if now - s.created_at > settings.SESSION_TTL_SECONDS
        ]
        for fid in expired:
            del self._sessions[fid]


# Global singleton instance
session_store = InMemorySessionStore()
