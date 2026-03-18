"""
Base agent class for the Autonomous Coding Agent.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import asyncio

from backend.models import model_manager, InferenceResult
from backend.tools import ToolRegistry, ToolResult
from backend.memory.working_memory import WorkingMemory
from backend.utils import logger, AgentLogger, generate_id
from backend.config import settings


class AgentState(str, Enum):
    """State of an agent."""
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING_TOOL = "executing_tool"
    WAITING = "waiting"
    ERROR = "error"
    COMPLETED = "completed"


@dataclass
class AgentMessage:
    """Message from an agent."""
    id: str
    agent_name: str
    content: str
    role: str = "agent"
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentDecision:
    """A decision made by an agent."""
    decision_type: str
    description: str
    reasoning: str
    confidence: float = 0.8
    alternatives: List[str] = field(default_factory=list)


class BaseAgent(ABC):
    """
    Abstract base class for all specialist agents.
    
    Each agent specializes in a particular type of task
    (coding, testing, debugging, etc.)
    """
    
    # Agent metadata (override in subclasses)
    name: str = "base_agent"
    display_name: str = "Base Agent"
    description: str = "Base agent class"
    
    # Model preference (override in subclasses)
    preferred_model: str = "base"  # 'base' or 'specialist'
    
    def __init__(
        self,
        session_id: str,
        workspace_path: str,
        working_memory: WorkingMemory = None
    ):
        """
        Initialize the agent.
        
        Args:
            session_id: Current session ID
            workspace_path: Path to workspace
            working_memory: Shared working memory instance
        """
        self.session_id = session_id
        self.workspace_path = workspace_path
        self.working_memory = working_memory or WorkingMemory()
        
        self.state = AgentState.IDLE
        self.current_task: Optional[str] = None
        self.tools_used: List[str] = []
        
        self.logger = AgentLogger(self.name, session_id)
    
    @abstractmethod
    async def execute(self, task: str, context: Dict[str, Any] = None) -> AgentMessage:
        """
        Execute a task.
        
        Args:
            task: Task description
            context: Additional context for the task
        
        Returns:
            AgentMessage with results
        """
        pass
    
    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Get the system prompt for this agent.
        
        Returns:
            System prompt string
        """
        pass
    
    async def think(
        self,
        prompt: str,
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """
        Generate thinking output (streamed).
        
        Args:
            prompt: Input prompt
            stream: Whether to stream output
        
        Yields:
            Generated text chunks
        """
        self.state = AgentState.THINKING
        
        full_response = ""
        
        try:
            if stream:
                async for chunk in model_manager.generate_stream(
                    prompt,
                    model_key=self.preferred_model
                ):
                    full_response += chunk
                    yield chunk
            else:
                result = await model_manager.generate(
                    prompt,
                    model_key=self.preferred_model
                )
                full_response = result.text
                yield result.text
            
            # Store in working memory
            await self.working_memory.add(
                content=full_response,
                role="agent",
                importance_score=0.6,
                metadata={"agent": self.name, "type": "thinking"}
            )
            
        except Exception as e:
            self.logger.error(e)
            self.state = AgentState.ERROR
            raise
        finally:
            if self.state == AgentState.THINKING:
                self.state = AgentState.IDLE
    
    async def use_tool(
        self,
        tool_name: str,
        **kwargs
    ) -> ToolResult:
        """
        Execute a tool.
        
        Args:
            tool_name: Name of the tool to use
            **kwargs: Tool parameters
        
        Returns:
            ToolResult
        """
        self.state = AgentState.EXECUTING_TOOL
        self.tools_used.append(tool_name)
        
        self.logger.tool_use(tool_name, kwargs)
        
        try:
            # Get tool instance
            tool = ToolRegistry.get_tool(
                tool_name,
                session_id=self.session_id,
                workspace_path=self.workspace_path
            )
            
            if not tool:
                return ToolResult(
                    tool_name=tool_name,
                    status="failed",
                    error=f"Tool not found: {tool_name}"
                )
            
            # Execute tool
            result = await tool.run(**kwargs)
            
            # Handle both enum and string status
            status_val = result.status.value if hasattr(result.status, 'value') else result.status
            success = status_val == "success"
            
            self.logger.tool_result(
                tool_name,
                success=success,
                result=str(result.result)[:500] if result.result else None
            )
            
            # Store result in memory
            await self.working_memory.add(
                content=f"Tool {tool_name}: {str(result.result)[:1000]}",
                role="tool",
                importance_score=0.5,
                metadata={
                    "tool": tool_name,
                    "success": success
                }
            )
            
            return result
            
        except Exception as e:
            self.logger.error(e)
            return ToolResult(
                tool_name=tool_name,
                status="failed",
                error=str(e)
            )
        finally:
            self.state = AgentState.IDLE
    
    async def generate_response(
        self,
        user_message: str,
        context: Dict[str, Any] = None
    ) -> str:
        """
        Generate a response to a user message.
        
        Builds the full prompt including system prompt and context.
        """
        # Get system prompt
        system_prompt = self.get_system_prompt()
        
        # Get context from working memory
        context_messages = await self.working_memory.get_context_for_model()
        
        # Build full prompt
        prompt_parts = [system_prompt, "\n"]
        
        # Add conversation context
        for msg in context_messages:
            role = msg["role"]
            content = msg["content"]
            if role == "user":
                prompt_parts.append(f"User: {content}\n")
            elif role == "agent":
                prompt_parts.append(f"Assistant: {content}\n")
            elif role == "tool":
                prompt_parts.append(f"Tool: {content}\n")
        
        # Add additional context
        if context:
            prompt_parts.append(f"\nContext:\n")
            for key, value in context.items():
                prompt_parts.append(f"- {key}: {value}\n")
        
        # Add current message
        prompt_parts.append(f"\nUser: {user_message}\n")
        prompt_parts.append("\nAssistant:")
        
        full_prompt = "".join(prompt_parts)
        
        # Generate response
        result = await model_manager.generate(
            full_prompt,
            model_key=self.preferred_model,
            stream=False
        )
        
        return result.text
    
    def format_tool_result(self, result: ToolResult) -> str:
        """Format a tool result for inclusion in context."""
        status_val = result.status.value if hasattr(result.status, 'value') else result.status
        if status_val == "success":
            return f"Tool '{result.tool_name}' succeeded: {result.result}"
        else:
            return f"Tool '{result.tool_name}' failed: {result.error}"
    
    def create_message(
        self,
        content: str,
        metadata: Dict[str, Any] = None
    ) -> AgentMessage:
        """Create an agent message."""
        return AgentMessage(
            id=generate_id(),
            agent_name=self.name,
            content=content,
            metadata=metadata or {}
        )


__all__ = [
    "BaseAgent",
    "AgentState",
    "AgentMessage",
    "AgentDecision"
]