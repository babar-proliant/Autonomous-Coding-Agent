"""
Metrics endpoint for Prometheus-style monitoring.
"""

import time
from typing import Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import threading

from backend.config import settings
from backend.utils import logger


@dataclass
class MetricValue:
    """A single metric value."""
    name: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    metric_type: str = "gauge"  # gauge, counter, histogram


class MetricsCollector:
    """
    Collects and exposes metrics for monitoring.
    
    Supports:
    - Counters (incrementing values)
    - Gauges (current values)
    - Histograms (distributions)
    """
    
    _instance: Optional['MetricsCollector'] = None
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
        
        self._metrics: Dict[str, MetricValue] = {}
        self._counters: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = {}
        self._start_time = time.time()
        self._initialized = True
        
        # Initialize default metrics
        self._init_default_metrics()
    
    def _init_default_metrics(self):
        """Initialize default system metrics."""
        # System info
        self.set_gauge("system_info", 1, {
            "version": settings.app_version,
            "debug": str(settings.debug)
        })
    
    def set_gauge(self, name: str, value: float, labels: Dict[str, str] = None):
        """Set a gauge metric value."""
        key = self._make_key(name, labels)
        self._metrics[key] = MetricValue(
            name=name,
            value=value,
            labels=labels or {},
            metric_type="gauge"
        )
    
    def increment_counter(self, name: str, amount: float = 1.0, labels: Dict[str, str] = None):
        """Increment a counter metric."""
        key = self._make_key(name, labels)
        
        if key not in self._counters:
            self._counters[key] = 0
        
        self._counters[key] += amount
        
        self._metrics[key] = MetricValue(
            name=name,
            value=self._counters[key],
            labels=labels or {},
            metric_type="counter"
        )
    
    def observe_histogram(self, name: str, value: float, labels: Dict[str, str] = None):
        """Observe a value for histogram metrics."""
        key = self._make_key(name, labels)
        
        if key not in self._histograms:
            self._histograms[key] = []
        
        self._histograms[key].append(value)
        
        # Keep only last 1000 observations
        if len(self._histograms[key]) > 1000:
            self._histograms[key] = self._histograms[key][-1000:]
    
    def _make_key(self, name: str, labels: Dict[str, str] = None) -> str:
        """Create a unique key for a metric."""
        if not labels:
            return name
        
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
    
    def get_metric(self, name: str) -> Optional[MetricValue]:
        """Get a specific metric."""
        return self._metrics.get(name)
    
    def get_all_metrics(self) -> List[MetricValue]:
        """Get all metrics."""
        return list(self._metrics.values())
    
    def get_histogram_summary(self, name: str, labels: Dict[str, str] = None) -> Dict[str, float]:
        """Get histogram summary statistics."""
        key = self._make_key(name, labels)
        
        if key not in self._histograms:
            return {}
        
        values = sorted(self._histograms[key])
        
        if not values:
            return {}
        
        n = len(values)
        
        return {
            "count": n,
            "sum": sum(values),
            "min": values[0],
            "max": values[-1],
            "p50": values[int(n * 0.5)] if n > 0 else 0,
            "p90": values[int(n * 0.9)] if n > 0 else 0,
            "p95": values[int(n * 0.95)] if n > 0 else 0,
            "p99": values[int(n * 0.99)] if n > 0 else 0,
        }
    
    def to_prometheus_format(self) -> str:
        """Export metrics in Prometheus text format."""
        lines = []
        
        # Add process info
        lines.append("# HELP agent_uptime_seconds Time since process started")
        lines.append("# TYPE agent_uptime_seconds gauge")
        lines.append(f"agent_uptime_seconds {time.time() - self._start_time}")
        lines.append("")
        
        # Export all metrics
        for key, metric in self._metrics.items():
            # Skip counters, they're handled separately
            if metric.metric_type == "counter" and key in self._counters:
                continue
            
            # Add help and type
            lines.append(f"# HELP {metric.name} {metric.name}")
            lines.append(f"# TYPE {metric.name} {metric.metric_type}")
            
            # Add metric value with labels
            if metric.labels:
                label_str = ",".join(f'{k}="{v}"' for k, v in metric.labels.items())
                lines.append(f"{metric.name}{{{label_str}}} {metric.value}")
            else:
                lines.append(f"{metric.name} {metric.value}")
            
            lines.append("")
        
        # Export counters
        for key, value in self._counters.items():
            metric = self._metrics.get(key)
            if metric:
                lines.append(f"# HELP {metric.name} {metric.name}")
                lines.append(f"# TYPE {metric.name} counter")
                
                if metric.labels:
                    label_str = ",".join(f'{k}="{v}"' for k, v in metric.labels.items())
                    lines.append(f"{metric.name}_total{{{label_str}}} {value}")
                else:
                    lines.append(f"{metric.name}_total {value}")
                
                lines.append("")
        
        # Export histogram summaries
        for key, values in self._histograms.items():
            if not values:
                continue
            
            metric = self._metrics.get(key)
            if not metric:
                continue
            
            summary = self.get_histogram_summary(metric.name, metric.labels)
            
            lines.append(f"# HELP {metric.name} {metric.name}")
            lines.append(f"# TYPE {metric.name} histogram")
            
            if metric.labels:
                label_str = ",".join(f'{k}="{v}"' for k, v in metric.labels.items())
                lines.append(f"{metric.name}_count{{{label_str}}} {summary.get('count', 0)}")
                lines.append(f"{metric.name}_sum{{{label_str}}} {summary.get('sum', 0):.2f}")
            else:
                lines.append(f"{metric.name}_count {summary.get('count', 0)}")
                lines.append(f"{metric.name}_sum {summary.get('sum', 0):.2f}")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def to_json(self) -> Dict[str, Any]:
        """Export metrics as JSON."""
        metrics = {}
        
        for key, metric in self._metrics.items():
            metrics[key] = {
                "name": metric.name,
                "value": metric.value,
                "labels": metric.labels,
                "type": metric.metric_type,
                "timestamp": metric.timestamp
            }
        
        # Add histogram summaries
        for key, values in self._histograms.items():
            if key in metrics:
                metrics[key]["histogram"] = self.get_histogram_summary(
                    self._metrics[key].name,
                    self._metrics[key].labels
                )
        
        return {
            "uptime_seconds": time.time() - self._start_time,
            "metrics": metrics
        }


# Global metrics collector
metrics = MetricsCollector()


# Convenience functions
def record_model_inference(model_name: str, duration_ms: int, tokens: int):
    """Record model inference metrics."""
    metrics.increment_counter("model_inferences_total", 1, {"model": model_name})
    metrics.observe_histogram("model_inference_duration_ms", duration_ms, {"model": model_name})
    metrics.observe_histogram("model_tokens_generated", tokens, {"model": model_name})


def record_tool_execution(tool_name: str, duration_ms: int, success: bool):
    """Record tool execution metrics."""
    metrics.increment_counter("tool_executions_total", 1, {
        "tool": tool_name,
        "status": "success" if success else "failure"
    })
    metrics.observe_histogram("tool_execution_duration_ms", duration_ms, {"tool": tool_name})


def record_session_event(event_type: str, session_id: str = None):
    """Record session events."""
    labels = {"event_type": event_type}
    if session_id:
        labels["session_id"] = session_id[:8]  # Truncate for cardinality
    
    metrics.increment_counter("session_events_total", 1, labels)


def update_system_metrics(cpu: float, memory: float, gpu_memory: float = None):
    """Update system resource metrics."""
    metrics.set_gauge("system_cpu_percent", cpu)
    metrics.set_gauge("system_memory_percent", memory)
    
    if gpu_memory is not None:
        metrics.set_gauge("system_gpu_memory_percent", gpu_memory)


__all__ = [
    "MetricsCollector",
    "MetricValue",
    "metrics",
    "record_model_inference",
    "record_tool_execution",
    "record_session_event",
    "update_system_metrics"
]
