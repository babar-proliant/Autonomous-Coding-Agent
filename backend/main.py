"""
Main FastAPI application for the Autonomous Coding Agent.

This is the entry point for the backend server.
"""

import asyncio
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn


if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
# Add backend to path for imports
backend_path = Path(__file__).parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from backend.config import settings
from backend.utils import logger, setup_logging
from backend.models import model_manager
from backend.memory.database import db
from backend.api.routes import router
import backend.tools

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown.
    """
    # Startup
    logger.info("=" * 50)
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info("=" * 50)
    
    # Ensure directories exist
    settings.ensure_directories()
    
    # Initialize database
    await db.initialize()
    logger.info("Database initialized")
    
    # Initialize model manager (loads base model)
    try:
        await model_manager.initialize()
        logger.info("Model manager initialized")
    except Exception as e:
        logger.warning(f"Could not initialize model manager: {e}")
        logger.info("Server will start but models need to be loaded manually")
    
    logger.info(f"Server ready at http://{settings.host}:{settings.port}")
    logger.info("=" * 50)
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    
    # Shutdown model manager
    await model_manager.shutdown()
    
    # Close database
    await db.close()
    
    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Autonomous Coding Agent - World-Class Full-Stack AI Software Engineer",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Add both
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix=settings.api_prefix)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": settings.app_version
    }


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "api": settings.api_prefix
    }


def run_server():
    """Run the FastAPI server."""
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.value.lower()
    )


if __name__ == "__main__":
    run_server()
