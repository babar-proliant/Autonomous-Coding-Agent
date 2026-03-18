"""
Code-based Tool Call Parser using AST.

This allows the LLM to write natural Python code for tool calls
instead of rigid JSON format. The AST parser extracts function calls
and converts them to tool executions.

Example LLM output that works:
    write_file("index.html", "<html>...</html>")
    read_file("config.py")
    list_all_files()
    find_file("*.py")
"""

import ast
import json
from typing import List, Tuple, Dict, Any, Optional
from backend.utils import logger


class ToolCallParser:
    """
    Parse Python code to extract tool calls using AST.
    
    Simple and flexible - handles various Python syntaxes:
    - write_file("path", "content")
    - write_file(file_path="path", content="content")
    - write_file("path", content="content")
    """
    
    # Allowed tool names (whitelist for security)
    ALLOWED_TOOLS = {
        # File operations
        "read_file",
        "write_file", 
        "edit_file",
        "delete_file",
        "list_directory",
        "create_directory",
        "find_file",
        "list_all_files",
        "search_files",
        # Terminal
        "execute_command",
    }
    
    def __init__(self, allowed_tools: set = None):
        if allowed_tools:
            self.ALLOWED_TOOLS = allowed_tools
    
    def parse(self, code: str) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Parse code and extract tool calls.
        
        Returns list of (tool_name, args_dict) tuples.
        """
        tool_calls = []
        
        # Handle empty or None
        if not code or not code.strip():
            return tool_calls
        
        # Try to parse as Python
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            logger.debug(f"AST parse error: {e}")
            # Try to fix common issues and reparse
            fixed_code = self._fix_common_syntax(code)
            try:
                tree = ast.parse(fixed_code)
            except SyntaxError:
                # If still fails, try extracting just function calls
                return self._extract_simple_calls(code)
        
        # Walk the AST and find function calls
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                tool_call = self._parse_call(node)
                if tool_call:
                    tool_calls.append(tool_call)
        
        return tool_calls
    
    def _parse_call(self, node: ast.Call) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Parse a single function call AST node."""
        # Get function name
        func_name = None
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        
        if not func_name or func_name not in self.ALLOWED_TOOLS:
            return None
        
        # Parse arguments
        args = {}
        
        # Positional args -> map to common param names
        param_names = self._get_param_names(func_name)
        for i, arg in enumerate(node.args):
            value = self._parse_value(arg)
            if value is not None and i < len(param_names):
                args[param_names[i]] = value
        
        # Keyword args
        for keyword in node.keywords:
            value = self._parse_value(keyword.value)
            if value is not None:
                args[keyword.arg] = value
        
        return (func_name, args)
    
    def _parse_value(self, node) -> Any:
        """Parse an AST value node to Python value."""
        if node is None:
            return None
        
        # String
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        
        # Number
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        
        # Boolean
        if isinstance(node, ast.Constant) and isinstance(node.value, bool):
            return node.value
        
        # None
        if isinstance(node, ast.Constant) and node.value is None:
            return None
        
        # Dict
        if isinstance(node, ast.Dict):
            result = {}
            for key, value in zip(node.keys, node.values):
                k = self._parse_value(key)
                v = self._parse_value(value)
                if k is not None:
                    result[k] = v
            return result
        
        # List
        if isinstance(node, ast.List):
            return [self._parse_value(item) for item in node.elts]
        
        # Tuple
        if isinstance(node, ast.Tuple):
            return tuple(self._parse_value(item) for item in node.elts)
        
        # F-string or joined string
        if isinstance(node, ast.JoinedStr):
            parts = []
            for value in node.values:
                if isinstance(value, ast.Constant):
                    parts.append(str(value.value))
                else:
                    parts.append(f"{{{self._parse_value(value)}}}")
            return "".join(parts)
        
        # Variable reference (we can't resolve, return as string placeholder)
        if isinstance(node, ast.Name):
            return f"${node.id}"
        
        # Attribute access
        if isinstance(node, ast.Attribute):
            return f"$TODO"  # Placeholder
        
        # Call (nested function) - return as placeholder
        if isinstance(node, ast.Call):
            return "$EXPR"
        
        return None
    
    def _get_param_names(self, func_name: str) -> List[str]:
        """Get expected parameter names for a tool (for positional arg mapping)."""
        param_map = {
            "read_file": ["file_path", "encoding"],
            "write_file": ["file_path", "content"],
            "edit_file": ["file_path", "old_content", "new_content"],
            "delete_file": ["file_path"],
            "list_directory": ["dir_path", "show_hidden"],
            "create_directory": ["dir_path"],
            "find_file": ["pattern", "directory"],
            "list_all_files": ["extension"],
            "search_files": ["pattern", "directory"],
            "execute_command": ["command"],
        }
        return param_map.get(func_name, [])
    
    def _fix_common_syntax(self, code: str) -> str:
        """Try to fix common Python syntax issues."""
        # Wrap in a function if it's bare statements
        if not code.strip().startswith(("def ", "class ", "import ", "from ")):
            # Check if it looks like function calls
            if "(" in code and ")" in code:
                return code  # Probably fine
        
        return code
    
    def _extract_simple_calls(self, code: str) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Fallback: extract simple function calls using regex when AST fails.
        Handles cases where LLM output isn't valid Python.
        """
        import re
        tool_calls = []
        
        # Pattern: func_name(args)
        pattern = r'(\w+)\s*\(([^)]*)\)'
        
        for match in re.finditer(pattern, code):
            func_name = match.group(1)
            args_str = match.group(2)
            
            if func_name not in self.ALLOWED_TOOLS:
                continue
            
            args = self._parse_args_string(func_name, args_str)
            tool_calls.append((func_name, args))
        
        return tool_calls
    
    def _parse_args_string(self, func_name: str, args_str: str) -> Dict[str, Any]:
        """Parse args string (when AST parsing failed)."""
        args = {}
        param_names = self._get_param_names(func_name)
        
        # Try JSON parse first (for dict args)
        args_str = args_str.strip()
        if args_str.startswith("{"):
            try:
                data = json.loads(args_str)
                if isinstance(data, dict):
                    return data
            except:
                pass
        
        # Try as positional string args
        # Simple split by comma (doesn't handle nested commas well)
        parts = self._split_args(args_str)
        for i, part in enumerate(parts):
            part = part.strip()
            if i < len(param_names):
                # Remove quotes if present
                if (part.startswith('"') and part.endswith('"')) or \
                   (part.startswith("'") and part.endswith("'")):
                    part = part[1:-1]
                args[param_names[i]] = part
        
        return args
    
    def _split_args(self, args_str: str) -> List[str]:
        """Split args string by comma, respecting brackets."""
        parts = []
        current = []
        depth = 0
        in_string = False
        string_char = None
        
        for char in args_str:
            if char in ('"', "'") and not in_string:
                in_string = True
                string_char = char
            elif char == string_char and in_string:
                in_string = False
            elif not in_string:
                if char in '([{':
                    depth += 1
                elif char in ')]}':
                    depth -= 1
                elif char == ',' and depth == 0:
                    parts.append(''.join(current))
                    current = []
                    continue
            
            current.append(char)
        
        if current:
            parts.append(''.join(current))
        
        return parts


# Create a singleton instance
parser = ToolCallParser()


def parse_tool_calls(code: str) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Convenience function to parse tool calls from code.
    
    Returns list of (tool_name, args) tuples.
    """
    return parser.parse(code)


__all__ = ["ToolCallParser", "parse_tool_calls"]
