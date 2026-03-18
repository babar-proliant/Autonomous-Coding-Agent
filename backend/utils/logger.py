"""
Logging system for the Autonomous Coding Agent.
Uses Loguru for structured logging with rotation and formatting.
"""

import sys
from pathlib import Path
from loguru import logger
from typing import Optional
import json
from datetime import datetime

from backend.config import settings, LOGS_DIR


# Remove default handler
logger.remove()

# Custom format for console output
CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{message}</level>"
)

# Custom format for file output (JSON)
def json_format(record):
    """Format log record as JSON for structured logging."""
    log_entry = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "module": record["name"],
        "function": record["function"],
        "line": record["line"],
        "message": record["message"],
    }
    
    # Add extra data if present
    if record.get("extra"):
        log_entry["extra"] = record["extra"]
    
    # Add exception info if present
    if record["exception"]:
        log_entry["exception"] = {
            "type": record["exception"].type.__name__ if record["exception"].type else None,
            "value": str(record["exception"].value) if record["exception"].value else None,
            "traceback": record["exception"].traceback if record["exception"].traceback else None,
        }
    
    return json.dumps(log_entry) + "\n"


def setup_logging():
    """Configure logging handlers based on settings."""
    
    # Ensure logs directory exists
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Console handler (colored output)
    logger.add(
        sys.stderr,
        format=CONSOLE_FORMAT,
        level=settings.log_level.value,
        colorize=True,
        backtrace=True,
        diagnose=settings.debug,
    )
    
    # Main log file (with rotation)
    logger.add(
        LOGS_DIR / "agent_{time:YYYY-MM-DD}.log",
        format=CONSOLE_FORMAT,
        level="DEBUG",
        rotation="00:00",  # Rotate at midnight
        retention="7 days",
        compression="gz",
        colorize=False,
        backtrace=True,
        diagnose=settings.debug,
    )
    
    # JSON structured log file (for analysis)
    logger.add(
        LOGS_DIR / "agent_structured_{time:YYYY-MM-DD}.jsonl",
        level="DEBUG",
        rotation="00:00",
        retention="30 days",
        compression="gz",
        serialize=True,
    )
    
    # Error-only log file
    logger.add(
        LOGS_DIR / "errors_{time:YYYY-MM-DD}.log",
        format=CONSOLE_FORMAT,
        level="ERROR",
        rotation="00:00",
        retention="30 days",
        compression="gz",
        backtrace=True,
        diagnose=True,
    )
    
    logger.info(f"Logging initialized. Log level: {settings.log_level.value}")
    logger.info(f"Log files location: {LOGS_DIR}")


class AgentLogger:
    """Context-aware logger for agent activities."""
    
    def __init__(self, agent_name: str, session_id: Optional[str] = None):
        self.agent_name = agent_name
        self.session_id = session_id
        self.logger = logger.bind(
            agent=agent_name,
            session_id=session_id or "no-session"
        )
    
    def thinking(self, message: str, **kwargs):
        """Log agent thinking process."""
        self.logger.bind(**kwargs).info(f"[THINKING] {message}")
    
    def tool_use(self, tool_name: str, params: dict, **kwargs):
        """Log tool usage."""
        self.logger.bind(tool=tool_name, **kwargs).info(
            f"[TOOL] Using {tool_name} with params: {params}"
        )
    
    def tool_result(self, tool_name: str, success: bool, result: str = None, **kwargs):
        """Log tool result."""
        status = "SUCCESS" if success else "FAILED"
        self.logger.bind(tool=tool_name, success=success, **kwargs).info(
            f"[TOOL] {tool_name} {status}: {result[:200] if result else 'N/A'}..."
        )
    
    def decision(self, decision: str, reasoning: str, **kwargs):
        """Log agent decision."""
        self.logger.bind(**kwargs).info(
            f"[DECISION] {decision} - Reason: {reasoning}"
        )
    
    def error(self, error: Exception, context: dict = None, **kwargs):
        """Log error with context."""
        self.logger.bind(**(context or {}), **kwargs).error(
            f"[ERROR] {type(error).__name__}: {str(error)}"
        )
    
    def info(self, message: str, **kwargs):
        """Log info message."""
        self.logger.bind(**kwargs).info(message)
    
    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self.logger.bind(**kwargs).debug(message)
    
    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self.logger.bind(**kwargs).warning(message)


# Initialize logging on import
setup_logging()

# Export logger and AgentLogger
__all__ = ["logger", "AgentLogger", "setup_logging"]
