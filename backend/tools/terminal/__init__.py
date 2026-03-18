"""Terminal and command execution tools for the Autonomous Coding Agent."""

from ..base_tool import BaseTool, ToolResult, ToolParameter, ToolRisk, ToolStatus, register_tool
from backend.config import settings
from backend.utils import logger

import asyncio
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
import time


class CommandFilter:
    """Simple command filter for safety."""
    
    BLOCKED_COMMANDS = [
        "rm -rf /", "format", "del /f", "shutdown", "reboot",
        "mkfs", "dd if=", "> /dev/sd", "chmod 777 /"
    ]
    
    def check_command(self, command: str):
        """Check if command is allowed."""
        from dataclasses import dataclass
        @dataclass
        class FilterResult:
            blocked: bool
            reason: str = ""
        
        cmd_lower = command.lower()
        for blocked in self.BLOCKED_COMMANDS:
            if blocked.lower() in cmd_lower:
                return FilterResult(blocked=True, reason=f"Blocked command pattern: {blocked}")
        
        return FilterResult(blocked=False)


@register_tool
class ExecuteCommandTool(BaseTool):
    """Tool for executing shell commands."""
    
    name = "execute_command"
    description = "Execute a shell command in the workspace"
    category = "terminal"
    risk = ToolRisk.HIGH
    timeout_seconds = 300
    requires_confirmation = False
    
    parameters = [
        ToolParameter(
            name="command",
            type="string",
            description="Command to execute",
            required=True
        ),
        ToolParameter(
            name="cwd",
            type="string",
            description="Working directory for command execution",
            required=False,
            default="."
        )
    ]
    
    def __init__(self, session_id: str = None, workspace_path: str = None):
        super().__init__(session_id, workspace_path)
        self.command_filter = CommandFilter()
    
    async def execute(self, **kwargs) -> ToolResult:
        command = kwargs["command"]
        cwd = kwargs.get("cwd", ".")
        
        try:
            # Safety check
            filter_result = self.command_filter.check_command(command)
            if filter_result.blocked:
                return ToolResult(
                    tool_name=self.name,
                    status=ToolStatus.BLOCKED,
                    error=f"Command blocked: {filter_result.reason}"
                )
            
            # Resolve working directory
            work_dir = Path(self.workspace_path) / cwd
            work_dir = work_dir.resolve()
            
            # Execute command
            start_time = time.time()
            
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(work_dir)
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=60
                )
            except asyncio.TimeoutError:
                process.kill()
                return ToolResult(
                    tool_name=self.name,
                    status=ToolStatus.TIMEOUT,
                    error="Command timed out after 60 seconds"
                )
            
            execution_time = int((time.time() - start_time) * 1000)
            
            stdout_text = stdout.decode('utf-8', errors='replace')
            stderr_text = stderr.decode('utf-8', errors='replace')
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS if process.returncode == 0 else ToolStatus.FAILED,
                result={
                    "command": command,
                    "return_code": process.returncode,
                    "stdout": stdout_text[:5000],
                    "stderr": stderr_text[:5000],
                    "execution_time_ms": execution_time
                },
                error=stderr_text if process.returncode != 0 else None,
                execution_time_ms=execution_time
            )
            
        except Exception as e:
            logger.exception(f"Command execution failed: {e}")
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(e)
            )


@register_tool
class StartProcessTool(BaseTool):
    """Tool for starting long-running processes."""
    
    name = "start_process"
    description = "Start a long-running process in the background"
    category = "terminal"
    risk = ToolRisk.HIGH
    timeout_seconds = 30
    
    parameters = [
        ToolParameter(
            name="command",
            type="string",
            description="Command to start",
            required=True
        ),
        ToolParameter(
            name="name",
            type="string",
            description="Name to identify this process",
            required=True
        )
    ]
    
    _processes: Dict[str, asyncio.subprocess.Process] = {}
    
    def __init__(self, session_id: str = None, workspace_path: str = None):
        super().__init__(session_id, workspace_path)
        self.command_filter = CommandFilter()
    
    async def execute(self, **kwargs) -> ToolResult:
        command = kwargs["command"]
        name = kwargs["name"]
        
        try:
            filter_result = self.command_filter.check_command(command)
            if filter_result.blocked:
                return ToolResult(
                    tool_name=self.name,
                    status=ToolStatus.BLOCKED,
                    error=f"Command blocked: {filter_result.reason}"
                )
            
            if name in self._processes:
                existing = self._processes[name]
                if existing.returncode is None:
                    return ToolResult(
                        tool_name=self.name,
                        status=ToolStatus.FAILED,
                        error=f"Process '{name}' is already running"
                    )
            
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workspace_path)
            )
            
            self._processes[name] = process
            
            await asyncio.sleep(0.5)
            
            if process.returncode is not None:
                return ToolResult(
                    tool_name=self.name,
                    status=ToolStatus.FAILED,
                    error=f"Process exited immediately with code {process.returncode}"
                )
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                result={
                    "name": name,
                    "pid": process.pid,
                    "command": command,
                    "status": "running"
                }
            )
            
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(e)
            )


@register_tool
class ReadProcessOutputTool(BaseTool):
    """Tool for reading output from a running process."""
    
    name = "read_process_output"
    description = "Read output from a running process"
    category = "terminal"
    risk = ToolRisk.LOW
    timeout_seconds = 10
    
    parameters = [
        ToolParameter(
            name="name",
            type="string",
            description="Name of the process",
            required=True
        )
    ]
    
    async def execute(self, **kwargs) -> ToolResult:
        name = kwargs["name"]
        
        try:
            process = StartProcessTool.get_process(name)
            
            if not process:
                return ToolResult(
                    tool_name=self.name,
                    status=ToolStatus.FAILED,
                    error=f"Process '{name}' not found"
                )
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                result={
                    "name": name,
                    "status": "running" if process.returncode is None else "stopped"
                }
            )
            
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(e)
            )


@register_tool
class StopProcessTool(BaseTool):
    """Tool for stopping a running process."""
    
    name = "stop_process"
    description = "Stop a running process"
    category = "terminal"
    risk = ToolRisk.MEDIUM
    timeout_seconds = 10
    
    parameters = [
        ToolParameter(
            name="name",
            type="string",
            description="Name of the process to stop",
            required=True
        )
    ]
    
    async def execute(self, **kwargs) -> ToolResult:
        name = kwargs["name"]
        
        try:
            process = StartProcessTool.get_process(name)
            
            if not process:
                return ToolResult(
                    tool_name=self.name,
                    status=ToolStatus.FAILED,
                    error=f"Process '{name}' not found"
                )
            
            if process.returncode is not None:
                return ToolResult(
                    tool_name=self.name,
                    status=ToolStatus.SUCCESS,
                    result={"name": name, "status": "already_stopped"}
                )
            
            process.terminate()
            
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                result={"name": name, "status": "stopped"}
            )
            
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(e)
            )


__all__ = [
    "ExecuteCommandTool",
    "StartProcessTool",
    "ReadProcessOutputTool",
    "StopProcessTool"
]
