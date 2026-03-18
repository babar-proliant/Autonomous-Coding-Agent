"""
Enhanced session manager with state persistence and recovery.
"""

import json
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
import asyncio

from backend.config import settings
from backend.memory.database import db
from backend.memory.working_memory import WorkingMemory
from backend.core.event_bus import event_bus, EventType
from backend.utils import logger, AgentLogger, generate_id


@dataclass
class SessionState:
    """Serializable session state."""
    id: str
    project_name: str
    project_path: str
    status: str
    created_at: str
    updated_at: str
    
    # Working memory state
    working_memory_items: List[Dict[str, Any]]
    
    # Task tracking
    active_task_id: Optional[str]
    completed_task_ids: List[str]
    failed_task_ids: List[str]
    
    # Agent state
    current_agent: str
    
    # Checkpoint info
    last_checkpoint_id: Optional[str]
    checkpoint_count: int
    
    # Metadata
    metadata: Dict[str, Any]


class SessionPersistenceManager:
    """
    Manages session state persistence and recovery.
    
    Features:
    - Auto-save session state periodically
    - Recover sessions after crash
    - Export/import session state
    """
    
    def __init__(self):
        self._logger = AgentLogger("SessionPersistence")
        self._auto_save_interval = 30  # seconds
        self._auto_save_task: Optional[asyncio.Task] = None
    
    async def save_session_state(
        self,
        session_id: str,
        session_data: Dict[str, Any],
        working_memory: WorkingMemory
    ) -> bool:
        """
        Save session state to database.
        
        Args:
            session_id: Session ID
            session_data: In-memory session data
            working_memory: Working memory instance
            
        Returns:
            True if successful
        """
        try:
            # Serialize working memory
            memory_state = working_memory.get_state()
            
            # Create state object
            state = SessionState(
                id=session_id,
                project_name=session_data.get("project_name", "Untitled"),
                project_path=session_data.get("project_path", ""),
                status=session_data.get("status", "active"),
                created_at=session_data.get("created_at", datetime.utcnow().isoformat()),
                updated_at=datetime.utcnow().isoformat(),
                working_memory_items=memory_state.get("items", []),
                active_task_id=session_data.get("active_task_id"),
                completed_task_ids=session_data.get("completed_task_ids", []),
                failed_task_ids=session_data.get("failed_task_ids", []),
                current_agent=session_data.get("current_agent", "orchestrator"),
                last_checkpoint_id=session_data.get("last_checkpoint_id"),
                checkpoint_count=session_data.get("checkpoint_count", 0),
                metadata=session_data.get("metadata", {})
            )
            
            # Save to database
            state_json = json.dumps(asdict(state), default=str)
            
            await db.update(
                "sessions",
                {
                    "status": state.status,
                    "updated_at": datetime.utcnow().isoformat(),
                    "metadata": state_json
                },
                "id = ?",
                (session_id,)
            )
            
            self._logger.debug(f"Saved session state: {session_id}")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to save session state: {e}")
            return False
    
    async def load_session_state(
        self,
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Load session state from database.
        
        Args:
            session_id: Session ID to load
            
        Returns:
            Session data dict or None if not found
        """
        try:
            row = await db.fetch_one(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,)
            )
            
            if not row:
                return None
            
            # Parse metadata
            metadata = json.loads(row.get("metadata", "{}"))
            
            # Reconstruct session data
            session_data = {
                "id": session_id,
                "project_name": row.get("project_name", "Untitled"),
                "project_path": row.get("project_path", ""),
                "status": row.get("status", "active"),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
                "active_task_id": metadata.get("active_task_id"),
                "completed_task_ids": metadata.get("completed_task_ids", []),
                "failed_task_ids": metadata.get("failed_task_ids", []),
                "current_agent": metadata.get("current_agent", "orchestrator"),
                "last_checkpoint_id": metadata.get("last_checkpoint_id"),
                "checkpoint_count": metadata.get("checkpoint_count", 0),
                "metadata": metadata.get("metadata", {})
            }
            
            # Reconstruct working memory
            working_memory = WorkingMemory()
            memory_items = metadata.get("working_memory_items", [])
            working_memory.load_state({
                "items": memory_items,
                "current_tokens": sum(item.get("token_count", 0) for item in memory_items)
            })
            
            session_data["working_memory"] = working_memory
            
            self._logger.info(f"Loaded session state: {session_id}")
            return session_data
            
        except Exception as e:
            self._logger.error(f"Failed to load session state: {e}")
            return None
    
    async def list_recoverable_sessions(self) -> List[Dict[str, Any]]:
        """
        List all sessions that can be recovered.
        
        Returns:
            List of recoverable sessions
        """
        try:
            rows = await db.fetch_all(
                "SELECT id, project_name, status, updated_at FROM sessions WHERE status = 'active' ORDER BY updated_at DESC"
            )
            
            return [
                {
                    "id": row["id"],
                    "project_name": row["project_name"],
                    "status": row["status"],
                    "updated_at": row["updated_at"]
                }
                for row in rows
            ]
            
        except Exception as e:
            self._logger.error(f"Failed to list sessions: {e}")
            return []
    
    async def auto_save_loop(
        self,
        get_sessions: callable,
        get_session_data: callable
    ):
        """
        Background loop for auto-saving session states.
        
        Args:
            get_sessions: Function returning active session IDs
            get_session_data: Function returning session data for a session ID
        """
        while True:
            try:
                await asyncio.sleep(self._auto_save_interval)
                
                session_ids = get_sessions()
                for session_id in session_ids:
                    session_data = get_session_data(session_id)
                    if session_data and "working_memory" in session_data:
                        await self.save_session_state(
                            session_id,
                            session_data,
                            session_data["working_memory"]
                        )
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Auto-save error: {e}")
    
    def start_auto_save(self, get_sessions: callable, get_session_data: callable):
        """Start the auto-save background task."""
        if self._auto_save_task is None:
            self._auto_save_task = asyncio.create_task(
                self.auto_save_loop(get_sessions, get_session_data)
            )
            self._logger.info("Started auto-save background task")
    
    def stop_auto_save(self):
        """Stop the auto-save background task."""
        if self._auto_save_task:
            self._auto_save_task.cancel()
            self._auto_save_task = None
            self._logger.info("Stopped auto-save background task")


# Global instance
session_persistence = SessionPersistenceManager()


__all__ = ["SessionPersistenceManager", "SessionState", "session_persistence"]
