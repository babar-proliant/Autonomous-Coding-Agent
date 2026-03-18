"""
API routes for the Autonomous Coding Agent.
"""

import asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from pathlib import Path
import json
import time

from backend.config import settings
from backend.core import event_bus, EventType
from backend.models import model_manager
from backend.agents.orchestrator import ChiefOrchestrator
from backend.agents.coder_agent import CoderAgent, PlannerAgent, ReviewerAgent, DebuggerAgent
from backend.memory.working_memory import WorkingMemory
from backend.utils import generate_id, logger


router = APIRouter()

# Active sessions
sessions: Dict[str, Dict[str, Any]] = {}


# ============================================
# REQUEST MODELS
# ============================================

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class SessionCreateRequest(BaseModel):
    project_name: Optional[str] = "Untitled Project"


class ToolExecuteRequest(BaseModel):
    tool_name: str
    parameters: Dict[str, Any]
    session_id: str


# ============================================
# SESSION MANAGEMENT
# ============================================

@router.post("/session/create")
async def create_session(request: SessionCreateRequest):
    """Create a new session."""
    session_id = generate_id()
    
    project_path = str(settings.workspace_dir / session_id)
    Path(project_path).mkdir(parents=True, exist_ok=True)
    
    sessions[session_id] = {
        "id": session_id,
        "project_name": request.project_name,
        "project_path": project_path,
        "status": "active",
        "working_memory": WorkingMemory(),
        "orchestrator": None
    }
    
    await event_bus.emit(
        EventType.SESSION_START,
        session_id,
        project_name=request.project_name,
        project_path=project_path
    )
    
    logger.info(f"Created session: {session_id}")
    
    return {
        "session_id": session_id,
        "project_path": project_path,
        "status": "created"
    }


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    """Get session information."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    
    return {
        "session_id": session_id,
        "project_name": session.get("project_name"),
        "project_path": session.get("project_path"),
        "status": session.get("status", "active")
    }


@router.delete("/session/{session_id}")
async def end_session(session_id: str):
    """End a session."""
    if session_id in sessions:
        sessions[session_id]["status"] = "ended"
        
        await event_bus.emit(
            EventType.SESSION_END,
            session_id,
            status="ended"
        )
        
        event_bus.clear_session(session_id)
        del sessions[session_id]
    
    return {"status": "ended", "session_id": session_id}


# ============================================
# CHAT INTERACTION
# ============================================

@router.post("/chat")
async def chat(request: ChatRequest, background_tasks: BackgroundTasks):
    """Send a message to the agent."""
    if request.session_id and request.session_id in sessions:
        session_id = request.session_id
        session = sessions[session_id]
    else:
        session_id = generate_id()
        project_path = str(settings.workspace_dir / session_id)
        Path(project_path).mkdir(parents=True, exist_ok=True)
        
        session = {
            "id": session_id,
            "project_name": "Chat Session",
            "project_path": project_path,
            "status": "active",
            "working_memory": WorkingMemory(),
            "orchestrator": None
        }
        sessions[session_id] = session
    
    await session["working_memory"].add(
        content=request.message,
        role="user",
        importance_score=0.8
    )
    
    background_tasks.add_task(
        process_message,
        session_id,
        request.message
    )
    
    return {
        "session_id": session_id,
        "status": "processing"
    }


async def process_message(session_id: str, message: str):
    """Process a user message (runs in background)."""
    try:
        session = sessions.get(session_id)
        if not session:
            return
        
        if not session.get("orchestrator"):
            orchestrator = ChiefOrchestrator(
                session_id=session_id,
                workspace_path=session["project_path"],
                working_memory=session["working_memory"]
            )
            
            orchestrator.register_agent(CoderAgent(
                session_id=session_id,
                workspace_path=session["project_path"],
                working_memory=session["working_memory"]
            ))
            orchestrator.register_agent(PlannerAgent(
                session_id=session_id,
                workspace_path=session["project_path"],
                working_memory=session["working_memory"]
            ))
            orchestrator.register_agent(ReviewerAgent(
                session_id=session_id,
                workspace_path=session["project_path"],
                working_memory=session["working_memory"]
            ))
            orchestrator.register_agent(DebuggerAgent(
                session_id=session_id,
                workspace_path=session["project_path"],
                working_memory=session["working_memory"]
            ))
            
            session["orchestrator"] = orchestrator
        
        orchestrator = session["orchestrator"]
        
        result = await orchestrator.execute(message)
        
        await session["working_memory"].add(
            content=result.content,
            role="agent",
            importance_score=0.7,
            metadata=result.metadata
        )
        
        await event_bus.emit(
            EventType.DONE,
            session_id,
            summary=result.content[:500]
        )
        
    except Exception as e:
        logger.exception(f"Error processing message: {e}")
        
        await event_bus.emit(
            EventType.ERROR,
            session_id,
            error=str(e),
            error_type=type(e).__name__
        )
        
        await event_bus.emit(
            EventType.DONE,
            session_id,
            status="error"
        )


# ============================================
# SSE STREAMING
# ============================================

@router.get("/events/{session_id}")
async def stream_events(session_id: str):
    """Stream events via SSE."""
    async def generate():
        yield f"event: connected\ndata: {{\"message\": \"Connected\"}}\n\n"
        
        async for event_str in event_bus.event_stream(session_id):
            yield event_str
            # Yield control to event loop for immediate flush
            await asyncio.sleep(0)
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        }
    )


# ============================================
# WORKSPACE OPERATIONS
# ============================================

@router.get("/workspace/{session_id}")
async def list_workspace(session_id: str, path: str = ""):
    """List files in the workspace."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    workspace_path = Path(sessions[session_id]["project_path"])
    target_path = workspace_path / path if path else workspace_path
    
    if not target_path.exists():
        return {"files": [], "path": str(path)}
    
    files = []
    for item in target_path.iterdir():
        files.append({
            "name": item.name,
            "path": str(item.relative_to(workspace_path)),
            "is_file": item.is_file(),
            "is_dir": item.is_dir(),
            "size": item.stat().st_size if item.is_file() else 0
        })
    
    return {
        "files": sorted(files, key=lambda x: (not x["is_dir"], x["name"])),
        "path": path
    }


@router.get("/file/{session_id}")
async def read_file(session_id: str, path: str):
    """Read a file from the workspace."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    workspace_path = Path(sessions[session_id]["project_path"])
    file_path = workspace_path / path
    
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        content = file_path.read_text(encoding='utf-8')
        return {
            "path": path,
            "content": content,
            "size": len(content)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# FILE UPLOAD
# ============================================

from fastapi import UploadFile, File, Form
import shutil
import os

@router.post("/upload/{session_id}")
async def upload_files(
    session_id: str,
    files: List[UploadFile] = File(...),
    base_path: str = Form(default="")
):
    """Upload files to the workspace."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    workspace_path = Path(sessions[session_id]["project_path"])
    upload_path = workspace_path / base_path if base_path else workspace_path
    
    # Ensure upload directory exists
    upload_path.mkdir(parents=True, exist_ok=True)
    
    uploaded_files = []
    errors = []
    
    for file in files:
        try:
            # Preserve directory structure if relative path is provided
            # The filename may contain path separators from webkitRelativePath
            file_path = file.filename
            if not file_path:
                continue
                
            # Sanitize path - remove any leading slashes and prevent traversal
            file_path = file_path.lstrip('/\\')
            
            # Create full target path
            target_path = upload_path / file_path
            
            # Ensure parent directories exist
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Security check - ensure path is within workspace
            try:
                target_path.resolve().relative_to(workspace_path.resolve())
            except ValueError:
                errors.append({
                    "file": file_path,
                    "error": "Path traversal attempt blocked"
                })
                continue
            
            # Write file
            with open(target_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            uploaded_files.append({
                "path": str(target_path.relative_to(workspace_path)),
                "size": target_path.stat().st_size
            })
            
        except Exception as e:
            errors.append({
                "file": file.filename,
                "error": str(e)
            })
        finally:
            await file.close()
    
    return {
        "session_id": session_id,
        "uploaded": uploaded_files,
        "errors": errors,
        "total_uploaded": len(uploaded_files),
        "total_errors": len(errors)
    }


# ============================================
# TOOLS
# ============================================

@router.get("/tools")
async def list_tools():
    """List all available tools."""
    from backend.tools import ToolRegistry
    return {
        "tools": ToolRegistry.get_all_schemas(),
        "categories": ToolRegistry.get_tools_by_category()
    }


@router.post("/tools/execute")
async def execute_tool(request: ToolExecuteRequest):
    """Execute a tool directly."""
    from backend.tools import ToolRegistry
    
    if request.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[request.session_id]
    
    tool = ToolRegistry.get_tool(
        request.tool_name,
        session_id=request.session_id,
        workspace_path=session["project_path"]
    )
    
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    result = await tool.run(**request.parameters)
    
    return result.to_dict()


# ============================================
# MODELS
# ============================================

@router.get("/models/status")
async def get_models_status():
    """Get status of loaded models."""
    return {
        "loaded_models": model_manager.get_loaded_models(),
        "model_states": {
            key: state.value 
            for key, state in model_manager._model_states.items()
        }
    }


# ============================================
# SYSTEM STATUS
# ============================================

@router.get("/health")
async def health_check():
    """Lightweight health check - returns immediately."""
    return {"status": "ok", "timestamp": time.time()}


@router.get("/status")
async def get_system_status():
    """Get overall system status."""
    import psutil
    import platform
    
    try:
        disk_path = 'C:\\' if platform.system() == 'Windows' else '/'
        
        return {
            "status": "operational",
            "active_sessions": len(sessions),
            "system": {
                "cpu_percent": psutil.cpu_percent(interval=0.0),  # Non-blocking
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage(disk_path).percent
            },
            "models": {
                "loaded": model_manager.get_loaded_models()
            }
        }
    except Exception as e:
        return {
            "status": "degraded",
            "error": str(e),
            "active_sessions": len(sessions)
        }


__all__ = ["router"]
