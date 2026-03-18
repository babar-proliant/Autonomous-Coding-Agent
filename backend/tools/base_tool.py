"""
Base tool class and interfaces for the Autonomous Coding Agent.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import time

from backend.utils import logger, generate_id


class ToolRisk(str, Enum):
    """Risk levels for tools."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ToolStatus(str, Enum):
    """Status of tool execution."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"


@dataclass
class ToolResult:
    """Result of a tool execution."""
    tool_name: str
    status: ToolStatus
    result: Any = None
    error: Optional[str] = None
    execution_time_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "tool_name": self.tool_name,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "metadata": self.metadata
        }


@dataclass
class ToolParameter:
    """Definition of a tool parameter."""
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
    choices: List[Any] = None


class BaseTool(ABC):
    """
    Abstract base class for all tools.
    
    Tools are the primary way the agent interacts with the world.
    Each tool performs a specific action and returns results.
    """
    
    # Tool metadata (override in subclasses)
    name: str = "base_tool"
    description: str = "Base tool class"
    category: str = "general"
    risk: ToolRisk = ToolRisk.LOW
    requires_confirmation: bool = False
    timeout_seconds: int = 60
    
    # Parameters definition (override in subclasses)
    parameters: List[ToolParameter] = []
    
    def __init__(self, session_id: str = None, workspace_path: str = None):
        """
        Initialize the tool.
        
        Args:
            session_id: Current session ID
            workspace_path: Path to the workspace
        """
        self.session_id = session_id
        self.workspace_path = workspace_path
        self._start_time: Optional[float] = None
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """
        Execute the tool.
        
        Args:
            **kwargs: Tool parameters
        
        Returns:
            ToolResult with execution outcome
        """
        pass
    
    async def run(self, **kwargs) -> ToolResult:
        """
        Run the tool with validation and timing.
        
        This is the main entry point for tool execution.
        """
        self._start_time = time.time()
        
        # Validate parameters
        validation_error = self._validate_parameters(kwargs)
        if validation_error:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=validation_error
            )
        
        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                self.execute(**kwargs),
                timeout=self.timeout_seconds
            )
            return result
            
        except asyncio.TimeoutError:
            execution_time = int((time.time() - self._start_time) * 1000)
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.TIMEOUT,
                error=f"Tool execution timed out after {self.timeout_seconds} seconds",
                execution_time_ms=execution_time
            )
            
        except Exception as e:
            execution_time = int((time.time() - self._start_time) * 1000)
            logger.exception(f"Tool {self.name} failed with error: {e}")
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(e),
                execution_time_ms=execution_time
            )
    
    def _validate_parameters(self, kwargs: Dict[str, Any]) -> Optional[str]:
        """
        Validate tool parameters.
        
        Returns:
            Error message if validation fails, None otherwise
        """
        provided_params = set(kwargs.keys())
        
        for param in self.parameters:
            # Check required parameters
            if param.required and param.name not in kwargs:
                return f"Missing required parameter: {param.name}"
            
            # Check type (basic validation)
            if param.name in kwargs:
                value = kwargs[param.name]
                if value is not None:
                    type_valid = self._check_type(value, param.type)
                    if not type_valid:
                        return f"Parameter '{param.name}' must be of type {param.type}"
                
                # Check choices
                if param.choices and value not in param.choices:
                    return f"Parameter '{param.name}' must be one of: {param.choices}"
        
        return None
    
    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected type."""
        type_mapping = {
            "string": str,
            "integer": int,
            "float": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        
        expected = type_mapping.get(expected_type)
        if expected is None:
            return True  # Unknown type, skip validation
        
        return isinstance(value, expected)
    
    def get_schema(self) -> Dict[str, Any]:
        """Get JSON schema for the tool."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "risk": self.risk.value,
            "requires_confirmation": self.requires_confirmation,
            "timeout_seconds": self.timeout_seconds,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                    "default": p.default,
                    "choices": p.choices
                }
                for p in self.parameters
            ]
        }
    
    def _get_execution_time_ms(self) -> int:
        """Get execution time in milliseconds."""
        if self._start_time:
            return int((time.time() - self._start_time) * 1000)
        return 0


class ToolRegistry:
    """
    Registry for all available tools.
    
    Tools register themselves here and can be retrieved by name.
    """
    
    _tools: Dict[str, type] = {}
    _instances: Dict[str, BaseTool] = {}
    
    @classmethod
    def register(cls, tool_class: type) -> type:
        """
        Register a tool class.
        
        Can be used as a decorator:
        @ToolRegistry.register
        class MyTool(BaseTool):
            ...
        """
        instance = tool_class()
        cls._tools[instance.name] = tool_class
        logger.debug(f"Registered tool: {instance.name}")
        return tool_class
    
    @classmethod
    def get_tool(
        cls,
        name: str,
        session_id: str = None,
        workspace_path: str = None
    ) -> Optional[BaseTool]:
        """
        Get a tool instance by name.
        
        Args:
            name: Tool name
            session_id: Current session ID
            workspace_path: Path to workspace
        
        Returns:
            Tool instance or None if not found
        """
        tool_class = cls._tools.get(name)
        if tool_class:
            return tool_class(session_id=session_id, workspace_path=workspace_path)
        return None
    
    @classmethod
    def list_tools(cls) -> List[str]:
        """List all registered tool names."""
        return list(cls._tools.keys())
    
    @classmethod
    def get_all_schemas(cls) -> List[Dict[str, Any]]:
        """Get schemas for all registered tools."""
        schemas = []
        for tool_class in cls._tools.values():
            instance = tool_class()
            schemas.append(instance.get_schema())
        return schemas
    
    @classmethod
    def get_tools_by_category(cls) -> Dict[str, List[str]]:
        """Get tools grouped by category."""
        categories = {}
        for tool_class in cls._tools.values():
            instance = tool_class()
            category = instance.category
            if category not in categories:
                categories[category] = []
            categories[category].append(instance.name)
        return categories


# Decorator for easy registration
def register_tool(cls):
    """Decorator to register a tool class."""
    return ToolRegistry.register(cls)


__all__ = [
    "BaseTool",
    "ToolResult",
    "ToolParameter",
    "ToolRisk",
    "ToolStatus",
    "ToolRegistry",
    "register_tool"
]
