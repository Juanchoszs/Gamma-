"""Sistema de optimización de performance para gráficos Plotly.

Implementa técnicas de optimización como downsampling inteligente, 
chunking de datos, y precomputación para mejorar el rendimiento.
"""

import numpy as np
import pandas as pd
from typing import Tuple, List, Optional
from functools import lru_cache


class ChartOptimizer:
    """Optimizador de datos para gráficos de alto rendimiento."""
    
    # Configuración de downsampling
    MAX_POINTS = 1000  # Máximo de puntos por serie
    MIN_POINTS = 50     # Mínimo de puntos para downsampling
    
    @staticmethod
    def downsample_time_series(
        df: pd.DataFrame,
        time_column: str = "timestamp",
        max_points: int = MAX_POINTS
    ) -> pd.DataFrame:
        """Downsample series temporales manteniendo puntos clave."""
        
        if len(df) <= max_points:
            return df
        
        # Estrategia LTTB (Largest-Triangle-Three-Buckets) simplificada
        # Mantiene picos, valles y tendencias importantes
        if len(df) > max_points * 2:
            # Para datasets muy grandes, usar downsampling agresivo
            step = len(df) // max_points
            return df.iloc[::step].copy()
        
        # Para datasets medianos, usar LTTB básico
        return ChartOptimizer._lttb_downsample(df, time_column, max_points)
    
    @staticmethod
    def _lttb_downsample(
        df: pd.DataFrame,
        time_column: str,
        max_points: int
    ) -> pd.DataFrame:
        """Implementación simplificada de LTTB downsampling."""
        
        n = len(df)
        if n <= max_points:
            return df
        
        # Calcular bucket size
        bucket_size = n // max_points
        
        # Seleccionar: primer punto, un punto por bucket, último punto
        selected_indices = [0]
        
        for i in range(1, max_points - 1):
            bucket_start = i * bucket_size
            bucket_end = min((i + 1) * bucket_size, n)
            
            if bucket_start >= n:
                break
            
            bucket = df.iloc[bucket_start:bucket_end]
            
            # Seleccionar punto con mayor "área de triángulo"
            # (simplificado: punto extremo en bucket)
            if len(bucket) > 0:
                # Encontrar punto con mayor distancia visual
                if time_column in df.columns:
                    sorted_bucket = bucket.sort_values(time_column)
                    # Tomar punto medio para consistencia
                    mid_idx = len(sorted_bucket) // 2
                    selected_indices.append(sorted_bucket.index[mid_idx])
                else:
                    selected_indices.append(bucket.index[len(bucket) // 2])
        
        selected_indices.append(df.index[-1])
        
        return df.loc[selected_indices].copy()
    
    @staticmethod
    def optimize_numeric_column(series: pd.Series) -> pd.Series:
        """Optimizar representación de columnas numéricas."""
        
        # Convertir a tipo numérico óptimo
        if series.dtype == 'object':
            series = pd.to_numeric(series, errors='coerce')
        
        # Usar float32 en lugar de float64 para ahorrar memoria
        if series.dtype == 'float64':
            series = series.astype('float32')
        
        return series
    
    @staticmethod
    def chunk_large_data(
        data: pd.DataFrame,
        chunk_size: int = 10000
    ) -> List[pd.DataFrame]:
        """Dividir dataset grande en chunks procesables."""
        
        if len(data) <= chunk_size:
            return [data]
        
        chunks = []
        for i in range(0, len(data), chunk_size):
            chunk = data.iloc[i:i + chunk_size].copy()
            chunks.append(chunk)
        
        return chunks
    
    @staticmethod
    def precompute_aggregations(
        df: pd.DataFrame,
        group_columns: List[str],
        agg_columns: List[str],
        agg_funcs: List[str] = ['mean', 'std', 'min', 'max']
    ) -> pd.DataFrame:
        """Precomputar agregaciones comunes para performance."""
        
        try:
            return df.groupby(group_columns)[agg_columns].agg(agg_funcs)
        except Exception:
            # Fallback si agrupación falla
            return df


class ChartMemoryManager:
    """Gestor de memoria para gráficos complejos."""
    
    # Límites de memoria
    MAX_SERIES_PER_CHART = 10
    MAX_ANNOTATIONS = 20
    MAX_SHAPES = 15
    
    @staticmethod
    def estimate_series_memory(series_length: int, dtype: str = 'float64') -> int:
        """Estimar uso de memoria de una serie en bytes."""
        
        dtype_sizes = {
            'float64': 8,
            'float32': 4,
            'int64': 8,
            'int32': 4,
            'object': 50  # Estimación conservadora
        }
        
        return series_length * dtype_sizes.get(dtype, 8)
    
    @staticmethod
    def check_memory_feasibility(
        num_series: int,
        avg_length: int,
        dtype: str = 'float64'
    ) -> Tuple[bool, str]:
        """Verificar si gráfico es factible con límites de memoria."""
        
        if num_series > ChartMemoryManager.MAX_SERIES_PER_CHART:
            return False, f"Too many series ({num_series} > {ChartMemoryManager.MAX_SERIES_PER_CHART})"
        
        estimated_memory = ChartMemoryManager.estimate_series_memory(
            avg_length, dtype
        ) * num_series
        
        # Límite conservador de 50MB por gráfico
        if estimated_memory > 50 * 1024 * 1024:
            return False, f"Estimated memory usage too high: {estimated_memory / (1024*1024):.1f}MB"
        
        return True, "Memory usage acceptable"


class ChartPerformanceProfiler:
    """Profiler para identificar cuellos de botella en gráficos."""
    
    def __init__(self):
        self.metrics = {}
    
    def profile_chart_generation(
        self, 
        chart_id: str,
        generator_func: callable
    ) -> dict:
        """Profilear generación de gráfico y retornar métricas."""
        
        import time
        import tracemalloc
        
        # Iniciar tracking
        tracemalloc.start()
        start_time = time.time()
        
        # Generar gráfico
        result = generator_func()
        
        # Capturar métricas
        end_time = time.time()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        metrics = {
            "chart_id": chart_id,
            "generation_time_ms": (end_time - start_time) * 1000,
            "memory_usage_kb": current / 1024,
            "peak_memory_kb": peak / 1024,
            "timestamp": time.time()
        }
        
        self.metrics[chart_id] = metrics
        return metrics
    
    def get_slow_charts(self, threshold_ms: float = 1000) -> List[str]:
        """Identificar gráficos lentos según umbral."""
        
        return [
            chart_id for chart_id, metrics in self.metrics.items()
            if metrics["generation_time_ms"] > threshold_ms
        ]
    
    def get_memory_intensive_charts(self, threshold_kb: float = 10000) -> List[str]:
        """Identificar gráficos intensivos en memoria."""
        
        return [
            chart_id for chart_id, metrics in self.metrics.items()
            if metrics["peak_memory_kb"] > threshold_kb
        ]


# Instancias globales
chart_optimizer = ChartOptimizer()
memory_manager = ChartMemoryManager()
performance_profiler = ChartPerformanceProfiler()


def optimize_chart_data(df: pd.DataFrame, chart_type: str = "time_series") -> pd.DataFrame:
    """Función helper para optimizar datos de gráfico según tipo."""
    
    # Optimizar tipos numéricos
    for col in df.select_dtypes(include=['number']).columns:
        df[col] = chart_optimizer.optimize_numeric_column(df[col])
    
    # Aplicar downsampling según tipo
    if chart_type == "time_series":
        time_col = df.select_dtypes(include=['datetime']).columns[0] if len(df.select_dtypes(include=['datetime']).columns) > 0 else df.columns[0]
        df = chart_optimizer.downsample_time_series(df, time_col)
    
    return df