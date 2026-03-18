"""
Working memory for managing agent context.
Implements sliding window with importance scoring.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
from collections import OrderedDict

from backend.config import settings
from backend.utils import logger, count_tokens


@dataclass
class MemoryItem:
    """A single item in working memory."""
    id: str
    content: str
    role: str  # 'user', 'agent', 'tool', 'system'
    importance_score: float = 0.5
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def token_count(self) -> int:
        """Estimate token count for this item."""
        return count_tokens(self.content)


class WorkingMemory:
    """
    RAM-based working memory for the current session.
    Implements sliding window with importance-based eviction.
    """
    
    def __init__(
        self,
        max_tokens: int = None,
        importance_threshold: float = None
    ):
        self.max_tokens = max_tokens or settings.working_memory_max_tokens
        self.importance_threshold = importance_threshold or settings.importance_threshold
        
        # Memory storage (ordered by insertion)
        self._items: OrderedDict[str, MemoryItem] = OrderedDict()
        
        # Current token count
        self._current_tokens = 0
        
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
    
    async def add(
        self,
        content: str,
        role: str,
        importance_score: float = 0.5,
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Add a new item to working memory.
        
        Args:
            content: The content to store
            role: Role of the content creator
            importance_score: Importance score (0.0 - 1.0)
            metadata: Additional metadata
        
        Returns:
            ID of the added item
        """
        from backend.utils import generate_id
        
        item_id = generate_id()
        item = MemoryItem(
            id=item_id,
            content=content,
            role=role,
            importance_score=importance_score,
            metadata=metadata or {}
        )
        
        async with self._lock:
            # Add item
            self._items[item_id] = item
            self._current_tokens += item.token_count
            
            # Check if we need to evict
            await self._maybe_evict()
        
        return item_id
    
    async def get(self, item_id: str) -> Optional[MemoryItem]:
        """Get an item by ID."""
        return self._items.get(item_id)
    
    async def get_all(self) -> List[MemoryItem]:
        """Get all items in order."""
        return list(self._items.values())
    
    async def get_context_for_model(
        self,
        max_tokens: int = None,
        include_system: bool = True
    ) -> List[Dict[str, str]]:
        """
        Get context formatted for model input.
        
        Returns messages in format:
        [{"role": "user", "content": "..."}, ...]
        """
        max_tokens = max_tokens or self.max_tokens
        messages = []
        current_tokens = 0
        
        # Sort by importance (high to low) but maintain order for same importance
        items = list(self._items.values())
        
        # First pass: include high importance items
        for item in items:
            if item.importance_score >= 0.7:
                if current_tokens + item.token_count <= max_tokens:
                    messages.append({
                        "role": item.role,
                        "content": item.content
                    })
                    current_tokens += item.token_count
        
        # Second pass: include medium importance items
        for item in items:
            if 0.5 <= item.importance_score < 0.7:
                if current_tokens + item.token_count <= max_tokens:
                    messages.append({
                        "role": item.role,
                        "content": item.content
                    })
                    current_tokens += item.token_count
        
        # Third pass: include lower importance items if space allows
        for item in items:
            if item.importance_score < 0.5:
                if current_tokens + item.token_count <= max_tokens:
                    messages.append({
                        "role": item.role,
                        "content": item.content
                    })
                    current_tokens += item.token_count
        
        return messages
    
    async def update_importance(self, item_id: str, new_score: float):
        """Update importance score of an item."""
        if item_id in self._items:
            self._items[item_id].importance_score = new_score
    
    async def remove(self, item_id: str) -> bool:
        """Remove an item by ID."""
        async with self._lock:
            if item_id in self._items:
                item = self._items.pop(item_id)
                self._current_tokens -= item.token_count
                return True
            return False
    
    async def clear(self):
        """Clear all items."""
        async with self._lock:
            self._items.clear()
            self._current_tokens = 0
    
    async def _maybe_evict(self):
        """Evict items if over token limit."""
        while self._current_tokens > self.max_tokens and len(self._items) > 1:
            # Find lowest importance item
            lowest_id = None
            lowest_score = float('inf')
            
            for item_id, item in self._items.items():
                # Don't evict system messages
                if item.role == 'system':
                    continue
                if item.importance_score < lowest_score:
                    lowest_score = item.importance_score
                    lowest_id = item_id
            
            if lowest_id and lowest_score < self.importance_threshold:
                # Evict the item
                item = self._items.pop(lowest_id)
                self._current_tokens -= item.token_count
                logger.debug(f"Evicted memory item {lowest_id} (importance: {lowest_score})")
            else:
                # No more items can be evicted
                break
    
    @property
    def token_count(self) -> int:
        """Current token count."""
        return self._current_tokens
    
    @property
    def item_count(self) -> int:
        """Current item count."""
        return len(self._items)
    
    @property
    def utilization(self) -> float:
        """Memory utilization as percentage."""
        return (self._current_tokens / self.max_tokens) * 100
    
    def get_state(self) -> Dict[str, Any]:
        """Get current state for serialization."""
        return {
            "items": [
                {
                    "id": item.id,
                    "content": item.content,
                    "role": item.role,
                    "importance_score": item.importance_score,
                    "timestamp": item.timestamp.isoformat(),
                    "metadata": item.metadata
                }
                for item in self._items.values()
            ],
            "current_tokens": self._current_tokens,
            "max_tokens": self.max_tokens
        }
    
    def load_state(self, state: Dict[str, Any]):
        """Load state from serialization."""
        self._items.clear()
        self._current_tokens = 0
        
        for item_data in state.get("items", []):
            item = MemoryItem(
                id=item_data["id"],
                content=item_data["content"],
                role=item_data["role"],
                importance_score=item_data.get("importance_score", 0.5),
                timestamp=datetime.fromisoformat(item_data["timestamp"]),
                metadata=item_data.get("metadata", {})
            )
            self._items[item.id] = item
            self._current_tokens += item.token_count


class ContextScorer:
    """
    Scores the importance of context items.
    """
    
    @staticmethod
    def score_message(
        content: str,
        role: str,
        context: Dict[str, Any] = None
    ) -> float:
        """
        Calculate importance score for a message.
        
        Higher scores = more important to keep.
        """
        score = 0.5  # Base score
        
        # User messages are important
        if role == 'user':
            score += 0.2
        
        # System messages are very important
        if role == 'system':
            score += 0.3
        
        # Check for code blocks
        if '```' in content:
            score += 0.15
        
        # Check for errors
        error_indicators = ['error', 'exception', 'failed', 'traceback', 'bug']
        if any(indicator in content.lower() for indicator in error_indicators):
            score += 0.2
        
        # Check for decisions
        decision_indicators = ['decided', 'choosing', 'will use', 'implemented', 'created']
        if any(indicator in content.lower() for indicator in decision_indicators):
            score += 0.15
        
        # Check for questions
        if '?' in content:
            score += 0.1
        
        # Context bonus
        if context:
            # Referenced by later messages
            if context.get('is_referenced'):
                score += 0.2
            
            # Contains key information
            if context.get('contains_key_info'):
                score += 0.15
        
        return min(score, 1.0)


__all__ = ["WorkingMemory", "MemoryItem", "ContextScorer"]
