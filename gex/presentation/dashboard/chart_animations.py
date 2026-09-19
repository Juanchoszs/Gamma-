"""Sistema de animaciones sofisticadas para gráficos Plotly institucionales.

Implementa un motor de animaciones robusto con:
- Transiciones fluidas entre estados de datos
- Animaciones de entrada progresivas 
- Micro-interacciones con feedback visual
- Configuración flexible y performance optimizado
- Integración perfecta con ChartBuilder existente
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Union
from enum import Enum
import numpy as np
import plotly.graph_objects as go
from functools import lru_cache


class AnimationEasing(Enum):
    """Funciones de easing para animaciones suaves y naturales."""
    
    LINEAR = "linear"
    EASE_IN = "ease-in"
    EASE_OUT = "ease-out"
    EASE_IN_OUT = "ease-in-out"
    CUBIC_IN = "cubic-in"
    CUBIC_OUT = "cubic-out"
    CUBIC_IN_OUT = "cubic-in-out"
    ELASTIC_IN = "elastic-in"
    ELASTIC_OUT = "elastic-out"
    BOUNCE_IN = "bounce-in"
    BOUNCE_OUT = "bounce-out"


class AnimationType(Enum):
    """Tipos de animaciones disponibles."""
    
    # Animaciones de entrada
    FADE_IN = "fade_in"
    SLIDE_UP = "slide_up"
    SLIDE_DOWN = "slide_down"
    SLIDE_LEFT = "slide_left"
    SLIDE_RIGHT = "slide_right"
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    
    # Animaciones de transición
    MORPH = "morph"
    CROSSFADE = "crossfade"
    SEQUENTIAL = "sequential"
    
    # Animaciones de interacción
    HIGHLIGHT = "highlight"
    PULSE = "pulse"
    SHAKE = "shake"
    GLOW = "glow"


@dataclass
class AnimationConfig:
    """Configuración de animación individual."""
    
    animation_type: AnimationType
    duration_ms: int = 300
    easing: AnimationEasing = AnimationEasing.CUBIC_IN_OUT
    delay_ms: int = 0
    repeat: bool = False
    repeat_count: int = 1
    
    # Configuración específica por tipo
    from_opacity: float = 0.0
    to_opacity: float = 1.0
    from_scale: float = 0.8
    to_scale: float = 1.0
    from_position: Optional[Dict[str, float]] = None
    to_position: Optional[Dict[str, float]] = None
    
    def validate(self) -> bool:
        """Validar configuración de animación."""
        if self.duration_ms < 0:
            return False
        if self.delay_ms < 0:
            return False
        if self.repeat_count < 1:
            return False
        if not (0.0 <= self.from_opacity <= 1.0):
            return False
        if not (0.0 <= self.to_opacity <= 1.0):
            return False
        if self.from_scale <= 0:
            return False
        if self.to_scale <= 0:
            return False
        return True


@dataclass
class AnimationSequence:
    """Secuencia de animaciones coordinadas."""
    
    name: str
    animations: List[AnimationConfig] = field(default_factory=list)
    parallel: bool = False  # Si True, animaciones ejecutan en paralelo
    loop: bool = False  # Si True, secuencia se repite indefinidamente
    
    def add_animation(self, animation: AnimationConfig) -> 'AnimationSequence':
        """Añadir animación a la secuencia."""
        if animation.validate():
            self.animations.append(animation)
        return self
    
    def get_total_duration(self) -> int:
        """Calcular duración total de la secuencia."""
        if not self.animations:
            return 0
        
        if self.parallel:
            # Duración máxima entre animaciones
            return max(
                anim.duration_ms + anim.delay_ms 
                for anim in self.animations
            )
        else:
            # Suma de duraciones si son secuenciales
            return sum(
                anim.duration_ms + anim.delay_ms 
                for anim in self.animations
            )


@dataclass 
class ChartAnimationState:
    """Estado de animación para un gráfico específico."""
    
    chart_id: str
    current_sequence: Optional[str] = None
    is_animating: bool = False
    progress: float = 0.0  # 0.0 a 1.0
    last_update: Optional[float] = None


class AnimationPresets:
    """Presets de animaciones optimizadas para diferentes casos de uso."""
    
    @staticmethod
    def subtle_fade_in() -> AnimationConfig:
        """Fade in sutil y elegante."""
        return AnimationConfig(
            animation_type=AnimationType.FADE_IN,
            duration_ms=400,
            easing=AnimationEasing.CUBIC_OUT,
            from_opacity=0.0,
            to_opacity=1.0
        )
    
    @staticmethod
    def smooth_scale_up() -> AnimationConfig:
        """Scale up suave."""
        return AnimationConfig(
            animation_type=AnimationType.SCALE_UP,
            duration_ms=350,
            easing=AnimationEasing.CUBIC_OUT,
            from_scale=0.85,
            to_scale=1.0
        )
    
    @staticmethod
    def professional_slide_up() -> AnimationConfig:
        """Slide up profesional."""
        return AnimationConfig(
            animation_type=AnimationType.SLIDE_UP,
            duration_ms=450,
            easing=AnimationEasing.CUBIC_IN_OUT,
            from_position={"y": -20},
            to_position={"y": 0}
        )
    
    @staticmethod
    def data_transition() -> AnimationConfig:
        """Transición suave entre datos."""
        return AnimationConfig(
            animation_type=AnimationType.MORPH,
            duration_ms=600,
            easing=AnimationEasing.CUBIC_IN_OUT
        )
    
    @staticmethod
    def highlight_effect() -> AnimationConfig:
        """Efecto de highlight interactivo."""
        return AnimationConfig(
            animation_type=AnimationType.HIGHLIGHT,
            duration_ms=200,
            easing=AnimationEasing.CUBIC_OUT
        )
    
    @staticmethod
    def pulse_subtle() -> AnimationConfig:
        """Pulse sutil para llamar atención."""
        return AnimationConfig(
            animation_type=AnimationType.PULSE,
            duration_ms=800,
            easing=AnimationEasing.CUBIC_IN_OUT,
            repeat=True,
            repeat_count=2
        )
    
    @staticmethod
    def entry_sequence() -> AnimationSequence:
        """Secuencia de entrada completa para gráficos."""
        seq = AnimationSequence(name="entry", parallel=False)
        seq.add_animation(AnimationPresets.subtle_fade_in())
        seq.add_animation(AnimationPresets.smooth_scale_up())
        return seq


class AnimationEngine:
    """Motor principal de animaciones para gráficos Plotly."""
    
    def __init__(self):
        self.sequences: Dict[str, AnimationSequence] = {}
        self.states: Dict[str, ChartAnimationState] = {}
        self.global_enabled = True
        self.global_duration_multiplier = 1.0
        
    def register_sequence(self, sequence: AnimationSequence) -> None:
        """Registrar una secuencia de animación."""
        if sequence.animations:
            self.sequences[sequence.name] = sequence
    
    def get_sequence(self, name: str) -> Optional[AnimationSequence]:
        """Obtener secuencia por nombre."""
        return self.sequences.get(name)
    
    def set_global_enabled(self, enabled: bool) -> None:
        """Habilitar/deshabilitar animaciones globalmente."""
        self.global_enabled = enabled
    
    def set_duration_multiplier(self, multiplier: float) -> None:
        """Ajustar velocidad global de animaciones."""
        if multiplier > 0:
            self.global_duration_multiplier = multiplier
    
    def apply_animation_to_trace(
        self,
        trace: go.BaseTraceType,
        config: AnimationConfig,
        frame_index: int = 0
    ) -> go.BaseTraceType:
        """Aplicar configuración de animación a un trace Plotly.
        
        Nota: Plotly maneja animaciones principalmente a través de frames
        y configuración de layout, no a nivel de trace individual.
        Este método aplica efectos directos cuando es posible.
        """
        
        if not self.global_enabled or not config.validate():
            return trace
        
        # Aplicar configuración según tipo de animación
        if config.animation_type == AnimationType.FADE_IN:
            # Fade se aplica directamente al opacity
            trace.opacity = config.to_opacity
        
        elif config.animation_type == AnimationType.SCALE_UP:
            # Scale se aplica diferente según el tipo de trace
            if hasattr(trace, 'marker'):
                # Para scatter y otros traces con marker.size
                if hasattr(trace.marker, 'size'):
                    current_size = getattr(trace.marker, 'size', None)
                    if current_size is None:
                        current_size = 6
                    trace.update(marker=dict(size=current_size * config.to_scale))
                # Para bar traces que no tienen size pero tienen otras propiedades
                else:
                    # Para bars, scale puede aplicarse a opacity o width
                    trace.update(marker=dict(opacity=0.9))
        
        elif config.animation_type == AnimationType.HIGHLIGHT:
            # Highlight se aplica con line width y color
            if hasattr(trace, 'line'):
                current_width = getattr(trace.line, 'width', None)
                if current_width is None:
                    current_width = 2
                trace.update(line=dict(width=current_width * 1.5))
        
        elif config.animation_type == AnimationType.PULSE:
            # Pulse se aplica con marker size
            if hasattr(trace, 'marker'):
                current_size = getattr(trace.marker, 'size', None)
                if current_size is None:
                    current_size = 6
                trace.update(marker=dict(size=current_size * 1.2))
        
        # SLIDE_UP y otros requieren configuración a nivel de layout/frames
        # Se manejan en create_animation_frames
        
        return trace
    
    def create_animation_frames(
        self,
        figure: go.Figure,
        sequence: AnimationSequence
    ) -> go.Figure:
        """Crear frames de animación para una secuencia completa."""
        
        if not self.global_enabled or not sequence.animations:
            return figure
        
        frames = []
        
        for i, anim_config in enumerate(sequence.animations):
            # Crear frame con estado intermedio
            frame_data = []
            for trace in figure.data:
                animated_trace = self.apply_animation_to_trace(
                    trace.copy(), anim_config, i
                )
                frame_data.append(animated_trace)
            
            frames.append(go.Frame(
                data=frame_data,
                name=f"frame_{i}"
            ))
        
        # Añadir frames a la figura
        figure.frames = frames
        
        # Configurar animación con updatemenus
        figure.update_layout(
            updatemenus=[{
                "buttons": [
                    {
                        "args": [None, {
                            "frame": {"duration": int(anim_config.duration_ms * self.global_duration_multiplier),
                                      "redraw": True},
                            "fromcurrent": True,
                            "transition": {"duration": int(anim_config.duration_ms * self.global_duration_multiplier),
                                          "easing": anim_config.easing.value}
                        }],
                        "label": "▶ Play",
                        "method": "animate"
                    },
                    {
                        "args": [[None], {
                            "frame": {"duration": 0, "redraw": False},
                            "mode": "immediate"
                        }],
                        "label": "⏸ Pause",
                        "method": "animate"
                    }
                ],
                "direction": "left",
                "pad": {"r": 10, "t": 87},
                "showactive": False,
                "type": "buttons",
                "x": 0.1,
                "xanchor": "right",
                "y": 0,
                "yanchor": "top"
            }]
        )
        
        return figure
    
    def apply_entry_animation(
        self,
        figure: go.Figure,
        chart_type: str = "default"
    ) -> go.Figure:
        """Aplicar animación de entrada optimizada según tipo de gráfico."""
        
        if not self.global_enabled:
            return figure
        
        # Seleccionar preset según tipo de gráfico
        preset_map = {
            "bar": AnimationPresets.smooth_scale_up(),
            "line": AnimationPresets.subtle_fade_in(),
            "scatter": AnimationPresets.professional_slide_up(),
            "heatmap": AnimationPresets.subtle_fade_in(),
            "default": AnimationPresets.subtle_fade_in()
        }
        
        config = preset_map.get(chart_type, preset_map["default"])
        
        # Aplicar a todos los traces - figure.data es inmutable, usar lista
        animated_traces = list(figure.data)
        
        for i, trace in enumerate(animated_traces):
            # Añadir delay escalonado para efecto cascada
            delayed_config = AnimationConfig(
                animation_type=config.animation_type,
                duration_ms=config.duration_ms,
                easing=config.easing,
                delay_ms=i * 50,  # 50ms de delay entre elementos
                from_opacity=config.from_opacity,
                to_opacity=config.to_opacity,
                from_scale=config.from_scale,
                to_scale=config.to_scale
            )
            animated_traces[i] = self.apply_animation_to_trace(trace, delayed_config)
        
        # Reemplazar data con traces animados
        figure.data = animated_traces
        
        return figure
    
    def create_transition_animation(
        self,
        old_figure: go.Figure,
        new_figure: go.Figure,
        duration_ms: int = 600
    ) -> go.Figure:
        """Crear animación de transición entre dos estados de gráfico."""
        
        if not self.global_enabled:
            return new_figure
        
        # Crear frames para transición suave
        frames = []
        num_frames = 10  # Frames intermedios para suavidad
        
        for i in range(num_frames + 1):
            progress = i / num_frames  # 0.0 a 1.0
            
            # Interpolar datos entre old y new
            frame_data = []
            for old_trace, new_trace in zip(old_figure.data, new_figure.data):
                interpolated_trace = self._interpolate_traces(
                    old_trace, new_trace, progress
                )
                frame_data.append(interpolated_trace)
            
            frames.append(go.Frame(
                data=frame_data,
                name=f"transition_{i}"
            ))
        
        new_figure.frames = frames
        new_figure.update_layout(
            transition=dict(
                duration=duration_ms,
                easing="cubic-in-out"
            )
        )
        
        return new_figure
    
    def _interpolate_traces(
        self,
        trace1: go.BaseTraceType,
        trace2: go.BaseTraceType,
        progress: float
    ) -> go.BaseTraceType:
        """Interpolar entre dos traces para transición suave."""
        
        # Crear copia del trace base
        result = trace1.copy()
        
        # Interpolar valores numéricos (y, x, etc.)
        if hasattr(trace1, 'y') and hasattr(trace2, 'y'):
            y1 = np.array(trace1.y) if trace1.y is not None else np.array([])
            y2 = np.array(trace2.y) if trace2.y is not None else np.array([])
            
            if len(y1) == len(y2) and len(y1) > 0:
                result.y = y1 + (y2 - y1) * progress
        
        if hasattr(trace1, 'x') and hasattr(trace2, 'x'):
            x1 = np.array(trace1.x) if trace1.x is not None else np.array([])
            x2 = np.array(trace2.x) if trace2.x is not None else np.array([])
            
            if len(x1) == len(x2) and len(x1) > 0:
                result.x = x1 + (x2 - x1) * progress
        
        # Interpolar opacity
        if hasattr(trace1, 'opacity') and hasattr(trace2, 'opacity'):
            op1 = trace1.opacity if trace1.opacity is not None else 1.0
            op2 = trace2.opacity if trace2.opacity is not None else 1.0
            result.opacity = op1 + (op2 - op1) * progress
        
        return result
    
    def add_hover_animation(
        self,
        figure: go.Figure,
        trace_indices: Optional[List[int]] = None
    ) -> go.Figure:
        """Añadir configuración de hover para interactividad mejorada."""
        
        if not self.global_enabled:
            return figure
        
        indices = trace_indices if trace_indices else list(range(len(figure.data)))
        
        for idx in indices:
            if idx < len(figure.data):
                trace = figure.data[idx]
                
                # Configurar hover info básico
                if hasattr(trace, 'hoverinfo'):
                    trace.hoverinfo = "x+y+name"
                
                # Configurar mejoras básicas de marker
                if hasattr(trace, 'marker'):
                    current_opacity = trace.marker.opacity if trace.marker.opacity else 1.0
                    trace.update(marker=dict(opacity=min(current_opacity, 0.9)))
        
        return figure


# Instancia global del motor de animaciones
animation_engine = AnimationEngine()

# Registrar presets por defecto
animation_engine.register_sequence(AnimationPresets.entry_sequence())


@lru_cache(maxsize=16)
def get_cached_animation_config(
    animation_type: str,
    duration_ms: int,
    easing: str
) -> Optional[AnimationConfig]:
    """Obtener configuración de animación cacheada."""
    try:
        anim_type = AnimationType(animation_type)
        easing_type = AnimationEasing(easing)
        return AnimationConfig(
            animation_type=anim_type,
            duration_ms=duration_ms,
            easing=easing_type
        )
    except (ValueError, TypeError):
        return None


def animate_figure(
    figure: go.Figure,
    animation_type: str = "entry",
    chart_type: str = "default",
    custom_config: Optional[AnimationConfig] = None
) -> go.Figure:
    """Función helper para animar una figura rápidamente."""
    
    if custom_config:
        return animation_engine.apply_animation_to_trace(
            figure.data[0] if figure.data else None,
            custom_config
        )
    
    if animation_type == "entry":
        return animation_engine.apply_entry_animation(figure, chart_type)
    elif animation_type == "hover":
        return animation_engine.add_hover_animation(figure)
    
    return figure


class AnimatedChartBuilder:
    """Extensión de ChartBuilder con soporte de animaciones."""
    
    def __init__(self, base_builder):
        self.base_builder = base_builder
        self.animation_configs: List[AnimationConfig] = []
        self.animation_sequence: Optional[AnimationSequence] = None
    
    def with_animation(
        self,
        animation_type: Union[AnimationType, str],
        duration_ms: int = 300,
        easing: Union[AnimationEasing, str] = AnimationEasing.CUBIC_IN_OUT
    ) -> 'AnimatedChartBuilder':
        """Añadir configuración de animación."""
        
        if isinstance(animation_type, str):
            try:
                animation_type = AnimationType(animation_type)
            except ValueError:
                return self
        
        if isinstance(easing, str):
            try:
                easing = AnimationEasing(easing)
            except ValueError:
                easing = AnimationEasing.CUBIC_IN_OUT
        
        config = AnimationConfig(
            animation_type=animation_type,
            duration_ms=duration_ms,
            easing=easing
        )
        
        if config.validate():
            self.animation_configs.append(config)
        
        return self
    
    def with_animation_sequence(self, sequence: AnimationSequence) -> 'AnimatedChartBuilder':
        """Asignar secuencia de animación completa."""
        self.animation_sequence = sequence
        return self
    
    def build(self) -> go.Figure:
        """Construir figura con animaciones aplicadas."""
        
        # Construir figura base
        figure = self.base_builder.build()
        
        # Aplicar animaciones individuales
        for config in self.animation_configs:
            for i, trace in enumerate(figure.data):
                delayed_config = AnimationConfig(
                    animation_type=config.animation_type,
                    duration_ms=config.duration_ms,
                    easing=config.easing,
                    delay_ms=i * 30  # Delay escalonado
                )
                figure.data[i] = animation_engine.apply_animation_to_trace(
                    trace, delayed_config
                )
        
        # Aplicar secuencia completa si existe
        if self.animation_sequence:
            figure = animation_engine.create_animation_frames(
                figure, self.animation_sequence
            )
        
        # Añadir hover animations
        figure = animation_engine.add_hover_animation(figure)
        
        return figure