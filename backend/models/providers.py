"""
Provider abstraction layer for LLM inference.
Supports multiple providers with fallback and retry logic.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, AsyncGenerator
from dataclasses import dataclass
from enum import Enum
import asyncio

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)
from backend.utils import logger, AgentLogger
from backend.config import settings


class ProviderType(str, Enum):
    """Types of LLM providers."""
    LLAMA_CPP = "llama_cpp"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    Z_AI = "z_ai"  # z-ai-web-dev-sdk


@dataclass
class InferenceResult:
    """Result of model inference."""
    text: str
    tokens_generated: int
    tokens_input: int
    inference_time_ms: int
    model_name: str
    provider: str
    finish_reason: str = "stop"


class ModelProvider(ABC):
    """Abstract base class for LLM providers."""
    
    name: str = "base"
    provider_type: ProviderType = ProviderType.LLAMA_CPP
    
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs
    ) -> InferenceResult:
        """Generate text completion."""
        pass
    
    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Generate text with streaming."""
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """Check if provider is available."""
        pass


class LlamaCppProvider(ModelProvider):
    """Provider using llama-cpp-python for local inference."""
    
    name = "llama_cpp"
    provider_type = ProviderType.LLAMA_CPP
    
    def __init__(self, model_path: str, gpu_layers: int = 35, context_window: int = 8192):
        self.model_path = model_path
        self.gpu_layers = gpu_layers
        self.context_window = context_window
        self._model = None
        self._logger = AgentLogger("LlamaCppProvider")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(Exception),
        before_sleep=before_sleep_log(logger, "WARNING"),
        reraise=True
    )
    async def _load_model(self):
        """Load model with retry logic."""
        if self._model is not None:
            return
        
        try:
            from llama_cpp import Llama
            
            def load_sync():
                return Llama(
                    model_path=self.model_path,
                    n_gpu_layers=self.gpu_layers,
                    n_ctx=self.context_window,
                    verbose=settings.debug
                )
            
            loop = asyncio.get_event_loop()
            self._model = await loop.run_in_executor(None, load_sync)
            self._logger.info(f"Model loaded: {self.model_path}")
            
        except Exception as e:
            self._logger.error(f"Failed to load model: {e}")
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception_type(Exception),
        before_sleep=before_sleep_log(logger, "WARNING")
    )
    async def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs
    ) -> InferenceResult:
        """Generate text with retry logic."""
        import time
        
        await self._load_model()
        
        start_time = time.time()
        
        def generate_sync():
            return self._model(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=kwargs.get('top_p', 0.9),
                top_k=kwargs.get('top_k', 40),
                echo=False,
                stream=False
            )
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, generate_sync)
        
        inference_time = int((time.time() - start_time) * 1000)
        
        return InferenceResult(
            text=result['choices'][0]['text'],
            tokens_generated=result['usage']['completion_tokens'],
            tokens_input=result['usage']['prompt_tokens'],
            inference_time_ms=inference_time,
            model_name=self.model_path.split('/')[-1],
            provider=self.name,
            finish_reason=result['choices'][0].get('finish_reason', 'stop')
        )
    
    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=4),
        retry=retry_if_exception_type(Exception)
    )
    async def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Generate text with streaming."""
        await self._load_model()
        
        def generate_stream_sync():
            return self._model(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=kwargs.get('top_p', 0.9),
                top_k=kwargs.get('top_k', 40),
                echo=False,
                stream=True
            )
        
        loop = asyncio.get_event_loop()
        stream = await loop.run_in_executor(None, generate_stream_sync)
        
        for chunk in stream:
            if 'content' in chunk['choices'][0]:
                yield chunk['choices'][0]['content']
    
    async def is_available(self) -> bool:
        """Check if llama-cpp-python is available."""
        try:
            from llama_cpp import Llama
            return True
        except ImportError:
            return False
    
    async def unload(self):
        """Unload model from memory."""
        if self._model:
            del self._model
            self._model = None
            
            import gc
            gc.collect()
            
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass


class ZAIProvider(ModelProvider):
    """Provider using z-ai-web-dev-sdk."""
    
    name = "z_ai"
    provider_type = ProviderType.Z_AI
    
    def __init__(self):
        self._logger = AgentLogger("ZAIProvider")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(Exception),
        before_sleep=before_sleep_log(logger, "WARNING")
    )
    async def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs
    ) -> InferenceResult:
        """Generate text using z-ai-web-dev-sdk."""
        import time
        
        try:
            from z_ai_web_dev_sdk import LLM
            
            start_time = time.time()
            
            response = await LLM.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model=kwargs.get("model", "default"),
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            inference_time = int((time.time() - start_time) * 1000)
            
            return InferenceResult(
                text=response.get("content", ""),
                tokens_generated=response.get("usage", {}).get("completion_tokens", 0),
                tokens_input=response.get("usage", {}).get("prompt_tokens", 0),
                inference_time_ms=inference_time,
                model_name=kwargs.get("model", "z-ai-default"),
                provider=self.name,
                finish_reason=response.get("finish_reason", "stop")
            )
            
        except Exception as e:
            self._logger.error(f"Z-AI generation failed: {e}")
            raise
    
    async def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Generate text with streaming using z-ai-web-dev-sdk."""
        try:
            from z_ai_web_dev_sdk import LLM
            
            async for chunk in LLM.chat_completion_stream(
                messages=[{"role": "user", "content": prompt}],
                model=kwargs.get("model", "default"),
                temperature=temperature,
                max_tokens=max_tokens
            ):
                if chunk:
                    yield chunk
                    
        except Exception as e:
            self._logger.error(f"Z-AI streaming failed: {e}")
            raise
    
    async def is_available(self) -> bool:
        """Check if z-ai-web-dev-sdk is available."""
        try:
            from z_ai_web_dev_sdk import LLM
            return True
        except ImportError:
            return False


class ProviderRegistry:
    """
    Registry for managing multiple LLM providers with fallback.
    """
    
    _instance: Optional['ProviderRegistry'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._providers: Dict[str, ModelProvider] = {}
        self._fallback_order: List[str] = []
        self._logger = AgentLogger("ProviderRegistry")
        self._initialized = True
    
    def register(self, provider: ModelProvider, alias: str = None):
        """Register a provider."""
        key = alias or provider.name
        self._providers[key] = provider
        if key not in self._fallback_order:
            self._fallback_order.append(key)
        self._logger.info(f"Registered provider: {key}")
    
    def set_fallback_order(self, order: List[str]):
        """Set the fallback order for providers."""
        self._fallback_order = [p for p in order if p in self._providers]
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(Exception),
        before_sleep=before_sleep_log(logger, "WARNING")
    )
    async def generate(
        self,
        prompt: str,
        provider_key: str = None,
        fallback: bool = True,
        **kwargs
    ) -> InferenceResult:
        """
        Generate text with automatic fallback.
        
        Args:
            prompt: Input prompt
            provider_key: Specific provider to use (None for auto-select)
            fallback: Whether to fallback to other providers on failure
            **kwargs: Additional generation parameters
        """
        providers_to_try = []
        
        if provider_key and provider_key in self._providers:
            providers_to_try = [provider_key]
        
        if fallback or not providers_to_try:
            providers_to_try = self._fallback_order
        
        last_error = None
        
        for key in providers_to_try:
            provider = self._providers.get(key)
            if not provider:
                continue
            
            # Check availability
            if not await provider.is_available():
                self._logger.warning(f"Provider {key} not available, skipping")
                continue
            
            try:
                self._logger.info(f"Trying provider: {key}")
                result = await provider.generate(prompt, **kwargs)
                result.provider = key
                return result
                
            except Exception as e:
                self._logger.warning(f"Provider {key} failed: {e}")
                last_error = e
                continue
        
        raise RuntimeError(
            f"All providers failed. Last error: {last_error}"
        )
    
    async def generate_stream(
        self,
        prompt: str,
        provider_key: str = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Generate text with streaming."""
        providers_to_try = [provider_key] if provider_key else self._fallback_order
        
        for key in providers_to_try:
            provider = self._providers.get(key)
            if not provider:
                continue
            
            if not await provider.is_available():
                continue
            
            try:
                async for chunk in provider.generate_stream(prompt, **kwargs):
                    yield chunk
                return
                
            except Exception as e:
                self._logger.warning(f"Provider {key} streaming failed: {e}")
                continue
        
        raise RuntimeError("All providers failed for streaming")
    
    def get_available_providers(self) -> List[str]:
        """Get list of registered providers."""
        return list(self._providers.keys())
    
    async def health_check(self) -> Dict[str, bool]:
        """Check health of all providers."""
        results = {}
        for key, provider in self._providers.items():
            try:
                results[key] = await provider.is_available()
            except:
                results[key] = False
        return results


# Global registry
provider_registry = ProviderRegistry()


__all__ = [
    "ModelProvider",
    "LlamaCppProvider",
    "ZAIProvider",
    "ProviderRegistry",
    "ProviderType",
    "InferenceResult",
    "provider_registry"
]
