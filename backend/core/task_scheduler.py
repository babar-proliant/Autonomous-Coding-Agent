"""
Task Parallelization System for executing independent tasks concurrently.
Implements DAG-based execution with dependency resolution.
"""

import asyncio
from typing import Dict, Any, List, Optional, Set, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import heapq
from collections import defaultdict

from backend.utils import logger, AgentLogger, generate_id
from backend.core.event_bus import event_bus, EventType
from backend.config import settings


class TaskStatus(str, Enum):
    """Status of a task."""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class TaskPriority(int, Enum):
    """Priority levels for tasks."""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


@dataclass
class TaskNode:
    """A node in the task dependency graph."""
    id: str
    name: str
    description: str
    agent_name: str
    priority: int = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    dependencies: Set[str] = field(default_factory=set)
    dependents: Set[str] = field(default_factory=set)  # Tasks that depend on this
    result: Any = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 2
    
    def __lt__(self, other):
        """Comparison for priority queue."""
        return self.priority < other.priority


@dataclass
class ExecutionPlan:
    """Plan for parallel task execution."""
    total_tasks: int
    parallel_groups: List[List[str]]  # Groups of tasks that can run in parallel
    estimated_time: float
    critical_path: List[str]


class TaskScheduler:
    """
    Schedules and executes tasks with dependency resolution.
    
    Features:
    - DAG-based dependency management
    - Parallel execution of independent tasks
    - Priority-based scheduling
    - Retry logic for failed tasks
    - Progress tracking
    """
    
    def __init__(
        self,
        session_id: str,
        max_parallel: int = None,
        default_max_retries: int = 2
    ):
        """
        Initialize the task scheduler.
        
        Args:
            session_id: Session ID for events
            max_parallel: Maximum parallel tasks (default from settings)
            default_max_retries: Default retry count for tasks
        """
        self.session_id = session_id
        self.max_parallel = max_parallel or settings.max_parallel_agents
        self.default_max_retries = default_max_retries
        
        self._tasks: Dict[str, TaskNode] = {}
        self._pending_queue: List[TaskNode] = []  # Priority queue
        self._running_tasks: Set[str] = set()
        self._completed_tasks: Set[str] = set()
        self._failed_tasks: Set[str] = set()
        
        self._execution_lock = asyncio.Lock()
        self._task_handlers: Dict[str, Callable] = {}
        
        self._logger = AgentLogger("TaskScheduler", session_id)
    
    def register_handler(self, task_type: str, handler: Callable):
        """Register a handler for a task type."""
        self._task_handlers[task_type] = handler
    
    def add_task(
        self,
        name: str,
        description: str,
        agent_name: str,
        dependencies: List[str] = None,
        priority: int = TaskPriority.NORMAL,
        max_retries: int = None
    ) -> str:
        """
        Add a task to the scheduler.
        
        Args:
            name: Task name
            description: Task description
            agent_name: Agent to handle this task
            dependencies: List of task IDs this task depends on
            priority: Task priority
            max_retries: Maximum retry attempts
            
        Returns:
            Task ID
        """
        task_id = generate_id()
        
        task = TaskNode(
            id=task_id,
            name=name,
            description=description,
            agent_name=agent_name,
            priority=priority,
            dependencies=set(dependencies or []),
            max_retries=max_retries or self.default_max_retries
        )
        
        self._tasks[task_id] = task
        
        # Update dependents
        for dep_id in task.dependencies:
            if dep_id in self._tasks:
                self._tasks[dep_id].dependents.add(task_id)
        
        self._logger.debug(f"Added task: {name} ({task_id})")
        
        return task_id
    
    def create_execution_plan(self) -> ExecutionPlan:
        """
        Create an execution plan showing parallel groups.
        
        Returns:
            ExecutionPlan with parallel groups
        """
        # Topological sort with level assignment
        in_degree = {task_id: len(task.dependencies) for task_id, task in self._tasks.items()}
        levels: Dict[str, int] = {}
        parallel_groups: List[List[str]] = []
        
        # Find tasks with no dependencies (level 0)
        current_level = [
            task_id for task_id, degree in in_degree.items()
            if degree == 0
        ]
        
        level = 0
        while current_level:
            parallel_groups.append(sorted(current_level))
            
            for task_id in current_level:
                levels[task_id] = level
            
            # Find next level
            next_level = []
            for task_id in current_level:
                task = self._tasks[task_id]
                for dependent_id in task.dependents:
                    in_degree[dependent_id] -= 1
                    if in_degree[dependent_id] == 0:
                        next_level.append(dependent_id)
            
            current_level = next_level
            level += 1
        
        # Find critical path (longest path through DAG)
        critical_path = self._find_critical_path()
        
        # Estimate execution time (rough estimate)
        estimated_time = len(parallel_groups) * 2.0  # 2 minutes per level average
        
        return ExecutionPlan(
            total_tasks=len(self._tasks),
            parallel_groups=parallel_groups,
            estimated_time=estimated_time,
            critical_path=critical_path
        )
    
    def _find_critical_path(self) -> List[str]:
        """Find the critical path through the DAG."""
        # Dynamic programming approach
        longest_path_to: Dict[str, List[str]] = {}
        
        def get_longest_path(task_id: str) -> List[str]:
            if task_id in longest_path_to:
                return longest_path_to[task_id]
            
            task = self._tasks[task_id]
            
            if not task.dependencies:
                longest_path_to[task_id] = [task_id]
                return [task_id]
            
            longest_prev: List[str] = []
            for dep_id in task.dependencies:
                path = get_longest_path(dep_id)
                if len(path) > len(longest_prev):
                    longest_prev = path
            
            result = longest_prev + [task_id]
            longest_path_to[task_id] = result
            return result
        
        # Find longest path from any starting task
        critical_path: List[str] = []
        for task_id, task in self._tasks.items():
            path = get_longest_path(task_id)
            if len(path) > len(critical_path):
                critical_path = path
        
        return critical_path
    
    async def execute_all(
        self,
        task_executor: Callable[[str, Dict[str, Any]], Awaitable[Any]]
    ) -> Dict[str, Any]:
        """
        Execute all tasks respecting dependencies.
        
        Args:
            task_executor: Async function to execute a task
            
        Returns:
            Summary of execution
        """
        self._logger.info(f"Starting execution of {len(self._tasks)} tasks")
        
        # Emit planning event
        plan = self.create_execution_plan()
        
        await event_bus.emit(
            EventType.TASK_CREATED,
            self.session_id,
            total_tasks=len(self._tasks),
            parallel_groups=len(plan.parallel_groups)
        )
        
        # Execute tasks in waves
        execution_results = {}
        
        for wave_index, wave_tasks in enumerate(plan.parallel_groups):
            self._logger.info(f"Executing wave {wave_index + 1}: {len(wave_tasks)} tasks")
            
            # Run tasks in wave in parallel
            tasks_to_run = []
            for task_id in wave_tasks:
                task = self._tasks[task_id]
                
                # Check if dependencies completed
                if not all(dep_id in self._completed_tasks for dep_id in task.dependencies):
                    task.status = TaskStatus.SKIPPED
                    self._failed_tasks.add(task_id)
                    continue
                
                tasks_to_run.append(self._execute_task(task_id, task_executor))
            
            # Wait for wave to complete
            if tasks_to_run:
                results = await asyncio.gather(*tasks_to_run, return_exceptions=True)
                
                for task_id, result in zip([t.get_name() for t in tasks_to_run], results):
                    if isinstance(result, Exception):
                        self._logger.error(f"Task {task_id} failed: {result}")
                    execution_results[task_id] = result
        
        # Compile summary
        summary = {
            "total_tasks": len(self._tasks),
            "completed": len(self._completed_tasks),
            "failed": len(self._failed_tasks),
            "skipped": len([t for t in self._tasks.values() if t.status == TaskStatus.SKIPPED]),
            "results": {
                task_id: {
                    "status": task.status.value,
                    "result": task.result,
                    "error": task.error
                }
                for task_id, task in self._tasks.items()
            }
        }
        
        await event_bus.emit(
            EventType.TASK_COMPLETED,
            self.session_id,
            summary=summary
        )
        
        return summary
    
    async def _execute_task(
        self,
        task_id: str,
        executor: Callable
    ) -> Any:
        """Execute a single task with retry logic."""
        task = self._tasks[task_id]
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.utcnow()
        self._running_tasks.add(task_id)
        
        await event_bus.emit(
            EventType.TASK_STARTED,
            self.session_id,
            task_id=task_id,
            name=task.name
        )
        
        while task.retry_count <= task.max_retries:
            try:
                result = await asyncio.wait_for(
                    executor(task_id, {
                        "name": task.name,
                        "description": task.description,
                        "agent_name": task.agent_name
                    }),
                    timeout=settings.max_tool_execution_time
                )
                
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.completed_at = datetime.utcnow()
                
                self._running_tasks.discard(task_id)
                self._completed_tasks.add(task_id)
                
                self._logger.info(f"Task completed: {task.name}")
                
                return result
                
            except asyncio.TimeoutError:
                task.retry_count += 1
                self._logger.warning(
                    f"Task {task.name} timed out, retry {task.retry_count}/{task.max_retries}"
                )
                
            except Exception as e:
                task.retry_count += 1
                self._logger.warning(
                    f"Task {task.name} failed: {e}, retry {task.retry_count}/{task.max_retries}"
                )
                
                if task.retry_count > task.max_retries:
                    task.status = TaskStatus.FAILED
                    task.error = str(e)
                    task.completed_at = datetime.utcnow()
                    
                    self._running_tasks.discard(task_id)
                    self._failed_tasks.add(task_id)
                    
                    await event_bus.emit(
                        EventType.TASK_FAILED,
                        self.session_id,
                        task_id=task_id,
                        error=str(e)
                    )
                    
                    raise
        
        return None
    
    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """Get status of a task."""
        task = self._tasks.get(task_id)
        return task.status if task else None
    
    def get_progress(self) -> Dict[str, int]:
        """Get execution progress."""
        return {
            "total": len(self._tasks),
            "pending": len([t for t in self._tasks.values() if t.status == TaskStatus.PENDING]),
            "running": len(self._running_tasks),
            "completed": len(self._completed_tasks),
            "failed": len(self._failed_tasks)
        }
    
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending or running task."""
        task = self._tasks.get(task_id)
        if not task:
            return False
        
        if task.status in (TaskStatus.PENDING, TaskStatus.QUEUED):
            task.status = TaskStatus.CANCELLED
            return True
        
        if task.status == TaskStatus.RUNNING:
            task.status = TaskStatus.CANCELLED
            self._running_tasks.discard(task_id)
            return True
        
        return False
    
    def clear(self):
        """Clear all tasks."""
        self._tasks.clear()
        self._pending_queue.clear()
        self._running_tasks.clear()
        self._completed_tasks.clear()
        self._failed_tasks.clear()


__all__ = [
    "TaskScheduler",
    "TaskNode",
    "TaskStatus",
    "TaskPriority",
    "ExecutionPlan"
]
