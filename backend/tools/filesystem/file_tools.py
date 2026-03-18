"""File system tools for the Autonomous Coding Agent."""

from ..base_tool import BaseTool, ToolResult, ToolParameter, ToolRisk, ToolStatus, register_tool
from backend.utils import safe_path, ensure_directory
from backend.config import settings
from backend.utils import logger

import os
import aiofiles
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
import fnmatch


@register_tool
class ReadFileTool(BaseTool):
    """Tool for reading file contents."""
    
    name = "read_file"
    description = "Read the contents of a file"
    category = "filesystem"
    risk = ToolRisk.LOW
    timeout_seconds = 10
    
    parameters = [
        ToolParameter(
            name="file_path",
            type="string",
            description="Path to the file to read",
            required=True
        ),
        ToolParameter(
            name="encoding",
            type="string",
            description="File encoding",
            required=False,
            default="utf-8"
        )
    ]
    
    async def execute(self, **kwargs) -> ToolResult:
        file_path = kwargs["file_path"]
        encoding = kwargs.get("encoding", "utf-8")
        
        try:
            full_path = safe_path(file_path, self.workspace_path)
            
            if not full_path.exists():
                return ToolResult(
                    tool_name=self.name,
                    status=ToolStatus.FAILED,
                    error=f"File not found: {file_path}"
                )
            
            async with aiofiles.open(full_path, 'r', encoding=encoding) as f:
                content = await f.read()
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                result={
                    "content": content,
                    "file_path": str(full_path)
                },
                execution_time_ms=self._get_execution_time_ms()
            )
            
        except FileNotFoundError:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=f"File not found: {file_path}"
            )
        except PermissionError:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=f"Permission denied: {file_path}"
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(e)
            )


@register_tool
class WriteFileTool(BaseTool):
    """Tool for writing file contents."""
    
    name = "write_file"
    description = "Write content to a file (creates or overwrites)"
    category = "filesystem"
    risk = ToolRisk.MEDIUM
    timeout_seconds = 30
    
    parameters = [
        ToolParameter(
            name="file_path",
            type="string",
            description="Path to the file to write",
            required=True
        ),
        ToolParameter(
            name="content",
            type="string",
            description="Content to write to the file",
            required=True
        ),
        ToolParameter(
            name="create_dirs",
            type="boolean",
            description="Create parent directories if they don't exist",
            required=False,
            default=True
        )
    ]
    
    async def execute(self, **kwargs) -> ToolResult:
        file_path = kwargs["file_path"]
        content = kwargs["content"]
        create_dirs = kwargs.get("create_dirs", True)
        
        try:
            full_path = safe_path(file_path, self.workspace_path)
            
            if create_dirs:
                ensure_directory(full_path.parent)
            
            async with aiofiles.open(full_path, 'w', encoding='utf-8') as f:
                await f.write(content)
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                result={
                    "file_path": str(full_path),
                    "bytes_written": len(content.encode('utf-8')),
                    "lines_written": content.count('\n') + 1
                },
                execution_time_ms=self._get_execution_time_ms()
            )
            
        except PermissionError:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=f"Permission denied: {file_path}"
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(e)
            )


@register_tool
class EditFileTool(BaseTool):
    """Tool for editing files by replacing text."""
    
    name = "edit_file"
    description = "Edit a file by replacing specific text"
    category = "filesystem"
    risk = ToolRisk.MEDIUM
    timeout_seconds = 30
    
    parameters = [
        ToolParameter(
            name="file_path",
            type="string",
            description="Path to the file to edit",
            required=True
        ),
        ToolParameter(
            name="old_content",
            type="string",
            description="Text to replace (must match exactly)",
            required=True
        ),
        ToolParameter(
            name="new_content",
            type="string",
            description="New text to insert",
            required=True
        )
    ]
    
    async def execute(self, **kwargs) -> ToolResult:
        file_path = kwargs["file_path"]
        old_content = kwargs["old_content"]
        new_content = kwargs["new_content"]
        
        try:
            full_path = safe_path(file_path, self.workspace_path)
            
            async with aiofiles.open(full_path, 'r', encoding='utf-8') as f:
                content = await f.read()
            
            if old_content not in content:
                return ToolResult(
                    tool_name=self.name,
                    status=ToolStatus.FAILED,
                    error="Old content not found in file"
                )
            
            new_file_content = content.replace(old_content, new_content, 1)
            
            async with aiofiles.open(full_path, 'w', encoding='utf-8') as f:
                await f.write(new_file_content)
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                result={
                    "file_path": str(full_path),
                    "replacements_made": 1
                },
                execution_time_ms=self._get_execution_time_ms()
            )
            
        except FileNotFoundError:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=f"File not found: {file_path}"
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(e)
            )


@register_tool
class DeleteFileTool(BaseTool):
    """Tool for deleting files."""
    
    name = "delete_file"
    description = "Delete a file"
    category = "filesystem"
    risk = ToolRisk.HIGH
    requires_confirmation = True
    timeout_seconds = 10
    
    parameters = [
        ToolParameter(
            name="file_path",
            type="string",
            description="Path to the file to delete",
            required=True
        )
    ]
    
    async def execute(self, **kwargs) -> ToolResult:
        file_path = kwargs["file_path"]
        
        try:
            full_path = safe_path(file_path, self.workspace_path)
            
            if not full_path.exists():
                return ToolResult(
                    tool_name=self.name,
                    status=ToolStatus.FAILED,
                    error=f"File not found: {file_path}"
                )
            
            full_path.unlink()
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                result={
                    "file_path": str(full_path),
                    "deleted": True
                },
                execution_time_ms=self._get_execution_time_ms()
            )
            
        except PermissionError:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=f"Permission denied: {file_path}"
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(e)
            )


@register_tool
class ListDirectoryTool(BaseTool):
    """Tool for listing directory contents."""
    
    name = "list_directory"
    description = "List contents of a directory"
    category = "filesystem"
    risk = ToolRisk.LOW
    timeout_seconds = 10
    
    parameters = [
        ToolParameter(
            name="dir_path",
            type="string",
            description="Path to the directory to list (default: workspace root)",
            required=False,
            default="."
        ),
        ToolParameter(
            name="show_hidden",
            type="boolean",
            description="Show hidden files (starting with .)",
            required=False,
            default=False
        )
    ]
    
    async def execute(self, **kwargs) -> ToolResult:
        # Default to current directory if not provided
        dir_path = kwargs.get("dir_path", ".") or "."
        show_hidden = kwargs.get("show_hidden", False)
        
        try:
            full_path = safe_path(dir_path, self.workspace_path)
            
            if not full_path.is_dir():
                return ToolResult(
                    tool_name=self.name,
                    status=ToolStatus.FAILED,
                    error=f"Not a directory: {dir_path}"
                )
            
            entries = []
            for entry in full_path.iterdir():
                # Skip hidden files unless explicitly requested
                if not show_hidden and entry.name.startswith('.'):
                    continue
                
                # Always skip common VCS and cache directories
                if entry.is_dir() and entry.name in ['.git', '.svn', '__pycache__', 'node_modules']:
                    continue
                    
                entry_info = {
                    "name": entry.name,
                    "path": str(entry.relative_to(full_path)),
                    "full_path": str(entry.relative_to(self.workspace_path)) if entry.is_relative_to(self.workspace_path) else entry.name,
                    "is_file": entry.is_file(),
                    "is_dir": entry.is_dir(),
                }
                
                if entry.is_file():
                    try:
                        stat = entry.stat()
                        entry_info["size"] = stat.st_size
                    except:
                        pass
                
                entries.append(entry_info)
            
            # Sort: directories first, then files, alphabetically
            entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                result={
                    "dir_path": str(full_path),
                    "relative_path": dir_path,
                    "entries": entries,
                    "total_count": len(entries)
                },
                execution_time_ms=self._get_execution_time_ms()
            )
            
        except FileNotFoundError:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=f"Directory not found: {dir_path}"
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(e)
            )


@register_tool
class CreateDirectoryTool(BaseTool):
    """Tool for creating directories."""
    
    name = "create_directory"
    description = "Create a directory (and parent directories)"
    category = "filesystem"
    risk = ToolRisk.LOW
    timeout_seconds = 10
    
    parameters = [
        ToolParameter(
            name="dir_path",
            type="string",
            description="Path of the directory to create",
            required=True
        )
    ]
    
    async def execute(self, **kwargs) -> ToolResult:
        dir_path = kwargs["dir_path"]
        
        try:
            full_path = safe_path(dir_path, self.workspace_path)
            full_path.mkdir(parents=True, exist_ok=True)
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                result={
                    "dir_path": str(full_path),
                    "created": True
                },
                execution_time_ms=self._get_execution_time_ms()
            )
            
        except PermissionError:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=f"Permission denied: {dir_path}"
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(e)
            )


@register_tool
class SearchFilesTool(BaseTool):
    """Tool for searching files by content."""
    
    name = "search_files"
    description = "Search for text pattern in files"
    category = "filesystem"
    risk = ToolRisk.LOW
    timeout_seconds = 60
    
    parameters = [
        ToolParameter(
            name="pattern",
            type="string",
            description="Text pattern to search for",
            required=True
        ),
        ToolParameter(
            name="directory",
            type="string",
            description="Directory to search in",
            required=False,
            default="."
        )
    ]
    
    async def execute(self, **kwargs) -> ToolResult:
        pattern = kwargs["pattern"]
        directory = kwargs.get("directory", ".")
        
        try:
            full_path = safe_path(directory, self.workspace_path)
            
            if not full_path.is_dir():
                full_path = full_path.parent
            
            results = []
            
            for root, dirs, files in os.walk(full_path):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in 
                          ['node_modules', '__pycache__', 'venv', '.venv', 'dist', 'build']]
                
                for file_name in files:
                    file_path = Path(root) / file_name
                    
                    if file_path.suffix.lower() in ['.pyc', '.pyo', '.so', '.dll', '.exe', '.bin']:
                        continue
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            for line_num, line in enumerate(f, 1):
                                if pattern in line:
                                    results.append({
                                        "file_path": str(file_path.relative_to(full_path)),
                                        "line_number": line_num,
                                        "line_content": line.strip()[:200]
                                    })
                    except:
                        continue
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                result={
                    "pattern": pattern,
                    "directory": str(full_path),
                    "matches": results[:100],
                    "total_matches": len(results)
                },
                execution_time_ms=self._get_execution_time_ms()
            )
            
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(e)
            )


@register_tool
class FindFileTool(BaseTool):
    """Tool for finding files by name pattern."""
    
    name = "find_file"
    description = "Find files by name pattern (supports wildcards like *.py, desktop.ini, etc.)"
    category = "filesystem"
    risk = ToolRisk.LOW
    timeout_seconds = 30
    
    parameters = [
        ToolParameter(
            name="pattern",
            type="string",
            description="File name pattern to search for (supports wildcards: *.py, desktop.ini, test*)",
            required=True
        ),
        ToolParameter(
            name="directory",
            type="string",
            description="Directory to search in (default: workspace root)",
            required=False,
            default="."
        )
    ]
    
    async def execute(self, **kwargs) -> ToolResult:
        pattern = kwargs["pattern"]
        directory = kwargs.get("directory", ".")
        
        try:
            full_path = safe_path(directory, self.workspace_path)
            
            if not full_path.is_dir():
                full_path = full_path.parent if full_path.parent.exists() else self.workspace_path
            
            results = []
            
            for root, dirs, files in os.walk(full_path):
                # Skip hidden and common exclusion directories
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in 
                          ['node_modules', '__pycache__', 'venv', '.venv', 'dist', 'build', '.git']]
                
                for file_name in files:
                    # Match using fnmatch for wildcard support
                    if fnmatch.fnmatch(file_name.lower(), pattern.lower()):
                        file_path = Path(root) / file_name
                        relative_path = file_path.relative_to(self.workspace_path)
                        
                        results.append({
                            "name": file_name,
                            "path": str(relative_path),
                            "size": file_path.stat().st_size if file_path.exists() else 0
                        })
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                result={
                    "pattern": pattern,
                    "directory": str(full_path),
                    "files": results[:50],  # Limit to 50 results
                    "total_matches": len(results)
                },
                execution_time_ms=self._get_execution_time_ms()
            )
            
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(e)
            )


@register_tool
class ListAllFilesTool(BaseTool):
    """Tool for listing all files in workspace recursively."""
    
    name = "list_all_files"
    description = "List all files in the workspace recursively (use this to discover uploaded files)"
    category = "filesystem"
    risk = ToolRisk.LOW
    timeout_seconds = 30
    
    parameters = [
        ToolParameter(
            name="extension",
            type="string",
            description="Filter by file extension (e.g., 'py', 'js', 'ini'). Optional.",
            required=False,
            default=""
        )
    ]
    
    async def execute(self, **kwargs) -> ToolResult:
        extension = kwargs.get("extension", "").lower().lstrip('.')
        
        try:
            results = []
            
            for root, dirs, files in os.walk(self.workspace_path):
                # Skip hidden and common exclusion directories
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in 
                          ['node_modules', '__pycache__', 'venv', '.venv', 'dist', 'build', '.git']]
                
                for file_name in files:
                    # Filter by extension if provided
                    if extension:
                        if not file_name.lower().endswith(f'.{extension}'):
                            continue
                    
                    file_path = Path(root) / file_name
                    relative_path = file_path.relative_to(self.workspace_path)
                    
                    results.append({
                        "name": file_name,
                        "path": str(relative_path),
                        "size": file_path.stat().st_size if file_path.exists() else 0
                    })
            
            # Sort by path
            results.sort(key=lambda x: x["path"])
            
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                result={
                    "total_files": len(results),
                    "files": results[:100],  # Limit to 100 results
                    "truncated": len(results) > 100
                },
                execution_time_ms=self._get_execution_time_ms()
            )
            
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.FAILED,
                error=str(e)
            )


__all__ = [
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool",
    "DeleteFileTool",
    "ListDirectoryTool",
    "CreateDirectoryTool",
    "SearchFilesTool",
    "FindFileTool",
    "ListAllFilesTool"
]
