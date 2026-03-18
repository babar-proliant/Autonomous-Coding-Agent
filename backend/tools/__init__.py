"""Tools package for the Autonomous Coding Agent."""

from .base_tool import (
    BaseTool,
    ToolResult,
    ToolParameter,
    ToolRisk,
    ToolStatus,
    ToolRegistry,
    register_tool
)

# Import all tool implementations to register them with ToolRegistry
# These imports MUST be here for the @register_tool decorators to run
from .filesystem import (
    ReadFileTool,
    WriteFileTool,
    EditFileTool,
    DeleteFileTool,
    ListDirectoryTool,
    CreateDirectoryTool,
    SearchFilesTool,
    FindFileTool,
    ListAllFilesTool,
)

from .terminal import (
    ExecuteCommandTool,
    StartProcessTool,
    ReadProcessOutputTool,
    StopProcessTool,
)

__all__ = [
    "BaseTool",
    "ToolResult",
    "ToolParameter",
    "ToolRisk",
    "ToolStatus",
    "ToolRegistry",
    "register_tool",
    # Filesystem tools
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool",
    "DeleteFileTool",
    "ListDirectoryTool",
    "CreateDirectoryTool",
    "SearchFilesTool",
    "FindFileTool",
    "ListAllFilesTool",
    # Terminal tools
    "ExecuteCommandTool",
    "StartProcessTool",
    "ReadProcessOutputTool",
    "StopProcessTool",
]
