"""
Enhanced command execution with real-time streaming and allowlist security.
"""

import asyncio
import os
import signal
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable, AsyncGenerator
from dataclasses import dataclass
from enum import Enum
import re

from backend.config import settings
from backend.utils import logger, AgentLogger
from backend.core.event_bus import event_bus, EventType


class CommandRisk(str, Enum):
    """Risk level for commands."""
    SAFE = "safe"
    MODERATE = "moderate"
    DANGEROUS = "dangerous"
    BLOCKED = "blocked"


@dataclass
class CommandCheckResult:
    """Result of command safety check."""
    allowed: bool
    risk: CommandRisk
    reason: str = ""
    requires_confirmation: bool = False
    sanitized_command: str = ""


class AllowlistCommandFilter:
    """
    Allowlist-based command filter for maximum security.
    
    Only explicitly allowed commands can be executed.
    """
    
    # Default allowed command patterns
    ALLOWED_PATTERNS = {
        # File operations
        r"^ls(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        r"^cat\s+[^\|;<>&`]+\.[a-zA-Z]+$": CommandRisk.SAFE,
        r"^head\s+-n\s+\d+\s+[^\|;<>&`]+$": CommandRisk.SAFE,
        r"^tail\s+-n\s+\d+\s+[^\|;<>&`]+$": CommandRisk.SAFE,
        r"^mkdir\s+-p\s+[^\|;<>&`]+$": CommandRisk.SAFE,
        r"^touch\s+[^\|;<>&`]+$": CommandRisk.SAFE,
        r"^cp\s+-r?\s+[^\|;<>&`]+\s+[^\|;<>&`]+$": CommandRisk.MODERATE,
        r"^mv\s+[^\|;<>&`]+\s+[^\|;<>&`]+$": CommandRisk.MODERATE,
        r"^find\s+[^\|;<>&`]+\s+-name\s+[^\|;<>&`]+$": CommandRisk.SAFE,
        
        # Development tools
        r"^npm\s+(install|run|test|build|start|dev|init)(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        r"^npx\s+[a-zA-Z0-9_-]+(?:\s+[^\|;<>&`]*)?$": CommandRisk.MODERATE,
        r"^yarn\s+(install|add|test|build|start|dev)(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        r"^pnpm\s+(install|add|test|build|start|dev)(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        r"^pip\s+(install|uninstall|list|show)(?:\s+[^\|;<>&`]*)?$": CommandRisk.MODERATE,
        r"^pip3\s+(install|uninstall|list|show)(?:\s+[^\|;<>&`]*)?$": CommandRisk.MODERATE,
        r"^python\s+[a-zA-Z0-9_/-]+\.py(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        r"^python3\s+[a-zA-Z0-9_/-]+\.py(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        r"^node\s+[a-zA-Z0-9_/-]+\.js(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        r"^bun\s+(install|run|test|build|dev)(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        
        # Git operations
        r"^git\s+(status|log|diff|branch|add|commit|push|pull|clone|checkout|merge|stash)(?:\s+[^\|;<>&`]*)?$": CommandRisk.MODERATE,
        r"^git\s+init$": CommandRisk.SAFE,
        
        # Build tools
        r"^make(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        r"^cmake(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        r"^cargo\s+(build|run|test|check|clippy|fmt)(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        r"^go\s+(build|run|test|fmt|mod)(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        r"^rustc(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        r"^gcc(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        r"^g\+\+(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        
        # Testing
        r"^pytest(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        r"^jest(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        r"^vitest(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        r"^mocha(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        
        # Linting/formatting
        r"^eslint(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        r"^prettier(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        r"^black(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        r"^ruff(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        r"^mypy(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        r"^flake8(?:\s+[^\|;<>&`]*)?$": CommandRisk.SAFE,
        
        # Docker (moderate risk)
        r"^docker\s+(build|run|ps|images|logs|exec|stop|rm)(?:\s+[^\|;<>&`]*)?$": CommandRisk.MODERATE,
        r"^docker-compose\s+(up|down|build|ps|logs)(?:\s+[^\|;<>&`]*)?$": CommandRisk.MODERATE,
        
        # Safe utilities
        r"^echo\s+[^\|;<>&`]+$": CommandRisk.SAFE,
        r"^pwd$": CommandRisk.SAFE,
        r"^which\s+[a-zA-Z0-9_-]+$": CommandRisk.SAFE,
        r"^env$": CommandRisk.SAFE,
        r"^date$": CommandRisk.SAFE,
        r"^uname(?:\s+-[a-z])?$": CommandRisk.SAFE,
        r"^wc\s+-[lwc]\s+[^\|;<>&`]+$": CommandRisk.SAFE,
        r"^grep\s+[^\|;<>&`]+$": CommandRisk.SAFE,
    }
    
    # Always blocked patterns (even if in allowlist)
    BLOCKED_PATTERNS = [
        r"rm\s+-rf\s+/",
        r"rm\s+-rf\s+~",
        r"rm\s+-rf\s+\*",
        r">\s*/dev/sd",
        r"mkfs",
        r"dd\s+if=",
        r"chmod\s+777\s+/",
        r":\(\)\{.*:\|:&\s*\}",  # Fork bomb
        r"curl.*\|\s*(ba)?sh",
        r"wget.*\|\s*(ba)?sh",
        r"eval\s+",
        r"exec\s+",
        r">\s*/etc/",
        r">\s*/sys/",
        r">\s*/proc/",
    ]
    
    # Commands requiring confirmation
    CONFIRMATION_REQUIRED = [
        r"^rm\s+",
        r"^git\s+push\s+--force",
        r"^git\s+reset\s+--hard",
        r"^docker\s+system\s+prune",
        r"^npm\s+publish",
    ]
    
    def __init__(self):
        self._logger = AgentLogger("AllowlistFilter")
        self._custom_allowed: Dict[str, CommandRisk] = {}
    
    def add_allowed_pattern(self, pattern: str, risk: CommandRisk = CommandRisk.SAFE):
        """Add a custom allowed pattern."""
        self._custom_allowed[pattern] = risk
    
    def check_command(self, command: str) -> CommandCheckResult:
        """
        Check if a command is allowed.
        
        Args:
            command: Command to check
            
        Returns:
            CommandCheckResult with approval status
        """
        command = command.strip()
        
        # First, check blocked patterns
        for pattern in self.BLOCKED_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return CommandCheckResult(
                    allowed=False,
                    risk=CommandRisk.BLOCKED,
                    reason=f"Command matches blocked pattern: {pattern}",
                    sanitized_command=""
                )
        
        # Check for dangerous characters/constructs
        dangerous_chars = ["|", ";", "&", "`", "$(", "${"]
        for char in dangerous_chars:
            if char in command:
                return CommandCheckResult(
                    allowed=False,
                    risk=CommandRisk.BLOCKED,
                    reason=f"Command contains dangerous character/construct: {char}",
                    sanitized_command=""
                )
        
        # Check against allowed patterns
        all_patterns = {**self._custom_allowed, **self.ALLOWED_PATTERNS}
        
        for pattern, risk in all_patterns.items():
            try:
                if re.match(pattern, command, re.IGNORECASE):
                    # Check if confirmation required
                    requires_confirmation = any(
                        re.search(p, command, re.IGNORECASE)
                        for p in self.CONFIRMATION_REQUIRED
                    )
                    
                    return CommandCheckResult(
                        allowed=True,
                        risk=risk,
                        reason=f"Matched allowlist pattern",
                        requires_confirmation=requires_confirmation,
                        sanitized_command=command
                    )
            except re.error:
                continue
        
        # Command not in allowlist
        return CommandCheckResult(
            allowed=False,
            risk=CommandRisk.BLOCKED,
            reason="Command not in allowlist. Use a different approach or request administrator to add pattern.",
            sanitized_command=""
        )


class StreamingCommandExecutor:
    """
    Executes commands with real-time stdout/stderr streaming.
    """
    
    def __init__(self, session_id: str, workspace_path: str):
        self.session_id = session_id
        self.workspace_path = Path(workspace_path)
        self.filter = AllowlistCommandFilter()
        self._logger = AgentLogger("CommandExecutor", session_id)
        self._active_processes: Dict[str, asyncio.subprocess.Process] = {}
    
    async def execute(
        self,
        command: str,
        timeout: int = 300,
        cwd: str = "."
    ) -> Dict[str, Any]:
        """
        Execute a command with streaming output.
        
        Args:
            command: Command to execute
            timeout: Timeout in seconds
            cwd: Working directory
            
        Returns:
            Execution result
        """
        # Safety check
        check_result = self.filter.check_command(command)
        if not check_result.allowed:
            return {
                "success": False,
                "error": check_result.reason,
                "blocked": True
            }
        
        if check_result.requires_confirmation:
            # Emit event requiring user confirmation
            await event_bus.emit(
                EventType.USER_APPROVAL_REQUIRED,
                self.session_id,
                command=command,
                reason="Command requires confirmation"
            )
            # For now, proceed - in production would wait for approval
        
        # Resolve working directory
        work_dir = self.workspace_path / cwd
        work_dir = work_dir.resolve()
        
        # Verify within workspace
        try:
            work_dir.relative_to(self.workspace_path.resolve())
        except ValueError:
            return {
                "success": False,
                "error": "Working directory must be within workspace"
            }
        
        start_time = time.time()
        stdout_chunks = []
        stderr_chunks = []
        
        try:
            # Create process with new session for proper process group
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(work_dir),
                start_new_session=True,  # Create new process group
            )
            
            # Store active process
            process_id = f"proc_{time.time()}"
            self._active_processes[process_id] = process
            
            # Emit tool start event
            await event_bus.emit(
                EventType.TOOL_START,
                self.session_id,
                tool_name="execute_command",
                command=command
            )
            
            # Stream output concurrently
            async def read_stream(stream, event_type, chunks):
                """Read from stream and emit events."""
                try:
                    while True:
                        line = await asyncio.wait_for(
                            stream.readline(),
                            timeout=timeout
                        )
                        if not line:
                            break
                        
                        line_text = line.decode('utf-8', errors='replace')
                        chunks.append(line_text)
                        
                        # Emit streaming event
                        await event_bus.emit(
                            event_type,
                            self.session_id,
                            line=line_text.strip(),
                            stream=event_type.split('_')[-1]
                        )
                except asyncio.TimeoutError:
                    pass
            
            # Run both stream readers concurrently
            await asyncio.gather(
                read_stream(process.stdout, EventType.TOOL_OUTPUT, stdout_chunks),
                read_stream(process.stderr, EventType.TOOL_OUTPUT, stderr_chunks),
            )
            
            # Wait for process to complete with timeout
            try:
                return_code = await asyncio.wait_for(
                    process.wait(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                # Kill process group
                await self._kill_process_group(process)
                return {
                    "success": False,
                    "error": f"Command timed out after {timeout} seconds",
                    "stdout": "".join(stdout_chunks),
                    "stderr": "".join(stderr_chunks),
                    "return_code": -1
                }
            
            # Remove from active processes
            if process_id in self._active_processes:
                del self._active_processes[process_id]
            
            execution_time = int((time.time() - start_time) * 1000)
            
            stdout_text = "".join(stdout_chunks)
            stderr_text = "".join(stderr_chunks)
            
            # Truncate if needed
            max_output = settings.max_command_output_size
            if len(stdout_text) > max_output:
                stdout_text = stdout_text[:max_output] + "\n... [truncated]"
            if len(stderr_text) > max_output:
                stderr_text = stderr_text[:max_output] + "\n... [truncated]"
            
            # Emit completion event
            await event_bus.emit(
                EventType.TOOL_RESULT,
                self.session_id,
                tool_name="execute_command",
                success=return_code == 0,
                execution_time_ms=execution_time
            )
            
            return {
                "success": return_code == 0,
                "stdout": stdout_text,
                "stderr": stderr_text,
                "return_code": return_code,
                "execution_time_ms": execution_time
            }
            
        except Exception as e:
            self._logger.error(f"Command execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "stdout": "".join(stdout_chunks),
                "stderr": "".join(stderr_chunks)
            }
    
    async def execute_streaming(
        self,
        command: str,
        timeout: int = 300,
        cwd: str = "."
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute command and yield output chunks in real-time.
        
        Yields:
            Dict with 'type', 'content', 'stream' keys
        """
        # Safety check
        check_result = self.filter.check_command(command)
        if not check_result.allowed:
            yield {
                "type": "error",
                "content": check_result.reason,
                "stream": "system"
            }
            return
        
        # Resolve working directory
        work_dir = self.workspace_path / cwd
        work_dir = work_dir.resolve()
        
        try:
            work_dir.relative_to(self.workspace_path.resolve())
        except ValueError:
            yield {
                "type": "error",
                "content": "Working directory must be within workspace",
                "stream": "system"
            }
            return
        
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(work_dir),
                start_new_session=True
            )
            
            yield {
                "type": "start",
                "content": f"Started: {command}",
                "stream": "system"
            }
            
            # Stream both stdout and stderr
            async def read_and_yield():
                """Read from both streams and yield lines."""
                tasks = []
                
                async def read_stdout():
                    while True:
                        line = await process.stdout.readline()
                        if not line:
                            break
                        yield ("stdout", line.decode('utf-8', errors='replace'))
                
                async def read_stderr():
                    while True:
                        line = await process.stderr.readline()
                        if not line:
                            break
                        yield ("stderr", line.decode('utf-8', errors='replace'))
                
                # Create async generators
                stdout_gen = read_stdout()
                stderr_gen = read_stderr()
                
                # Use asyncio to interleave outputs
                while True:
                    # Check both streams
                    stdout_done = False
                    stderr_done = False
                    
                    # Try to get from stdout
                    try:
                        async for stream, line in stdout_gen:
                            yield (stream, line)
                            break
                    except StopAsyncIteration:
                        stdout_done = True
                    
                    # Try to get from stderr
                    try:
                        async for stream, line in stderr_gen:
                            yield (stream, line)
                            break
                    except StopAsyncIteration:
                        stderr_done = True
                    
                    if stdout_done and stderr_done:
                        break
            
            # Yield output
            async for stream, line in read_and_yield():
                yield {
                    "type": "output",
                    "content": line,
                    "stream": stream
                }
            
            # Wait for completion
            try:
                return_code = await asyncio.wait_for(
                    process.wait(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                await self._kill_process_group(process)
                yield {
                    "type": "error",
                    "content": f"Command timed out after {timeout} seconds",
                    "stream": "system"
                }
                return
            
            yield {
                "type": "complete",
                "content": f"Process completed with return code {return_code}",
                "stream": "system",
                "return_code": return_code
            }
            
        except Exception as e:
            yield {
                "type": "error",
                "content": str(e),
                "stream": "system"
            }
    
    async def _kill_process_group(self, process: asyncio.subprocess.Process):
        """Kill a process and all its children."""
        try:
            # Send SIGTERM to process group
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            
            # Wait briefly
            await asyncio.sleep(0.5)
            
            # Force kill if still running
            if process.returncode is None:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                await process.wait()
                
        except (ProcessLookupError, OSError):
            # Process already dead
            pass
    
    async def stop_all(self):
        """Stop all active processes."""
        for process_id, process in list(self._active_processes.items()):
            if process.returncode is None:
                await self._kill_process_group(process)
        
        self._active_processes.clear()


__all__ = [
    "AllowlistCommandFilter",
    "StreamingCommandExecutor",
    "CommandCheckResult",
    "CommandRisk"
]
