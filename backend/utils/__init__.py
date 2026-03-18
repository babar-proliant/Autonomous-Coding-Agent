"""Utilities package for the Autonomous Coding Agent."""

from .logger import logger, AgentLogger, setup_logging
from .helpers import (
    generate_id,
    generate_short_id,
    timestamp,
    file_hash,
    content_hash,
    ensure_directory,
    safe_path,
    truncate_text,
    parse_json_safely,
    extract_json_from_text,
    count_tokens,
    format_size,
    parse_size,
    merge_dicts,
    flatten_dict,
    run_in_executor,
    AsyncContextManager,
)
from .security import (
    detect_secrets,
    redact_secrets,
    redact_dict,
    safe_log,
    PathValidator,
    validate_command_safety,
    SecretDetection,
    SENSITIVE_KEYS,
)

__all__ = [
    # Logging
    "logger",
    "AgentLogger",
    "setup_logging",
    # Helpers
    "generate_id",
    "generate_short_id",
    "timestamp",
    "file_hash",
    "content_hash",
    "ensure_directory",
    "safe_path",
    "truncate_text",
    "parse_json_safely",
    "extract_json_from_text",
    "count_tokens",
    "format_size",
    "parse_size",
    "merge_dicts",
    "flatten_dict",
    "run_in_executor",
    "AsyncContextManager",
    # Security
    "detect_secrets",
    "redact_secrets",
    "redact_dict",
    "safe_log",
    "PathValidator",
    "validate_command_safety",
    "SecretDetection",
    "SENSITIVE_KEYS",
]
