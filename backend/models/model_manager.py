"""
Model management system for local LLM inference.
Handles model loading, unloading, and context preservation.
Single model architecture - Qwen 2.5 Coder for all tasks.
"""

import asyncio
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, AsyncGenerator
from dataclasses import dataclass
from enum import Enum
import json
import threading
import concurrent.futures
from backend.config import settings, MODELS_DIR
from backend.utils import logger, AgentLogger
from backend.memory.working_memory import WorkingMemory

_process_executor = None


class ModelRole(str, Enum):
    """Role/purpose of a model."""
    DEFAULT = "default"    # Single model for all tasks


class ModelState(str, Enum):
    """State of a model."""
    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    ERROR = "error"
    UNLOADING = "unloading"


@dataclass
class ModelConfig:
    """Configuration for a model."""
    name: str
    display_name: str
    file_path: Path
    gpu_layers: int
    context_window: int
    vram_usage_gb: float
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    max_tokens: int = 2048
    
    # HuggingFace download info
    huggingface_repo: str = ""
    huggingface_file: str = ""


@dataclass
class InferenceResult:
    """Result of model inference."""
    text: str
    tokens_generated: int
    tokens_input: int
    inference_time_ms: int
    model_name: str
    finish_reason: str = "stop"


class ModelManager:
    """
    Manages local LLM models with GPU memory optimization.
    
    Single model architecture - Qwen 2.5 Coder handles all tasks.
    """
    
    _instance: Optional['ModelManager'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        self._initialized = False
        self._models: Dict[str, Any] = {}  # Llama instances
        self._model_configs: Dict[str, ModelConfig] = {}
        self._model_states: Dict[str, ModelState] = {}
        self._model_locks: Dict[str, asyncio.Lock] = {}
        
        self.logger = AgentLogger("ModelManager")
        
        self._initialize_configs()
        self._initialized = True
    
    def _initialize_configs(self):
        """Initialize model configurations - Single model architecture."""
        # Single model - Qwen Coder
        model_config = ModelConfig(
            name="qwen-14b",
            display_name="Qwen 2.5 Coder 14B (Q4)",
            file_path=MODELS_DIR / settings.specialist_model_name,
            gpu_layers=settings.specialist_model_gpu_layers,
            context_window=settings.specialist_model_context_window,
            vram_usage_gb=9.0,
            temperature=0.6,
            top_p=0.95,
            top_k=40,
            max_tokens=4096,
            huggingface_repo="Qwen/Qwen2.5-Coder-14B-Instruct-GGUF",
            huggingface_file=settings.specialist_model_name
        )
        
        # Only ONE actual model storage with key "default"
        self._model_configs["default"] = model_config
        self._model_locks["default"] = asyncio.Lock()
        self._model_states["default"] = ModelState.UNLOADED
        
        # Aliases for backward compatibility (same config object)
        # These share the same config, but state/lock/models are accessed via "default"
        self._model_configs["specialist"] = model_config
        self._model_configs["base"] = model_config
    
    async def initialize(self):
        """Initialize the model manager and load the model."""
        self.logger.info("Initializing model manager...")
        
        # Ensure models directory exists
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        
        # Check and download model if needed
        await self._ensure_model_available("default")
        
        # Load the model
        await self.load_model("default")
        
        self.logger.info("Model manager initialized")
    
    async def _ensure_model_available(self, model_key: str):
        """Ensure model file is available, download if necessary."""
        config = self._model_configs.get(model_key)
        if not config:
            return
        
        if config.file_path.exists():
            self.logger.info(f"Model found: {config.file_path}")
            return
        
        if not settings.auto_download_models:
            raise FileNotFoundError(
                f"Model not found at {config.file_path} and auto-download is disabled"
            )
        
        # Download model
        self.logger.info(f"Downloading model: {config.display_name}")
        await self._download_model(config)
    
    async def _download_model(self, config: ModelConfig):
        """Download a model from HuggingFace."""
        try:
            from huggingface_hub import hf_hub_download
            
            def download():
                return hf_hub_download(
                    repo_id=config.huggingface_repo,
                    filename=config.huggingface_file,
                    local_dir=str(MODELS_DIR),
                    local_dir_use_symlinks=False
                )
            
            # Run download in executor
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, download)
            
            self.logger.info(f"Model downloaded: {config.file_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to download model: {e}")
            raise
    
    async def load_model(self, model_key: str) -> bool:
        """
        Load a model into GPU memory.
        
        All keys (base, specialist, default) resolve to the same model.
        
        Returns:
            True if successful
        """
        config = self._model_configs.get(model_key)
        if not config:
            self.logger.error(f"Unknown model: {model_key}")
            return False
        
        # All keys resolve to the same "default" model
        actual_key = "default"
        
        async with self._model_locks[actual_key]:
            if self._model_states[actual_key] == ModelState.LOADED:
                return True
            
            self._model_states[actual_key] = ModelState.LOADING
            self.logger.info(f"Loading model: {config.display_name}")
            
            try:
                # Import llama-cpp-python
                from llama_cpp import Llama
                
                # Check if model file exists
                if not config.file_path.exists():
                    await self._ensure_model_available(actual_key)
                
                # Load model in executor (blocking operation)
                def load():
                    return Llama(
                        model_path=str(config.file_path),
                        n_gpu_layers=config.gpu_layers,
                        n_ctx=config.context_window,
                        f16_kv=True,
                        verbose=settings.debug
                    )
                
                loop = asyncio.get_event_loop()
                model = await loop.run_in_executor(None, load)
                
                self._models[actual_key] = model
                self._model_states[actual_key] = ModelState.LOADED
                
                self.logger.info(f"Model loaded: {config.display_name}")
                
                return True
                
            except Exception as e:
                self._model_states[actual_key] = ModelState.ERROR
                self.logger.error(f"Failed to load model: {e}")
                return False
    
    async def unload_model(self, model_key: str) -> bool:
        """
        Unload the model from GPU memory.
        
        Returns:
            True if successful
        """
        actual_key = "default"
        
        async with self._model_locks[actual_key]:
            if self._model_states[actual_key] != ModelState.LOADED:
                return True
            
            self._model_states[actual_key] = ModelState.UNLOADING
            self.logger.info("Unloading model...")
            
            try:
                # Delete model instance
                if actual_key in self._models:
                    del self._models[actual_key]
                
                # Force garbage collection
                import gc
                gc.collect()
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except ImportError:
                    pass
                
                self._model_states[actual_key] = ModelState.UNLOADED
                
                self.logger.info("Model unloaded")
                return True
                
            except Exception as e:
                self._model_states[actual_key] = ModelState.ERROR
                self.logger.error(f"Failed to unload model: {e}")
                return False
    
    async def switch_specialist(self, model_key: str = "specialist") -> bool:
        """
        No-op for backward compatibility - we only have one model.
        """
        return await self.load_model("default")
    
    async def generate(
        self,
        prompt: str,
        model_key: str = "default",
        max_tokens: int = None,
        temperature: float = None,
        stream: bool = False,
        stop: List[str] = None,
        **kwargs
    ) -> InferenceResult:
        """Generate text from the model."""
        config = self._model_configs.get(model_key, self._model_configs["default"])
        
        max_tokens = max_tokens or config.max_tokens
        temperature = temperature if temperature is not None else config.temperature
        
        default_stop = ["<|eot_id|>", "<|end_of_text|>"]
        stop_tokens = stop or default_stop
        
        # Ensure model is loaded (always use "default")
        await self.load_model("default")
        
        model = self._models.get("default")
        if not model:
            raise RuntimeError("Model not loaded")
        
        start_time = time.time()
        
        try:
            loop = asyncio.get_event_loop()
            
            result = await loop.run_in_executor(
                None,
                lambda: model(
                    prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=kwargs.get('top_p', config.top_p),
                    top_k=kwargs.get('top_k', config.top_k),
                    stop=stop_tokens,
                    echo=False,
                    stream=False
                )
            )
            
            await asyncio.sleep(0)
            
            generated_text = result['choices'][0]['text']
            tokens_generated = result['usage']['completion_tokens']
            tokens_input = result['usage']['prompt_tokens']
            
            inference_time = int((time.time() - start_time) * 1000)
            
            return InferenceResult(
                text=generated_text,
                tokens_generated=tokens_generated,
                tokens_input=tokens_input,
                inference_time_ms=inference_time,
                model_name=config.display_name,
                finish_reason=result['choices'][0].get('finish_reason', 'stop')
            )
            
        except Exception as e:
            self.logger.error(f"Generation failed: {e}")
            raise
    
    async def generate_stream(
        self,
        prompt: str,
        model_key: str = "default",
        max_tokens: int = None,
        temperature: float = None,
        stop: List[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        Generate text with streaming output.
        
        Yields tokens one at a time in real-time.
        """
        config = self._model_configs.get(model_key, self._model_configs["default"])
        
        max_tokens = max_tokens or config.max_tokens
        temperature = temperature if temperature is not None else config.temperature
        default_stop = ["<|eot_id|>", "<|end_of_text|>"]
        stop_tokens = stop or default_stop
        
        # Ensure model is loaded (always use "default")
        await self.load_model("default")
        
        model = self._models.get("default")
        if not model:
            raise RuntimeError("Model not loaded")
        
        self.logger.info(f"Starting stream generation with {config.display_name}")
        
        queue = asyncio.Queue()
        loop = asyncio.get_event_loop()
        token_count = [0]
        error_holder = [None]
        
        def sync_generate():
            """Run in executor - puts tokens in queue."""
            try:
                stream = model(
                    prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=kwargs.get('top_p', config.top_p),
                    top_k=kwargs.get('top_k', config.top_k),
                    stop=stop_tokens,
                    echo=False,
                    stream=True
                )
                
                for chunk in stream:
                    delta = chunk['choices'][0]
                    text = None
                    if 'text' in delta and delta['text']:
                        text = delta['text']
                    elif 'content' in delta and delta['content']:
                        text = delta['content']
                    
                    if text:
                        token_count[0] += 1
                        loop.call_soon_threadsafe(queue.put_nowait, text)
                
                loop.call_soon_threadsafe(queue.put_nowait, None)
                
            except Exception as e:
                error_holder[0] = e
                loop.call_soon_threadsafe(queue.put_nowait, None)
        
        loop.run_in_executor(None, sync_generate)
        
        while True:
            token = await queue.get()
            
            if token is None:
                break
            
            yield token
        
        if error_holder[0]:
            self.logger.error(f"Streaming generation failed: {error_holder[0]}")
            raise error_holder[0]
        
        self.logger.info(f"Stream completed: {token_count[0]} tokens")
    
    def get_model_state(self, model_key: str) -> ModelState:
        """Get the current state of the model."""
        return self._model_states.get("default", ModelState.UNLOADED)
    
    def get_loaded_models(self) -> List[str]:
        """Get list of currently loaded models."""
        if self._model_states.get("default") == ModelState.LOADED:
            return ["default"]
        return []
    
    def get_vram_usage(self) -> Dict[str, float]:
        """Get estimated VRAM usage by model."""
        if self._model_states.get("default") == ModelState.LOADED:
            config = self._model_configs.get("default")
            if config:
                return {"default": config.vram_usage_gb}
        return {}
    
    async def shutdown(self):
        """Shutdown and unload the model."""
        self.logger.info("Shutting down model manager...")
        await self.unload_model("default")
        self.logger.info("Model manager shutdown complete")


# Global model manager instance
model_manager = ModelManager()


__all__ = [
    "ModelManager",
    "ModelConfig",
    "ModelState",
    "ModelRole",
    "InferenceResult",
    "model_manager"
]