"""
Execution Monitor for detecting stuck agents and infinite loops.
Implements pattern detection, repetition tracking, and automatic intervention.
"""

import time
from typing import Dict, Any, List, Optional, Deque
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime
from enum import Enum
import hashlib
import json

from backend.utils import logger, AgentLogger
from backend.config import settings


class ExecutionState(str, Enum):
    """State of execution monitoring."""
    HEALTHY = "healthy"
    WARNING = "warning"
    STUCK = "stuck"
    INTERVENTION_REQUIRED = "intervention_required"


@dataclass
class ActionRecord:
    """Record of an agent action."""
    timestamp: float
    action_type: str  # "thinking", "tool_call", "decision"
    action_hash: str  # Hash of action content for comparison
    content_preview: str  # First 100 chars
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LoopPattern:
    """Detected loop pattern."""
    pattern_hash: str
    occurrences: int
    first_occurrence: float
    last_occurrence: float
    action_sequence: List[str]


class ExecutionMonitor:
    """
    Monitors agent execution for stuck states and infinite loops.
    
    Detection methods:
    1. Repetition detection - Same action repeated N times
    2. Pattern detection - Same sequence of actions in loop
    3. Progress detection - No forward progress after M steps
    4. Timeout detection - Task running too long
    """
    
    def __init__(
        self,
        max_repetitions: int = 3,
        pattern_window: int = 10,
        max_pattern_repetitions: int = 2,
        progress_check_interval: int = 20,
        timeout_seconds: int = 3600
    ):
        """
        Initialize the execution monitor.
        
        Args:
            max_repetitions: Maximum times same action can repeat
            pattern_window: Window size for pattern detection
            max_pattern_repetitions: Maximum times same pattern can repeat
            progress_check_interval: Steps between progress checks
            timeout_seconds: Maximum task duration
        """
        self.max_repetitions = max_repetitions
        self.pattern_window = pattern_window
        self.max_pattern_repetitions = max_pattern_repetitions
        self.progress_check_interval = progress_check_interval
        self.timeout_seconds = timeout_seconds
        
        # Per-session tracking
        self._session_monitors: Dict[str, Dict[str, Any]] = {}
        
        self._logger = AgentLogger("ExecutionMonitor")
    
    def start_session(self, session_id: str, task: str):
        """
        Start monitoring a new session.
        
        Args:
            session_id: Session to monitor
            task: Task description for progress tracking
        """
        self._session_monitors[session_id] = {
            "start_time": time.time(),
            "task": task,
            "actions": deque(maxlen=1000),  # Keep last 1000 actions
            "tool_calls": deque(maxlen=500),
            "decisions": deque(maxlen=200),
            "state": ExecutionState.HEALTHY,
            "warnings": [],
            "intervention_count": 0,
            "progress_markers": [],
            "last_progress_time": time.time(),
            "action_counts": {},  # Count of each action hash
            "pattern_history": deque(maxlen=100),
        }
        
        self._logger.info(f"Started monitoring session: {session_id}")
    
    def record_action(
        self,
        session_id: str,
        action_type: str,
        content: str,
        metadata: Dict[str, Any] = None
    ):
        """
        Record an agent action for monitoring.
        
        Args:
            session_id: Session being monitored
            action_type: Type of action (thinking, tool_call, decision)
            content: Action content
            metadata: Additional metadata
        """
        if session_id not in self._session_monitors:
            self.start_session(session_id, "Unknown task")
        
        monitor = self._session_monitors[session_id]
        
        # Create action record
        action_hash = hashlib.md5(content.encode()).hexdigest()[:16]
        
        record = ActionRecord(
            timestamp=time.time(),
            action_type=action_type,
            action_hash=action_hash,
            content_preview=content[:100],
            metadata=metadata or {}
        )
        
        monitor["actions"].append(record)
        
        # Track action counts
        if action_hash not in monitor["action_counts"]:
            monitor["action_counts"][action_hash] = 0
        monitor["action_counts"][action_hash] += 1
        
        # Track by type
        if action_type == "tool_call":
            monitor["tool_calls"].append(record)
        elif action_type == "decision":
            monitor["decisions"].append(record)
        
        # Check for issues
        self._check_repetition(session_id, action_hash)
        self._check_pattern(session_id)
        self._check_timeout(session_id)
        
        # Update state
        self._update_state(session_id)
    
    def _check_repetition(self, session_id: str, action_hash: str):
        """Check for excessive repetition of same action."""
        monitor = self._session_monitors[session_id]
        count = monitor["action_counts"].get(action_hash, 0)
        
        if count >= self.max_repetitions:
            warning = f"Action repeated {count} times (hash: {action_hash})"
            self._add_warning(session_id, warning, "repetition")
    
    def _check_pattern(self, session_id: str):
        """Check for repeating action patterns."""
        monitor = self._session_monitors[session_id]
        actions = list(monitor["actions"])
        
        if len(actions) < self.pattern_window * 2:
            return
        
        # Extract recent action hashes
        recent = [a.action_hash for a in actions[-self.pattern_window:]]
        previous = [a.action_hash for a in actions[-self.pattern_window*2:-self.pattern_window]]
        
        # Check if patterns match
        if recent == previous:
            pattern_hash = hashlib.md5("".join(recent).encode()).hexdigest()[:12]
            
            # Track pattern
            monitor["pattern_history"].append(pattern_hash)
            
            # Count pattern occurrences
            pattern_count = sum(1 for p in monitor["pattern_history"] if p == pattern_hash)
            
            if pattern_count >= self.max_pattern_repetitions:
                warning = f"Loop pattern detected (repeated {pattern_count} times)"
                self._add_warning(session_id, warning, "loop_pattern")
    
    def _check_timeout(self, session_id: str):
        """Check for task timeout."""
        monitor = self._session_monitors[session_id]
        elapsed = time.time() - monitor["start_time"]
        
        if elapsed > self.timeout_seconds:
            warning = f"Task timeout after {elapsed:.0f} seconds"
            self._add_warning(session_id, warning, "timeout")
    
    def _check_progress(self, session_id: str):
        """Check if task is making progress."""
        monitor = self._session_monitors[session_id]
        actions = list(monitor["actions"])
        
        if len(actions) < self.progress_check_interval:
            return
        
        # Look for progress indicators in recent actions
        recent_actions = actions[-self.progress_check_interval:]
        
        # Progress indicators: file writes, successful tool completions
        progress_indicators = [
            a for a in recent_actions
            if a.metadata.get("progress") or
               a.action_type == "tool_call" and 
               a.metadata.get("status") == "success"
        ]
        
        if not progress_indicators:
            elapsed = time.time() - monitor["last_progress_time"]
            if elapsed > 60:  # No progress for 60 seconds
                warning = f"No progress detected for {elapsed:.0f} seconds"
                self._add_warning(session_id, warning, "no_progress")
    
    def _add_warning(self, session_id: str, message: str, warning_type: str):
        """Add a warning to the session monitor."""
        monitor = self._session_monitors[session_id]
        
        # Avoid duplicate warnings
        recent_warnings = [w for w in monitor["warnings"][-10:] if w["type"] == warning_type]
        if recent_warnings:
            return
        
        warning = {
            "timestamp": time.time(),
            "message": message,
            "type": warning_type
        }
        
        monitor["warnings"].append(warning)
        self._logger.warning(f"[{session_id}] {message}")
    
    def _update_state(self, session_id: str):
        """Update the execution state based on warnings."""
        monitor = self._session_monitors[session_id]
        recent_warnings = monitor["warnings"][-5:]
        
        if len(recent_warnings) >= 3:
            monitor["state"] = ExecutionState.STUCK
        elif len(recent_warnings) >= 1:
            monitor["state"] = ExecutionState.WARNING
        else:
            monitor["state"] = ExecutionState.HEALTHY
    
    def mark_progress(self, session_id: str, description: str = ""):
        """
        Mark that progress has been made.
        
        Call this when the agent achieves a milestone.
        """
        if session_id not in self._session_monitors:
            return
        
        monitor = self._session_monitors[session_id]
        monitor["progress_markers"].append({
            "timestamp": time.time(),
            "description": description
        })
        monitor["last_progress_time"] = time.time()
        
        # Clear warnings if progress made
        monitor["warnings"] = [w for w in monitor["warnings"] if w["type"] == "timeout"]
        monitor["state"] = ExecutionState.HEALTHY
    
    def get_state(self, session_id: str) -> ExecutionState:
        """Get current execution state."""
        if session_id not in self._session_monitors:
            return ExecutionState.HEALTHY
        
        return self._session_monitors[session_id]["state"]
    
    def is_stuck(self, session_id: str) -> bool:
        """Check if session is stuck."""
        return self.get_state(session_id) == ExecutionState.STUCK
    
    def needs_intervention(self, session_id: str) -> bool:
        """Check if intervention is needed."""
        monitor = self._session_monitors.get(session_id)
        if not monitor:
            return False
        
        return (
            monitor["state"] == ExecutionState.STUCK or
            len(monitor["warnings"]) >= 5
        )
    
    def get_intervention_suggestion(self, session_id: str) -> Optional[str]:
        """
        Get a suggestion for intervention.
        
        Returns:
            Suggestion text or None
        """
        if not self.needs_intervention(session_id):
            return None
        
        monitor = self._session_monitors[session_id]
        warnings = monitor["warnings"][-5:]
        
        # Analyze warnings for suggestion
        warning_types = [w["type"] for w in warnings]
        
        if "loop_pattern" in warning_types:
            return (
                "Loop detected. Suggestion: Try a different approach or break down the task "
                "into smaller steps. Consider asking the user for clarification."
            )
        
        if "repetition" in warning_types:
            return (
                "Repetitive actions detected. Suggestion: The current approach may not be "
                "working. Try alternative tools or strategies."
            )
        
        if "no_progress" in warning_types:
            return (
                "No progress detected. Suggestion: Review the task requirements and "
                "consider if the goal is achievable with available tools."
            )
        
        if "timeout" in warning_types:
            return (
                "Task timeout. Suggestion: The task is taking too long. Consider "
                "simplifying or breaking into subtasks."
            )
        
        return "Multiple issues detected. Consider restarting with a different approach."
    
    def end_session(self, session_id: str) -> Dict[str, Any]:
        """
        End monitoring and get summary.
        
        Returns:
            Summary of the session execution
        """
        if session_id not in self._session_monitors:
            return {}
        
        monitor = self._session_monitors[session_id]
        
        summary = {
            "session_id": session_id,
            "duration_seconds": time.time() - monitor["start_time"],
            "total_actions": len(monitor["actions"]),
            "total_tool_calls": len(monitor["tool_calls"]),
            "final_state": monitor["state"].value,
            "warning_count": len(monitor["warnings"]),
            "progress_markers": len(monitor["progress_markers"]),
            "intervention_count": monitor["intervention_count"],
        }
        
        del self._session_monitors[session_id]
        
        self._logger.info(f"Ended monitoring session: {session_id}")
        
        return summary
    
    def force_intervention(self, session_id: str) -> str:
        """
        Force an intervention, returning what action to take.
        
        Returns:
            Intervention action to take
        """
        if session_id not in self._session_monitors:
            return "continue"
        
        monitor = self._session_monitors[session_id]
        monitor["intervention_count"] += 1
        monitor["state"] = ExecutionState.INTERVENTION_REQUIRED
        
        # Decide intervention type
        interventions = monitor["intervention_count"]
        
        if interventions == 1:
            return "retry_with_different_approach"
        elif interventions == 2:
            return "ask_user_for_help"
        else:
            return "abort_task"


# Global monitor instance
execution_monitor = ExecutionMonitor()


__all__ = [
    "ExecutionMonitor",
    "ExecutionState",
    "ActionRecord",
    "LoopPattern",
    "execution_monitor"
]
