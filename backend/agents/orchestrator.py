"""
Chief Orchestrator Agent - Streaming Version
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import json
import re
import asyncio

from .base_agent import BaseAgent, AgentState, AgentMessage
from backend.models import model_manager
from backend.tools import ToolRegistry
from backend.memory.working_memory import WorkingMemory
from backend.core import event_bus, EventType
from backend.utils import AgentLogger, generate_id, extract_json_from_text


@dataclass
class Task:
    id: str
    title: str
    description: str
    agent_name: str
    status: str = "pending"
    priority: int = 0
    dependencies: List[str] = field(default_factory=list)
    result: Any = None
    error: str = None
    started_at: datetime = None
    completed_at: datetime = None


class ChiefOrchestrator(BaseAgent):
    """Optimized multi-agent controller with streaming."""

    name = "orchestrator"
    display_name = "Chief Orchestrator"
    description = "Autonomous multi-agent controller"
    preferred_model = "base"

    CODING_KEYWORDS = [
        'create', 'build', 'make', 'implement', 'develop', 'write code',
        'fix', 'debug', 'refactor', 'test', 'deploy', 'design',
        'api', 'database', 'component', 'function', 'class', 'module',
        'website', 'app', 'application', 'file', 'project', 'setup',
        'error', 'bug', 'issue', 'problem', 'not working', 'broken',
    ]

    def __init__(
        self,
        session_id: str,
        workspace_path: str,
        working_memory: WorkingMemory = None
    ):
        super().__init__(session_id, workspace_path, working_memory)
        self.tasks: Dict[str, Task] = {}
        self.agents: Dict[str, BaseAgent] = {}
        self.completed_tasks: List[str] = []
        self.failed_tasks: List[str] = []
        self.orchestrator_logger = AgentLogger("Orchestrator", session_id)

    def get_system_prompt(self) -> str:
        return "You are a coding orchestrator. Analyze tasks and route to appropriate agents."

    def get_task_analysis_prompt(self, task: str) -> str:
        return f"""[INST] Analyze this request and determine how to handle it.

Request: {task}

Respond with a simple plan. Available agents: coder, planner, reviewer, debugger

For coding tasks, respond like:
mode: task
tasks:
  - id: t1
    title: short title
    description: what to do
    agent: coder
execution_order: [t1]

For questions/chat, respond like:
mode: chat
response: your answer here

Keep it simple and direct. [/INST]"""

    def _classify_intent(self, task: str) -> str:
        """Fast heuristic classification."""
        task_lower = task.lower()
        word_count = len(task.split())
        
        if word_count < 5:
            if not any(kw in task_lower for kw in self.CODING_KEYWORDS):
                return "chat"
        
        if any(kw in task_lower for kw in self.CODING_KEYWORDS):
            return "task"
        
        question_words = ['what', 'how', 'why', 'when', 'who', 'which', 'can you', 'could you', 'tell me']
        if any(qw in task_lower for qw in question_words):
            return "chat"
        
        return "chat"

    async def execute(self, task: str, context: Dict[str, Any] = None) -> AgentMessage:
        self.state = AgentState.THINKING

        try:
            intent = self._classify_intent(task)

            if intent == "chat":
                return await self._handle_chat_stream(task)

            # For coding tasks, directly delegate to CoderAgent without analysis
            # This avoids the model generating plans instead of code
            await event_bus.emit(
                EventType.THINKING_START,
                self.session_id,
                agent="orchestrator",
                message=f"Delegating to coder agent..."
            )

            # Directly create a single task for the coder
            self.tasks.clear()
            self.completed_tasks.clear()
            self.failed_tasks.clear()

            task_obj = Task(
                id="t1",
                title="Execute coding task",
                description=task,
                agent_name="coder"
            )
            self.tasks["t1"] = task_obj

            # Execute directly
            results = await self._execute_tasks()
            summary = self._compile_results(results)

            return self.create_message(summary, metadata={"mode": "task"})

        except Exception as e:
            self.state = AgentState.ERROR
            return self.create_message(f"Error: {str(e)}")

    async def _analyze_request(self, task: str) -> Dict[str, Any]:
        """Analyze request and create execution plan."""
        prompt = self.get_task_analysis_prompt(task)

        full_response = ""
        
        async for chunk in model_manager.generate_stream(
            prompt,
            model_key="base",
            max_tokens=512,
            temperature=0.2,
            stop=["<|im_end|>", "<|eot_id|>"]
        ):
            full_response += chunk
            await event_bus.emit(
                EventType.THINKING_STREAM,
                self.session_id,
                agent="orchestrator",
                content=chunk
            )

        # Try to parse the response
        data = self._parse_analysis_response(full_response)

        if not data:
            # Default: just send to coder
            return {
                "mode": "task",
                "tasks": [{
                    "id": "t1",
                    "title": "Execute",
                    "description": task,
                    "agent": "coder"
                }],
                "execution_order": ["t1"]
            }

        return data
    
    def _parse_analysis_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse the analysis response - supports both JSON and simple YAML-like format."""
        response = response.strip()
        
        # Try JSON first
        data = extract_json_from_text(response)
        if data:
            return data
        
        # Try simple YAML-like format
        if "mode:" in response:
            result = {"mode": "task", "tasks": [], "execution_order": []}
            
            # Extract mode
            mode_match = re.search(r'mode:\s*(\w+)', response)
            if mode_match:
                result["mode"] = mode_match.group(1)
            
            # Extract tasks
            task_pattern = r'-\s*id:\s*(\w+)\s*title:\s*([^\n]+)\s*description:\s*([^\n]+)\s*agent:\s*(\w+)'
            tasks = re.findall(task_pattern, response, re.IGNORECASE)
            
            for t in tasks:
                result["tasks"].append({
                    "id": t[0],
                    "title": t[1].strip(),
                    "description": t[2].strip(),
                    "agent": t[3]
                })
                result["execution_order"].append(t[0])
            
            # If no tasks found but mode is task, create default
            if result["mode"] == "task" and not result["tasks"]:
                return None
            
            return result
        
        return None

    def _create_tasks(self, plan: Dict[str, Any]):
        self.tasks.clear()
        self.completed_tasks.clear()
        self.failed_tasks.clear()

        for t in plan.get("tasks", []):
            task_obj = Task(
                id=t.get("id", generate_id()),
                title=t.get("title", ""),
                description=t.get("description", ""),
                agent_name=t.get("agent", "coder"),
                dependencies=t.get("dependencies", []),
                priority=t.get("priority", 0),
            )
            self.tasks[task_obj.id] = task_obj

    async def _execute_tasks(self) -> Dict[str, Any]:
        results = {}
        order = self._get_execution_order()

        for task_id in order:
            task = self.tasks[task_id]

            deps_met = all(dep in self.completed_tasks for dep in task.dependencies)
            if not deps_met:
                task.status = "failed"
                self.failed_tasks.append(task_id)
                continue

            try:
                agent = self.agents.get(task.agent_name)
                if not agent:
                    raise ValueError(f"Agent not found: {task.agent_name}")

                task.started_at = datetime.utcnow()

                await event_bus.emit(
                    EventType.AGENT_SWITCH,
                    self.session_id,
                    from_agent="orchestrator",
                    to_agent=task.agent_name
                )

                result = await agent.execute(
                    task.description,
                    context={
                        "task_id": task.id,
                        "workspace": str(self.workspace_path)
                    }
                )

                task.result = result.content
                task.status = "completed"
                self.completed_tasks.append(task_id)

            except Exception as e:
                task.error = str(e)
                task.status = "failed"
                self.failed_tasks.append(task_id)

            task.completed_at = datetime.utcnow()
            results[task_id] = {
                "status": task.status,
                "result": task.result,
                "error": task.error
            }

        return results

    def _get_execution_order(self) -> List[str]:
        in_degree = {tid: 0 for tid in self.tasks}

        for t in self.tasks.values():
            for d in t.dependencies:
                if d in in_degree:
                    in_degree[t.id] += 1

        queue = [tid for tid, deg in in_degree.items() if deg == 0]
        order = []

        while queue:
            queue.sort(key=lambda x: self.tasks[x].priority, reverse=True)
            current = queue.pop(0)
            order.append(current)

            for t in self.tasks.values():
                if current in t.dependencies:
                    in_degree[t.id] -= 1
                    if in_degree[t.id] == 0:
                        queue.append(t.id)

        return order

    async def _handle_chat_stream(self, message: str) -> AgentMessage:
        """Handle general chat with streaming output."""
        await event_bus.emit(
            EventType.THINKING_START,
            self.session_id,
            agent="orchestrator",
            message="Thinking..."
        )
        
        prompt = f"<|im_start|>user\n{message}<|im_end|>\n<|im_start|>assistant\n"
        
        full_response = ""
        
        async for chunk in model_manager.generate_stream(
            prompt,
            model_key="base",
            max_tokens=256,
            temperature=0.7,
            stop=["<|im_end|>", "<|eot_id|>"]
        ):
            full_response += chunk
            await event_bus.emit(
                EventType.THINKING_STREAM,
                self.session_id,
                agent="orchestrator",
                content=chunk
            )
        
        await event_bus.emit(
            EventType.THINKING_END,
            self.session_id,
            agent="orchestrator",
            content=full_response.strip()
        )
        
        return self.create_message(full_response.strip())

    def _compile_results(self, results: Dict[str, Any]) -> str:
        completed = len(self.completed_tasks)
        failed = len(self.failed_tasks)
        
        summary = f"**Completed:** {completed} tasks\n"
        
        if failed > 0:
            summary += f"**Failed:** {failed} tasks\n"
        
        if self.completed_tasks:
            last_task = self.tasks.get(self.completed_tasks[-1])
            if last_task and last_task.result:
                summary += f"\n**Result:**\n{str(last_task.result)[:500]}"
        
        return summary

    def register_agent(self, agent: BaseAgent):
        self.agents[agent.name] = agent


__all__ = ["ChiefOrchestrator", "Task"]
