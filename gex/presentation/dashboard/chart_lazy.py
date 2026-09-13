"""Sistema de lazy loading para optimizar performance de gráficos pesados.

Implementa lazy loading y memoización para gráficos complejos que no necesitan
cargarse inmediatamente, mejorando el tiempo de carga inicial de la aplicación.
"""

from functools import lru_cache, wraps
from typing import Callable, Any, Optional
import asyncio
from datetime import datetime, timedelta


def lazy_chart(generator_func: Callable) -> Callable:
    """Decorator para lazy loading de gráficos pesados.
    
    El gráfico solo se genera cuando se solicita explícitamente, no en el
    renderizado inicial del componente.
    """
    
    @wraps(generator_func)
    def wrapper(*args, **kwargs):
        # Retornar una función que genera el gráfico on-demand
        def generate_on_demand():
            return generator_func(*args, **kwargs)
        
        return generate_on_demand
    
    return wrapper


class ChartCache:
    """Cache inteligente para gráficos con TTL y invalidación."""
    
    def __init__(self, default_ttl: int = 300):  # 5 minutos default
        self.cache = {}
        self.default_ttl = default_ttl
    
    def get(
        self, 
        key: str, 
        generator: Callable,
        ttl: Optional[int] = None
    ) -> Any:
        """Obtener gráfico del cache o generarlo."""
        
        ttl = ttl or self.default_ttl
        current_time = datetime.now()
        
        # Verificar si existe y no ha expirado
        if key in self.cache:
            cached_data, timestamp = self.cache[key]
            if (current_time - timestamp).total_seconds() < ttl:
                return cached_data
        
        # Generar nuevo gráfico
        chart_data = generator()
        self.cache[key] = (chart_data, current_time)
        return chart_data
    
    def invalidate(self, key: Optional[str] = None) -> None:
        """Invalidar cache específico o completo."""
        if key:
            self.cache.pop(key, None)
        else:
            self.cache.clear()
    
    def cleanup_expired(self) -> int:
        """Limpiar entradas expiradas del cache."""
        current_time = datetime.now()
        expired_keys = []
        
        for key, (data, timestamp) in self.cache.items():
            if (current_time - timestamp).total_seconds() > self.default_ttl:
                expired_keys.append(key)
        
        for key in expired_keys:
            self.cache.pop(key, None)
        
        return len(expired_keys)


class AsyncChartLoader:
    """Cargador asíncrono de gráficos para operaciones pesadas."""
    
    def __init__(self):
        self.queue = asyncio.Queue()
        self.active_tasks = {}
    
    async def load_chart_async(
        self, 
        chart_id: str, 
        generator: Callable,
        priority: int = 0
    ) -> Any:
        """Cargar gráfico de forma asíncrona con prioridad."""
        
        task_key = f"{chart_id}_{priority}"
        
        # Si ya está cargando, esperar resultado
        if task_key in self.active_tasks:
            return await self.active_tasks[task_key]
        
        # Crear tarea asíncrona
        task = asyncio.create_task(self._execute_chart_generator(generator))
        self.active_tasks[task_key] = task
        
        try:
            result = await task
            return result
        finally:
            self.active_tasks.pop(task_key, None)
    
    async def _execute_chart_generator(self, generator: Callable) -> Any:
        """Ejecutar generador de gráfico en background."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, generator)
    
    def cancel_chart(self, chart_id: str) -> bool:
        """Cancelar carga de gráfico específico."""
        for task_key, task in list(self.active_tasks.items()):
            if chart_id in task_key:
                task.cancel()
                del self.active_tasks[task_key]
                return True
        return False


class ChartLoadingStrategy:
    """Estrategias de carga basadas en contexto."""
    
    @staticmethod
    def should_lazy_load(chart_type: str, user_context: dict) -> bool:
        """Determinar si un gráfico debe usar lazy loading."""
        
        # Gráficos pesados siempre lazy load
        heavy_charts = ["heatmap", "whale_tracker", "volatility_surface"]
        if chart_type in heavy_charts:
            return True
        
        # Lazy load si hay muchos gráficos en vista
        visible_charts = user_context.get("visible_charts", 0)
        if visible_charts > 5:
            return True
        
        # Lazy load en móvil
        if user_context.get("is_mobile", False):
            return True
        
        return False
    
    @staticmethod
    def get_priority(chart_type: str) -> int:
        """Obtener prioridad de carga para un tipo de gráfico."""
        
        priorities = {
            "main_exposure": 0,      # Más alta prioridad
            "time_series": 1,
            "heatmap": 2,           # Menor prioridad (pesado)
            "volatility": 2,
            "analytics": 1
        }
        
        return priorities.get(chart_type, 1)


# Instancia global del cache
chart_cache = ChartCache()
async_chart_loader = AsyncChartLoader()


def cached_chart(ttl: int = 300):
    """Decorator para cachear resultados de funciones de gráficos."""
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Crear key única basada en función y argumentos
            key = f"{func.__name__}_{str(args)}_{str(kwargs)}"
            return chart_cache.get(key, lambda: func(*args, **kwargs), ttl)
        return wrapper
    return decorator