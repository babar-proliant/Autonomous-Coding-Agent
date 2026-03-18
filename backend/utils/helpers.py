"""Utility functions and helpers for the Autonomous Coding Agent."""

import os
import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
import asyncio
import functools


def generate_id() -> str:
    """Generate a unique identifier."""
    return str(uuid.uuid4())


def generate_short_id(length: int = 8) -> str:
    """Generate a short unique identifier."""
    return uuid.uuid4().hex[:length]


def timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.utcnow().isoformat()


def file_hash(file_path: Path) -> str:
    """Calculate SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def content_hash(content: Union[str, bytes]) -> str:
    """Calculate SHA256 hash of content."""
    sha256 = hashlib.sha256()
    if isinstance(content, str):
        content = content.encode("utf-8")
    sha256.update(content)
    return sha256.hexdigest()


def ensure_directory(path: Path) -> Path:
    """Ensure a directory exists, creating it if necessary."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_path(path: Union[str, Path], base_dir: Path) -> Path:
    """
    Resolve a path safely within a base directory.
    Prevents path traversal attacks.
    """
    path = Path(path)
    base_dir = Path(base_dir).resolve()
    
    # If path is absolute, make it relative to base
    if path.is_absolute():
        # Try to make it relative to base_dir
        try:
            path = path.relative_to(base_dir)
        except ValueError:
            raise ValueError(f"Path {path} is outside workspace {base_dir}")
    
    # Resolve the full path
    full_path = (base_dir / path).resolve()
    
    # Verify it's within base_dir
    try:
        full_path.relative_to(base_dir)
    except ValueError:
        raise ValueError(f"Resolved path {full_path} is outside workspace {base_dir}")
    
    return full_path


def truncate_text(text: str, max_length: int = 500, suffix: str = "...") -> str:
    """Truncate text to a maximum length."""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def parse_json_safely(text: str) -> Optional[Dict[str, Any]]:
    """Attempt to parse JSON from text, returning None on failure."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON object from text that may contain other content."""
    # Try direct parse first
    result = parse_json_safely(text)
    if result is not None:
        return result
    
    # Try to find JSON in markdown code blocks
    json_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
    matches = re.findall(json_pattern, text)
    for match in matches:
        result = parse_json_safely(match.strip())
        if result is not None:
            return result
    
    # Try to find JSON-like structures
    json_pattern = r'\{[\s\S]*\}'
    matches = re.findall(json_pattern, text)
    for match in matches:
        result = parse_json_safely(match)
        if result is not None:
            return result
    
    return None


def count_tokens(text: str) -> int:
    """
    Estimate token count for text.
    Uses a simple approximation: ~4 characters per token.
    """
    return len(text) // 4


def format_size(size_bytes: int) -> str:
    """Format byte size as human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def parse_size(size_str: str) -> int:
    """Parse size string (e.g., '10MB') to bytes."""
    size_str = size_str.strip().upper()
    
    units = {
        "B": 1,
        "KB": 1024,
        "MB": 1024 * 1024,
        "GB": 1024 * 1024 * 1024,
        "TB": 1024 * 1024 * 1024 * 1024,
    }
    
    for unit, multiplier in units.items():
        if size_str.endswith(unit):
            try:
                return int(float(size_str[:-len(unit)]) * multiplier)
            except ValueError:
                break
    
    # Try parsing as plain number (assume bytes)
    try:
        return int(size_str)
    except ValueError:
        return 0


def merge_dicts(base: Dict, override: Dict) -> Dict:
    """Recursively merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def flatten_dict(d: Dict, parent_key: str = "", sep: str = ".") -> Dict:
    """Flatten a nested dictionary."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


async def run_in_executor(func, *args, **kwargs):
    """Run a synchronous function in the default executor."""
    loop = asyncio.get_event_loop()
    partial_func = functools.partial(func, *args, **kwargs)
    return await loop.run_in_executor(None, partial_func)


class AsyncContextManager:
    """Base class for async context managers."""
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


__all__ = [
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
]
