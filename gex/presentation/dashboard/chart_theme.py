"""Sistema de diseño visual institucional para gráficos Plotly.

Transforma los gráficos de estética neon a un diseño profesional de terminal
financiero con paleta institucional, tipografía consistente y accesibilidad WCAG AA.
"""

from dataclasses import dataclass
from typing import Dict, Any
import plotly.graph_objects as go


@dataclass
class ChartColors:
    """Paleta de colores institucional para gráficos financieros."""
    
    # Primary data series
    spot: str = "#ffffff"
    call: str = "#4caf8a"
    put: str = "#e06b7a"
    net: str = "#94a3b8"
    
    # Key levels
    call_wall: str = "#5b9bd5"
    put_wall: str = "#e06b7a"
    gamma_flip: str = "#d4a84b"
    hvl: str = "#4caf8a"
    
    # Backgrounds and grid
    background: str = "#111a25"
    surface: str = "#182332"
    grid: str = "#1a2535"
    axis: str = "#26334d"
    
    # Text colors
    text_primary: str = "#e2e8f0"
    text_secondary: str = "#94a3b8"
    text_muted: str = "#64748b"
    
    # Semantic states
    positive: str = "#4caf8a"
    negative: str = "#e06b7a"
    warning: str = "#d4a84b"
    info: str = "#5b9bd5"
    success: str = "#4caf8a"
    
    # Heatmap professional palette (replaces neon)
    heatmap_low: str = "#1e3a5f"
    heatmap_medium: str = "#3b5998"
    heatmap_high: str = "#5b9bd5"
    heatmap_very_high: str = "#7dd3fc"
    
    def to_dict(self) -> Dict[str, str]:
        """Convertir a diccionario para uso con Plotly."""
        return {
            "spot": self.spot,
            "call": self.call,
            "put": self.put,
            "net": self.net,
            "call_wall": self.call_wall,
            "put_wall": self.put_wall,
            "gamma_flip": self.gamma_flip,
            "hvl": self.hvl,
            "background": self.background,
            "surface": self.surface,
            "grid": self.grid,
            "axis": self.axis,
            "text_primary": self.text_primary,
            "text_secondary": self.text_secondary,
            "text_muted": self.text_muted,
            "positive": self.positive,
            "negative": self.negative,
            "warning": self.warning,
            "info": self.info,
            "success": self.success,
        }


@dataclass
class ChartFonts:
    """Sistema tipográfico consistente para gráficos."""
    
    ui: str = "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif"
    data: str = "JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    
    sizes: Dict[str, int] = None
    
    def __post_init__(self):
        if self.sizes is None:
            self.sizes = {
                "title": 13,
                "subtitle": 11,
                "axis": 11,
                "legend": 11,
                "tooltip": 12,
                "annotation": 11
            }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario para uso con Plotly."""
        return {
            "ui": self.ui,
            "data": self.data,
            "sizes": self.sizes
        }


@dataclass
class ChartSpacing:
    """Sistema de espaciado consistente para gráficos."""
    
    margin: Dict[str, int] = None
    
    def __post_init__(self):
        if self.margin is None:
            self.margin = {
                "l": 58,   # Left margin para labels
                "r": 18,   # Right margin
                "t": 42,   # Top margin para título
                "b": 38    # Bottom margin para eje X
            }
    
    def to_dict(self) -> Dict[str, int]:
        """Convertir a diccionario para uso con Plotly."""
        return self.margin


@dataclass
class ChartShadows:
    """Sistema de sombras profesionales (sin neón/glow)."""
    
    sm: str = "0 1px 3px rgba(0, 0, 0, 0.3)"
    md: str = "0 4px 12px rgba(0, 0, 0, 0.4)"
    lg: str = "0 12px 32px rgba(0, 0, 0, 0.5)"
    
    def to_dict(self) -> Dict[str, str]:
        """Convertir a diccionario."""
        return {
            "sm": self.sm,
            "md": self.md,
            "lg": self.lg
        }


@dataclass
class ChartAnimations:
    """Sistema de animaciones sutiles y profesionales."""
    
    duration: int = 300  # ms
    easing: str = "cubic-in-out"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario para uso con Plotly."""
        return {
            "duration": self.duration,
            "easing": self.easing
        }


class ChartTheme:
    """Sistema completo de temas para gráficos Plotly."""
    
    INSTITUTIONAL = "institutional"
    AVAILABLE_THEMES = [INSTITUTIONAL]
    
    def __init__(self, theme: str = INSTITUTIONAL):
        self.theme = theme
        self.colors = ChartColors()
        self.fonts = ChartFonts()
        self.spacing = ChartSpacing()
        self.shadows = ChartShadows()
        self.animations = ChartAnimations()
    
    def get_institutional_layout(
        self, 
        title: str, 
        height: int = 420,
        show_legend: bool = False
    ) -> Dict[str, Any]:
        """Genera layout base institucional."""
        
        layout = {
            "title": {
                "text": title,
                "font": {
                    "size": self.fonts.sizes["title"],
                    "color": self.colors.text_primary,
                    "family": self.fonts.ui
                },
                "x": 0.012,
                "y": 0.97,
                "xanchor": "left"
            },
            "template": None,
            "paper_bgcolor": self.colors.background,
            "plot_bgcolor": self.colors.background,
            "font": {
                "family": self.fonts.ui,
                "size": self.fonts.sizes["axis"],
                "color": self.colors.text_secondary
            },
            "margin": self.spacing.margin,
            "height": height,
            "xaxis": {
                "gridcolor": self.colors.grid,
                "zerolinecolor": self.colors.axis,
                "linecolor": self.colors.axis,
                "tickfont": {"color": self.colors.text_muted},
                "title": {"font": {"color": self.colors.text_muted}}
            },
            "yaxis": {
                "gridcolor": self.colors.grid,
                "zerolinecolor": self.colors.axis,
                "linecolor": self.colors.axis,
                "tickfont": {"color": self.colors.text_muted},
                "title": {"font": {"color": self.colors.text_muted}}
            },
            "hoverlabel": {
                "bgcolor": self.colors.surface,
                "font": {
                    "family": self.fonts.ui,
                    "color": self.colors.text_primary
                }
            },
            "showlegend": show_legend,
            "dragmode": "pan",  # Pan por defecto, zoom con scroll
        }
        
        if show_legend:
            layout["legend"] = {
                "orientation": "h",
                "y": 1.13,
                "x": 1,
                "xanchor": "right",
                "font": {
                    "color": self.colors.text_secondary,
                    "size": self.fonts.sizes["legend"]
                }
            }
            layout["margin"]["t"] = 62  # Espacio extra para leyenda
        
        return layout
    
    def apply_theme_to_figure(self, fig: go.Figure) -> go.Figure:
        """Aplica tema institucional a figura existente."""
        fig.update_layout(
            paper_bgcolor=self.colors.background,
            plot_bgcolor=self.colors.background,
            font=dict(
                family=self.fonts.ui,
                color=self.colors.text_primary
            )
        )
        return fig
    
    def get_heatmap_colorscale(self) -> list:
        """Genera colorscale profesional para heatmaps (sin neon)."""
        return [
            [0.0, self.colors.heatmap_low],
            [0.25, self.colors.heatmap_medium],
            [0.5, self.colors.heatmap_high],
            [0.75, self.colors.heatmap_very_high],
            [1.0, self.colors.spot]
        ]
    
    def get_color_by_signal(self, signal: str) -> str:
        """Obtener color basado en señal semántica."""
        color_map = {
            "positive": self.colors.positive,
            "negative": self.colors.negative,
            "warning": self.colors.warning,
            "info": self.colors.info,
            "success": self.colors.success,
            "call": self.colors.call,
            "put": self.colors.put,
            "spot": self.colors.spot,
            "call_wall": self.colors.call_wall,
            "put_wall": self.colors.put_wall,
            "gamma_flip": self.colors.gamma_flip,
            "hvl": self.colors.hvl
        }
        return color_map.get(signal, self.colors.net)


# Instancia global del tema institucional
INSTITUTIONAL_THEME = ChartTheme(ChartTheme.INSTITUTIONAL)