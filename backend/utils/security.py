"""
Security utilities for the Autonomous Coding Agent.
Includes secret redaction, path validation, and safety checks.
"""

import re
from typing import Dict, Any, List, Set, Optional, Union
from pathlib import Path
from dataclasses import dataclass
import os

from backend.config import settings
from backend.utils import logger


# Patterns for detecting secrets
SECRET_PATTERNS = {
    # API Keys
    "api_key": [
        r"sk-[a-zA-Z0-9]{20,}",
        r"sk_live_[a-zA-Z0-9]{24,}",
        r"api[_-]?key['\"]:\\s*['\"]?[a-zA-Z0-9_-]{20,}",
        r"x-api-key['\"]:\\s*['\"]?[a-zA-Z0-9_-]{20,}",
    ],
    # Tokens
    "token": [
        r"ghp_[a-zA-Z0-9]{36,}",
        r"gho_[a-zA-Z0-9]{36,}",
        r"ghu_[a-zA-Z0-9]{36,}",
        r"ghs_[a-zA-Z0-9]{36,}",
        r"ghr_[a-zA-Z0-9]{36,}",
        r"token['\"]:\\s*['\"]?[a-zA-Z0-9_-]{20,}",
        r"access_token['\"]:\\s*['\"]?[a-zA-Z0-9_-]{20,}",
        r"auth_token['\"]:\\s*['\"]?[a-zA-Z0-9_-]{20,}",
    ],
    # AWS
    "aws": [
        r"AKIA[0-9A-Z]{16}",
        r"aws_access_key_id['\"]:\\s*['\"]?AKIA[0-9A-Z]{16}",
        r"aws_secret_access_key['\"]:\\s*['\"]?[a-zA-Z0-9/+=]{40}",
    ],
    # Private Keys
    "private_key": [
        r"-----BEGIN (?:RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----",
        r"-----BEGIN PGP PRIVATE KEY BLOCK-----",
    ],
    # Passwords
    "password": [
        r"password['\"]:\\s*['\"]?[^'\"]{8,}",
        r"passwd['\"]:\\s*['\"]?[^'\"]{8,}",
        r"pwd['\"]:\\s*['\"]?[^'\"]{8,}",
    ],
    # Database URLs
    "database_url": [
        r"postgres(?:ql)?://[^:]+:[^@]+@[^/]+/[^\s]+",
        r"mysql://[^:]+:[^@]+@[^/]+/[^\s]+",
        r"mongodb(?:\\+srv)?://[^:]+:[^@]+@[^\s]+",
        r"redis://[^:]*:[^@]+@[^/]+[^\s]*",
    ],
    # Other secrets
    "secrets": [
        r"secret[_-]?key['\"]:\\s*['\"]?[a-zA-Z0-9_-]{16,}",
        r"private[_-]?key['\"]:\\s*['\"]?[a-zA-Z0-9_-]{16,}",
    ],
}

# Keys in dictionaries that should be redacted
SENSITIVE_KEYS: Set[str] = {
    "password", "passwd", "pwd",
    "secret", "secret_key", "secretkey",
    "api_key", "apikey", "api-key",
    "token", "access_token", "accesstoken", "auth_token",
    "private_key", "privatekey", "private-key",
    "api_secret", "apisecret", "api-secret",
    "client_secret", "clientsecret",
    "auth", "authorization", "bearer",
    "credential", "credentials",
    "key", "private_key_pem", "public_key",
}


@dataclass
class SecretDetection:
    """Result of secret detection."""
    has_secrets: bool
    detected_types: List[str]
    positions: List[Dict[str, Any]]
    redacted_text: str


def detect_secrets(text: str) -> SecretDetection:
    """
    Detect potential secrets in text.
    
    Args:
        text: Text to analyze
        
    Returns:
        SecretDetection with results
    """
    detected_types = set()
    positions = []
    
    for secret_type, patterns in SECRET_PATTERNS.items():
        for pattern in patterns:
            try:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    detected_types.add(secret_type)
                    positions.append({
                        "type": secret_type,
                        "start": match.start(),
                        "end": match.end(),
                        "pattern": pattern[:50] + "..." if len(pattern) > 50 else pattern
                    })
            except re.error:
                continue
    
    return SecretDetection(
        has_secrets=len(detected_types) > 0,
        detected_types=list(detected_types),
        positions=positions,
        redacted_text=redact_secrets(text) if detected_types else text
    )


def redact_secrets(text: str, replacement: str = "***REDACTED***") -> str:
    """
    Redact secrets from text.
    
    Args:
        text: Text to redact
        replacement: String to replace secrets with
        
    Returns:
        Text with secrets redacted
    """
    redacted = text
    
    for patterns in SECRET_PATTERNS.values():
        for pattern in patterns:
            try:
                redacted = re.sub(pattern, replacement, redacted, flags=re.IGNORECASE)
            except re.error:
                continue
    
    return redacted


def redact_dict(data: Dict[str, Any], replacement: str = "***REDACTED***") -> Dict[str, Any]:
    """
    Redact sensitive values in a dictionary.
    
    Args:
        data: Dictionary to process
        replacement: String to replace sensitive values with
        
    Returns:
        Dictionary with sensitive values redacted
    """
    if not isinstance(data, dict):
        return data
    
    result = {}
    
    for key, value in data.items():
        key_lower = key.lower().replace("-", "_")
        
        # Check if key is sensitive
        if key_lower in SENSITIVE_KEYS:
            result[key] = replacement
        elif isinstance(value, dict):
            result[key] = redact_dict(value, replacement)
        elif isinstance(value, str):
            # Check for secrets in string values
            detection = detect_secrets(value)
            if detection.has_secrets:
                result[key] = detection.redacted_text
            else:
                result[key] = value
        elif isinstance(value, list):
            result[key] = [
                redact_dict(item, replacement) if isinstance(item, dict)
                else redact_secrets(item) if isinstance(item, str)
                else item
                for item in value
            ]
        else:
            result[key] = value
    
    return result


def safe_log(data: Any) -> Any:
    """
    Prepare data for safe logging by redacting secrets.
    
    Args:
        data: Data to prepare
        
    Returns:
        Safe version of data with secrets redacted
    """
    if isinstance(data, dict):
        return redact_dict(data)
    elif isinstance(data, str):
        return redact_secrets(data)
    elif isinstance(data, list):
        return [safe_log(item) for item in data]
    else:
        return data


class PathValidator:
    """
    Validates and sanitizes file paths for security.
    """
    
    def __init__(self, workspace_path: str):
        self.workspace_path = Path(workspace_path).resolve()
        self.protected_paths = [Path(p).resolve() for p in settings.protected_paths]
    
    def is_safe_path(self, path: Union[str, Path]) -> bool:
        """
        Check if a path is safe to access.
        
        Args:
            path: Path to check
            
        Returns:
            True if path is safe
        """
        try:
            target = Path(path)
            
            # If path is relative, resolve from workspace
            if not target.is_absolute():
                target = self.workspace_path / target
            
            target = target.resolve()
            
            # Check protected paths
            for protected in self.protected_paths:
                try:
                    target.relative_to(protected)
                    return False  # Path is inside protected area
                except ValueError:
                    pass
            
            # Check workspace boundary
            try:
                target.relative_to(self.workspace_path)
            except ValueError:
                return False  # Path is outside workspace
            
            # Check for symlinks pointing outside workspace
            if target.exists() and target.is_symlink():
                real_target = target.resolve()
                try:
                    real_target.relative_to(self.workspace_path)
                except ValueError:
                    return False  # Symlink points outside workspace
            
            return True
            
        except Exception as e:
            logger.warning(f"Path validation error: {e}")
            return False
    
    def resolve_safe_path(self, path: Union[str, Path]) -> Optional[Path]:
        """
        Resolve a path safely within the workspace.
        
        Args:
            path: Path to resolve
            
        Returns:
            Resolved Path if safe, None otherwise
        """
        try:
            target = Path(path)
            
            # If path is relative, resolve from workspace
            if not target.is_absolute():
                target = self.workspace_path / target
            
            target = target.resolve()
            
            if not self.is_safe_path(target):
                raise ValueError(f"Path outside workspace: {target}")
            
            return target
            
        except Exception as e:
            logger.warning(f"Failed to resolve safe path: {e}")
            return None
    
    def is_symlink_safe(self, path: Union[str, Path]) -> bool:
        """
        Check if a path's symlink target is safe.
        
        Args:
            path: Path to check
            
        Returns:
            True if symlink target is within workspace
        """
        try:
            target = Path(path)
            
            if not target.exists() or not target.is_symlink():
                return True  # Not a symlink, no issue
            
            real_target = target.resolve()
            
            # Check if real target is within workspace
            try:
                real_target.relative_to(self.workspace_path)
                return True
            except ValueError:
                return False
                
        except Exception:
            return False
    
    def validate_no_escape(self, path: Union[str, Path]) -> bool:
        """
        Validate that path doesn't attempt to escape workspace.
        
        Checks for:
        - Directory traversal (..)
        - Symlinks pointing outside
        - Absolute paths outside workspace
        """
        path_str = str(path)
        
        # Check for obvious traversal attempts
        if ".." in path_str.split(os.sep):
            return False
        
        # Check for absolute path outside workspace
        if os.path.isabs(path_str):
            try:
                Path(path_str).relative_to(self.workspace_path)
            except ValueError:
                return False
        
        return self.is_symlink_safe(path)


def validate_command_safety(command: str) -> tuple[bool, str]:
    """
    Validate a shell command for safety issues.
    
    Returns:
        Tuple of (is_safe, reason)
    """
    # Check for common injection patterns
    dangerous_patterns = [
        (r';\s*rm\s', "Command injection attempt with rm"),
        (r'\$\([^)]+\)', "Subshell injection attempt"),
        (r'`[^`]+`', "Backtick injection attempt"),
        (r'\|\s*sh\s*$', "Pipe to shell injection"),
        (r'\|\s*bash\s*$', "Pipe to bash injection"),
        (r'>\s*/dev/[sh]d', "Direct disk write attempt"),
        (r'chmod\s+777\s+/', "Dangerous permission change"),
        (r'sudo\s+su', "Privilege escalation attempt"),
        (r'eval\s+', "Eval injection risk"),
    ]
    
    for pattern, reason in dangerous_patterns:
        if re.search(pattern, command, re.IGNORECASE):
            return False, reason
    
    return True, "OK"


__all__ = [
    "detect_secrets",
    "redact_secrets",
    "redact_dict",
    "safe_log",
    "PathValidator",
    "validate_command_safety",
    "SecretDetection",
    "SENSITIVE_KEYS",
]
