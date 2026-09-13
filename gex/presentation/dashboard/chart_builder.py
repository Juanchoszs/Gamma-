"""ChartBuilder pattern para construcción consistente de gráficos institucionales.

Implementa el patrón Builder para crear gráficos Plotly con diseño
profesional consistente, reduciendo duplicación y garantizando calidad visual.
"""

from typing import Dict, Any, List, Optional, Callable
import plotly.graph_objects as go
import numpy as np
from functools import lru_cache

from .chart_theme import INSTITUTIONAL_THEME, ChartTheme


class ChartBuilder:
    """Builder pattern para construcción consistente de gráficos institucionales."""
    
    def __init__(self, theme: ChartTheme = None):
        self.theme = theme or INSTITUTIONAL_THEME
        self.reset()
    
    def reset(self) -> 'ChartBuilder':
        """Resetear el builder para un nuevo gráfico."""
        self.fig = go.Figure()
        self.layout_config = {}
        self.traces = []
        self.annotations = []
        self.shapes = []
        self._title = ""
        self._height = 420
        self._show_legend = False
        return self
    
    def with_base_layout(
        self, 
        title: str, 
        height: int = 420,
        show_legend: bool = False
    ) -> 'ChartBuilder':
        """Aplica layout base institucional."""
        self._title = title
        self._height = height
        self._show_legend = show_legend
        self.layout_config = self.theme.get_institutional_layout(title, height, show_legend)
        return self
    
    def add_trace(
        self, 
        trace_type: str, 
        data: Dict[str, Any], 
        style: Optional[Dict[str, Any]] = None
    ) -> 'ChartBuilder':
        """Añade trace con estilos consistentes."""
        
        if style is None:
            style = {}
        
        # Aplicar colores institucionales si no se especifican
        if trace_type == "bar" and "marker" not in style:
            color = style.get("color", self.theme.colors.net)
            style["marker"] = {"color": color, "line": {"width": 0}}
        
        trace = self._create_trace(trace_type, data, style)
        self.traces.append(trace)
        return self
    
    def add_scatter(
        self,
        x: List,
        y: List,
        name: str,
        color: Optional[str] = None,
        mode: str = "lines"
    ) -> 'ChartBuilder':
        """Añade scatter plot simplificado."""
        trace = go.Scatter(
            x=x,
            y=y,
            name=name,
            mode=mode,
            line=dict(color=color or self.theme.colors.net, width=2),
            marker=dict(size=6, color=color or self.theme.colors.net)
        )
        self.traces.append(trace)
        return self
    
    def add_bar(
        self,
        x: List,
        y: List,
        name: str,
        color: Optional[str] = None,
        orientation: str = "v"
    ) -> 'ChartBuilder':
        """Añade bar chart simplificado."""
        trace = go.Bar(
            x=x,
            y=y,
            name=name,
            orientation=orientation,
            marker=dict(color=color or self.theme.colors.net)
        )
        self.traces.append(trace)
        return self
    
    def with_annotations(
        self, 
        annotations: List[Dict[str, Any]]
    ) -> 'ChartBuilder':
        """Añade anotaciones estandarizadas."""
        self.annotations.extend(annotations)
        return self
    
    def add_level_annotation(
        self,
        y_value: float,
        label: str,
        color: str,
        side: str = "right"
    ) -> 'ChartBuilder':
        """Añade anotación de nivel clave estandarizada."""
        annotation = {
            "y": y_value,
            "x": 1 if side == "right" else 0,
            "xanchor": "right" if side == "right" else "left",
            "yanchor": "middle",
            "text": label,
            "showarrow": False,
            "font": {
                "size": 11,
                "color": color,
                "family": self.theme.fonts.ui
            },
            "xref": "paper",
            "yref": "y"
        }
        self.annotations.append(annotation)
        return self
    
    def with_shapes(self, shapes: List[Dict[str, Any]]) -> 'ChartBuilder':
        """Añade shapes al gráfico."""
        self.shapes.extend(shapes)
        return self
    
    def add_vertical_line(
        self,
        x_value: float,
        color: str,
        line_type: str = "solid",
        width: float = 1.5
    ) -> 'ChartBuilder':
        """Añade línea vertical estandarizada."""
        shape = {
            "type": "line",
            "x0": x_value,
            "x1": x_value,
            "y0": 0,
            "y1": 1,
            "yref": "paper",
            "line": {
                "color": color,
                "width": width,
                "dash": line_type
            }
        }
        self.shapes.append(shape)
        return self
    
    def with_hover_template(
        self,
        template: str,
        custom_data: Optional[List] = None
    ) -> 'ChartBuilder':
        """Aplica template de hover consistente."""
        for trace in self.traces:
            trace.hovertemplate = template
            if custom_data is not None:
                trace.customdata = custom_data
        return self
    
    def with_range_selector(
        self,
        buttons: List[Dict[str, Any]],
        position: str = "right"
    ) -> 'ChartBuilder':
        """Añade selector de rango estilizado."""
        rangeselector = {
            "buttons": buttons,
            "bgcolor": self.theme.colors.surface,
            "activecolor": self.theme.colors.axis,
            "bordercolor": self.theme.colors.grid,
            "borderwidth": 1,
            "font": {
                "color": self.theme.colors.text_secondary,
                "size": 10
            },
            "x": 1 if position == "right" else 0,
            "xanchor": position,
            "y": 1.22,
            "yanchor": "top"
        }
        self.layout_config["rangeselector"] = rangeselector
        return self
    
    def build(self) -> go.Figure:
        """Construye figura final optimizada."""
        
        # Aplicar layout
        if self.layout_config:
            self.fig.update_layout(**self.layout_config)
        
        # Añadir traces
        for trace in self.traces:
            self.fig.add_trace(trace)
        
        # Añadir anotaciones
        if self.annotations:
            self.fig.update_layout(annotations=self.annotations)
        
        # Añadir shapes
        if self.shapes:
            self.fig.update_layout(shapes=self.shapes)
        
        # Aplicar tema
        self.theme.apply_theme_to_figure(self.fig)
        
        return self.fig
    
    def _create_trace(
        self, 
        trace_type: str, 
        data: Dict[str, Any], 
        style: Dict[str, Any]
    ) -> go.BaseTraceType:
        """Crea trace del tipo especificado."""
        
        trace_factories = {
            "scatter": go.Scatter,
            "bar": go.Bar,
            "line": go.Scatter,
            "area": go.Scatter,
            "heatmap": go.Heatmap,
            "candlestick": go.Candlestick
        }
        
        factory = trace_factories.get(trace_type, go.Scatter)
        return factory(**{**data, **style})


class ChartBuilderFactory:
    """Factory para crear builders especializados."""
    
    @staticmethod
    def exposure_chart(title: str = "Gamma Exposure") -> ChartBuilder:
        """Crea builder especializado para gráficos de exposure."""
        return ChartBuilder().with_base_layout(title, height=560)
    
    @staticmethod
    def heatmap_chart(title: str = "Heatmap") -> ChartBuilder:
        """Crea builder especializado para heatmaps."""
        return ChartBuilder().with_base_layout(title, height=480)
    
    @staticmethod
    def time_series_chart(title: str = "Time Series") -> ChartBuilder:
        """Crea builder especializado para series temporales."""
        return ChartBuilder().with_base_layout(title, height=420, show_legend=True)
    
    @staticmethod
    def volatility_chart(title: str = "Volatility") -> ChartBuilder:
        """Crea builder especializado para volatilidad."""
        return ChartBuilder().with_base_layout(title, height=400)


# Cache de layouts para performance
@lru_cache(maxsize=32)
def get_cached_layout(
    chart_type: str, 
    title: str, 
    height: int,
    show_legend: bool = False
) -> Dict[str, Any]:
    """Cache de layouts para evitar reconstrucción."""
    return INSTITUTIONAL_THEME.get_institutional_layout(title, height, show_legend)


def create_institutional_figure(
    title: str,
    height: int = 420,
    show_legend: bool = False
) -> go.Figure:
    """Función helper para crear figura institucional básica."""
    layout = get_cached_layout("base", title, height, show_legend)
    fig = go.Figure()
    fig.update_layout(**layout)
    INSTITUTIONAL_THEME.apply_theme_to_figure(fig)
    return fig