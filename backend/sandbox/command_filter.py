"""
Command filtering system for safe command execution.
"""

import re
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum

from backend.config import settings
from backend.utils import logger
import yaml
from pathlib import Path


class CommandAction(str, Enum):
    """Action to take for a command."""
    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"


@dataclass
class FilterResult:
    """Result of command filtering."""
    action: CommandAction
    blocked: bool
    reason: str = ""
    matched_pattern: str = ""
    requires_confirmation: bool = False


class CommandFilter:
    """
    Filters shell commands for safety.
    
    Uses blocklist mode by default - allows all commands
    except those explicitly blocked.
    """
    
    def __init__(self, config_path: str = None):
        """Initialize command filter with configuration."""
        self.blocked_commands: List[str] = []
        self.warn_commands: List[str] = []
        self.dangerous_patterns: List[str] = []
        self.mode = "blocklist"
        
        # Load configuration
        self._load_config(config_path)
    
    def _load_config(self, config_path: str = None):
        """Load command filter configuration."""
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "safety.yaml"
        
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            cmd_config = config.get('command_filter', {})
            self.mode = cmd_config.get('mode', 'blocklist')
            self.blocked_commands = cmd_config.get('blocked_commands', [])
            self.warn_commands = cmd_config.get('warn_commands', [])
            self.dangerous_patterns = cmd_config.get('dangerous_patterns', [])
            
            logger.info(f"Command filter loaded: {len(self.blocked_commands)} blocked, "
                       f"{len(self.warn_commands)} warn patterns")
            
        except Exception as e:
            logger.warning(f"Could not load command filter config: {e}")
            # Use defaults
            self._set_defaults()
    
    def _set_defaults(self):
        """Set default blocked commands."""
        self.blocked_commands = [
            "rm -rf /",
            "rm -rf ~",
            "rm -rf *",
            "mkfs",
            "dd if=/dev/zero",
            "shutdown",
            "reboot",
            "sudo su",
            "chmod 777 /",
        ]
        
        self.warn_commands = [
            "rm -rf",
            "git push --force",
            "sudo",
        ]
        
        self.dangerous_patterns = [
            r"rm\s+-rf\s+[^.]",
            r">\s*/dev/sd",
            r"curl.*\|.*sh",
        ]
    
    def check_command(self, command: str) -> FilterResult:
        """
        Check if a command is safe to execute.
        
        Args:
            command: The command to check
        
        Returns:
            FilterResult with action and reason
        """
        command_lower = command.lower().strip()
        
        # Check blocked commands (exact match)
        for blocked in self.blocked_commands:
            if blocked.lower() in command_lower:
                return FilterResult(
                    action=CommandAction.BLOCK,
                    blocked=True,
                    reason=f"Command matches blocked pattern: {blocked}",
                    matched_pattern=blocked
                )
        
        # Check dangerous patterns (regex)
        for pattern in self.dangerous_patterns:
            try:
                if re.search(pattern, command, re.IGNORECASE):
                    return FilterResult(
                        action=CommandAction.BLOCK,
                        blocked=True,
                        reason=f"Command matches dangerous pattern: {pattern}",
                        matched_pattern=pattern
                    )
            except re.error:
                continue
        
        # Check warn commands
        for warn in self.warn_commands:
            if warn.lower() in command_lower:
                return FilterResult(
                    action=CommandAction.WARN,
                    blocked=False,
                    reason=f"Command may be dangerous: {warn}",
                    matched_pattern=warn,
                    requires_confirmation=settings.debug  # Require confirmation in debug mode
                )
        
        # Command is allowed
        return FilterResult(
            action=CommandAction.ALLOW,
            blocked=False
        )
    
    def sanitize_command(self, command: str) -> str:
        """
        Sanitize a command by removing dangerous parts.
        
        This is a best-effort sanitization.
        """
        # Remove any shell expansions that could be dangerous
        sanitized = command
        
        # Remove backticks
        sanitized = re.sub(r'`([^`]*)`', r'\1', sanitized)
        
        # Remove $() subshells
        sanitized = re.sub(r'\$\(([^)]*)\)', r'\1', sanitized)
        
        return sanitized
    
    def is_safe_path(self, path: str, workspace: str = None) -> bool:
        """
        Check if a path is safe to access.
        
        Args:
            path: Path to check
            workspace: Workspace directory (paths outside are unsafe)
        """
        from pathlib import Path
        
        try:
            resolved = Path(path).resolve()
            
            # Check protected paths
            for protected in settings.protected_paths:
                if str(resolved).startswith(protected):
                    return False
            
            # Check workspace boundary
            if workspace:
                workspace_path = Path(workspace).resolve()
                try:
                    resolved.relative_to(workspace_path)
                except ValueError:
                    return False
            
            return True
            
        except Exception:
            return False


__all__ = ["CommandFilter", "FilterResult", "CommandAction"]
