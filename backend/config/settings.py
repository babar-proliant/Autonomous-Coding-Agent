"""
Configuration settings for the Autonomous Coding Agent.
Uses Pydantic Settings for environment variable loading and validation.
"""
import torch
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from enum import Enum


# Base directories
BASE_DIR = Path(__file__).parent.parent.parent.absolute()
BACKEND_DIR = BASE_DIR / "backend"
# Use environment variable or default to data/models in project directory
MODELS_DIR = Path("E:\\models")
WORKSPACE_DIR = BASE_DIR / "workspaces" / "projects"
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # ============================================
    # APPLICATION SETTINGS
    # ============================================
    app_name: str = "Autonomous Coding Agent"
    app_version: str = "1.0.0"
    debug: bool = True
    log_level: LogLevel = LogLevel.INFO
    
    # ============================================
    # SERVER SETTINGS
    # ============================================
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    
    # ============================================
    # PATH SETTINGS
    # ============================================
    models_dir: Path = MODELS_DIR
    workspace_dir: Path = WORKSPACE_DIR
    data_dir: Path = DATA_DIR
    logs_dir: Path = LOGS_DIR
    
    # ============================================
    # MODEL SETTINGS
    # ============================================
    # Base model (always loaded)
    base_model_name: str = "mistral-7b-instruct-v0.2.Q4_K_M.gguf"
    base_model_gpu_layers: int = -1  # Full GPU offload for 7B
    base_model_context_window: int = 8192
    
    # Specialist model (load on demand)
    specialist_model_name: str = "qwen2.5-coder-14b-instruct-q4_k_m.gguf"
    specialist_model_gpu_layers: int = -1  # Full GPU offload for 14B
    specialist_model_context_window: int = 16384
    
    # Embedding model
    embedding_model_name: str = "all-MiniLM-L6-v2"
    
    # Model behavior
    model_temperature: float = 0.7
    model_top_p: float = 0.9
    model_top_k: int = 40
    model_max_tokens: int = 4096
    model_stream: bool = True
    
    # ============================================
    # GPU/VRAM SETTINGS
    # ============================================
    total_vram_gb: float = 16.0
    vram_buffer_gb: float = 1.5  # Reserved for system
    base_model_vram_gb: float = 4.5  # Mistral-7B Q4
    
    @property
    def available_vram_for_specialist(self) -> float:
        """Calculate available VRAM for specialist model."""
        return self.total_vram_gb - self.vram_buffer_gb - self.base_model_vram_gb
    
    # ============================================
    # MEMORY SETTINGS
    # ============================================
    working_memory_max_tokens: int = 12000
    context_window_threshold: float = 0.8  # Compress at 80% capacity
    max_message_history: int = 100
    importance_threshold: float = 0.3  # Min importance to keep in context
    
    # ============================================
    # PARALLELISM SETTINGS
    # ============================================
    max_parallel_agents: int = 2  # Based on GPU memory
    max_parallel_tools: int = 4   # CPU-bound operations
    max_terminal_processes: int = 3
    
    # ============================================
    # EXECUTION LIMITS
    # ============================================
    max_tool_execution_time: int = 1800  # 30 minutes per tool
    max_task_execution_time: int = 3600  # 1 hour per task
    max_command_output_size: int = 1024 * 1024  # 1MB
    max_file_read_size: int = 10 * 1024 * 1024  # 10MB
    
    # ============================================
    # RESOURCE LIMITS
    # ============================================
    max_cpu_percent: float = 80.0
    max_ram_percent: float = 75.0
    max_gpu_vram_percent: float = 90.0
    
    # ============================================
    # SAFETY SETTINGS
    # ============================================
    enable_command_filter: bool = True
    enable_path_guard: bool = True
    enable_resource_monitoring: bool = True
    
    # Operations requiring user confirmation
    confirmation_required_for: List[str] = [
        "delete_file",
        "delete_directory", 
        "execute_command_dangerous",
        "rollback_checkpoint",
        "git_force_push",
        "git_reset_hard",
    ]
    
    # Protected paths (cannot be modified)
    protected_paths: List[str] = [
        "/etc", "/sys", "/proc", "/dev",
        "/root", "/boot", "/lib", "/lib64",
        "/usr/bin", "/usr/sbin",
        "/System", "/Library",  # macOS
        "C:/Windows", "C:/Program Files",  # Windows
    ]
    
    # ============================================
    # DATABASE SETTINGS
    # ============================================
    database_path: Path = DATA_DIR / "memory.db"
    vector_db_path: Path = DATA_DIR / "vectors.db"
    
    # ============================================
    # CHECKPOINT SETTINGS
    # ============================================
    auto_checkpoint_interval: int = 300  # 5 minutes
    max_checkpoints_per_session: int = 20
    checkpoint_compression: bool = True
    
    # ============================================
    # WEB SEARCH SETTINGS
    # ============================================
    web_search_enabled: bool = True
    web_search_timeout: int = 30
    web_fetch_timeout: int = 30
    max_fetch_size: int = 5 * 1024 * 1024  # 5MB
    
    # ============================================
    # INDEXING SETTINGS
    # ============================================
    auto_index_uploaded_projects: bool = False  # Wait for user command
    index_file_patterns: List[str] = [
        "*.py", "*.js", "*.ts", "*.tsx", "*.jsx",
        "*.java", "*.go", "*.rs", "*.cpp", "*.c",
        "*.h", "*.hpp", "*.json", "*.yaml", "*.yml",
        "*.md", "*.txt", "*.toml", "*.ini", "*.cfg",
    ]
    index_skip_patterns: List[str] = [
        ".git", "node_modules", "__pycache__", ".venv", "venv",
        ".next", "dist", "build", "target", "*.pyc", "*.pyo",
        ".env", "*.log", "*.tmp", ".idea", ".vscode",
    ]
    
    # ============================================
    # API SETTINGS
    # ============================================
    api_prefix: str = "/api"
    sse_heartbeat_interval: int = 15  # seconds
    
    # ============================================
    # HUGGINGFACE SETTINGS (for model download)
    # ============================================
    huggingface_token: Optional[str] = None
    auto_download_models: bool = True
    
    # ============================================
    # EXTERNAL API KEYS (Future use)
    # ============================================
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    
    model_config = {
        "env_file": str(BASE_DIR / ".env"),
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
        "protected_namespaces": ()
    }
    
    @field_validator("models_dir", "workspace_dir", "data_dir", "logs_dir", mode="before")
    @classmethod
    def ensure_path(cls, v):
        """Convert string paths to Path objects."""
        if isinstance(v, str):
            return Path(v)
        return v
    
    def ensure_directories(self):
        """Create necessary directories if they don't exist."""
        for directory in [self.workspace_dir, self.data_dir, self.logs_dir, self.models_dir]:
            directory.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
