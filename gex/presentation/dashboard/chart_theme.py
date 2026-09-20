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
    spot: str = "#f4f7fb"
    call: str = "#58b6c4"
    put: str = "#d98795"
    net: str = "#a8b3c2"
    
    # Key levels
    call_wall: str = "#58b6c4"
    put_wall: str = "#d98795"
    gamma_flip: str = "#d8b65a"
    hvl: str = "#a78bfa"
    session_regular: str = "#5e9cf3"
    session_overnight: str = "#c084fc"
    level_neutral: str = "#8c99a8"
    
    # Backgrounds and grid
    background: str = "#0b1118"
    surface: str = "#101923"
    grid: str = "#17232e"
    axis: str = "#334354"
    
    # Text colors
    text_primary: str = "#f4f7fb"
    text_secondary: str = "#a8b3c2"
    text_muted: str = "#748295"
    
    # Semantic states
    positive: str = "#6b93e5"
    negative: str = "#d98795"
    warning: str = "#d8b65a"
    info: str = "#58b6c4"
    success: str = "#6b93e5"
    
    # Heatmap professional palette (replaces neon)
    heatmap_low: str = "#25122f"
    heatmap_medium: str = "#762557"
    heatmap_high: str = "#0f718a"
    heatmap_very_high: str = "#58b6c4"
    
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
            "session_regular": self.session_regular,
            "session_overnight": self.session_overnight,
            "level_neutral": self.level_neutral,
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
            [0.5, self.colors.background],
            [0.75, self.colors.heatmap_high],
            [1.0, self.colors.heatmap_very_high],
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
