"""
Event bus for inter-agent communication and SSE streaming.
"""

import asyncio
from typing import Dict, Any, Optional, List, AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
from collections import defaultdict


class EventType(str, Enum):
    """Types of events in the system."""
    # Session events
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    
    # Thinking events (streaming)
    THINKING_START = "thinking_start"
    THINKING_STREAM = "thinking_stream"
    THINKING_END = "thinking_end"
    
    # Tool events
    TOOL_START = "tool_start"
    TOOL_OUTPUT = "tool_output"
    TOOL_RESULT = "tool_result"
    TOOL_ERROR = "tool_error"
    
    # Task events
    TASK_CREATED = "task_created"
    TASK_STARTED = "task_started"
    TASK_PROGRESS = "task_progress"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    
    # Agent events
    AGENT_SWITCH = "agent_switch"
    AGENT_ACTIVITY = "agent_activity"
    
    # Error events
    ERROR = "error"
    WARNING = "warning"
    
    # Control events
    DONE = "done"
    CONNECTED = "connected"


@dataclass
class Event:
    """An event in the system."""
    event_type: EventType
    session_id: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def to_sse(self) -> str:
        """Convert to SSE format."""
        return f"event: {self.event_type.value}\ndata: {json.dumps(self.data)}\n\n"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_type": self.event_type.value,
            "session_id": self.session_id,
            "data": self.data,
            "timestamp": self.timestamp
        }


class EventBus:
    """
    Event bus for publishing and subscribing to events.
    Supports SSE streaming to clients.
    """
    
    _instance: Optional['EventBus'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        self._subscribers: Dict[str, List[asyncio.Queue]] = defaultdict(list)
        self._global_subscribers: List[asyncio.Queue] = []
        self._event_history: Dict[str, List[Event]] = defaultdict(list)
        self._max_history = 100
        
        self._initialized = True
    
    def subscribe(self, session_id: str = None) -> asyncio.Queue:
        """Subscribe to events."""
        queue = asyncio.Queue()
        
        if session_id:
            self._subscribers[session_id].append(queue)
        else:
            self._global_subscribers.append(queue)
        
        return queue
    
    def unsubscribe(self, queue: asyncio.Queue, session_id: str = None):
        """Unsubscribe from events."""
        if session_id:
            if queue in self._subscribers[session_id]:
                self._subscribers[session_id].remove(queue)
        else:
            if queue in self._global_subscribers:
                self._global_subscribers.remove(queue)
    
    async def publish(self, event: Event):
        """Publish an event to all subscribers."""
        # Store in history
        self._event_history[event.session_id].append(event)
        if len(self._event_history[event.session_id]) > self._max_history:
            self._event_history[event.session_id].pop(0)
        
        # Send to session-specific subscribers
        for queue in self._subscribers.get(event.session_id, []):
            try:
                await queue.put(event)
            except:
                pass
        
        # Send to global subscribers
        for queue in self._global_subscribers:
            try:
                await queue.put(event)
            except:
                pass
    
    async def emit(
        self,
        event_type: EventType,
        session_id: str,
        **data
    ):
        """Create and publish an event."""
        event = Event(
            event_type=event_type,
            session_id=session_id,
            data=data
        )
        await self.publish(event)
    
    async def event_stream(
        self,
        session_id: str,
        heartbeat_interval: int = 15
    ) -> AsyncGenerator[str, None]:
        """Generate SSE event stream for a session."""
        queue = self.subscribe(session_id)
        last_heartbeat = datetime.utcnow()
        
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(),
                        timeout=1.0
                    )
                    
                    yield event.to_sse()
                    
                    if event.event_type == EventType.DONE:
                        break
                    
                except asyncio.TimeoutError:
                    now = datetime.utcnow()
                    elapsed = (now - last_heartbeat).total_seconds()
                    
                    if elapsed >= heartbeat_interval:
                        yield ": heartbeat\n\n"
                        last_heartbeat = now
                    
        except asyncio.CancelledError:
            pass
        finally:
            self.unsubscribe(queue, session_id)
    
    def clear_session(self, session_id: str):
        """Clear all data for a session."""
        for queue in self._subscribers.get(session_id, []):
            try:
                queue.put_nowait(None)
            except:
                pass
        
        if session_id in self._subscribers:
            del self._subscribers[session_id]
        
        if session_id in self._event_history:
            del self._event_history[session_id]


# Global event bus instance
event_bus = EventBus()


__all__ = ["EventBus", "Event", "EventType", "event_bus"]
