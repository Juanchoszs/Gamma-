"""Generador de documentos Markdown profesionales para análisis GEX."""
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

@dataclass
class DocumentSection:
    title: str
    content: str
    subsections: List['DocumentSection'] = None
    level: int = 1

class MarkdownGenerator:
    def __init__(self):
        self.sections = []
        self.metadata = {}
    
    def add_section(self, section: DocumentSection):
        self.sections.append(section)
        return self
    
    def set_metadata(self, **metadata):
        self.metadata.update(metadata)
        return self
    
    def generate(self) -> str:
        md = self._generate_header()
        md += self._generate_toc()
        md += self._generate_sections()
        md += self._generate_footer()
        return md
    
    def _generate_header(self) -> str:
        header = f"# {self.metadata.get('title', 'Análisis GEX')}\n\n"
        header += f"**Fecha**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        header += f"**Símbolo**: {self.metadata.get('symbol', 'N/A')}\n"
        header += "---\n\n"
        return header
    
    def _generate_toc(self) -> str:
        toc = "## Índice\n\n"
        for section in self.sections:
            indent = "  " * (section.level - 1)
            toc += f"{indent}- [{section.title}](#{self._slugify(section.title)})\n"
        return toc + "\n"
    
    def _generate_sections(self) -> str:
        content = ""
        for section in self.sections:
            heading = "#" * section.level
            content += f"{heading} {section.title}\n\n"
            content += f"{section.content}\n\n"
        return content
    
    def _generate_footer(self) -> str:
        return "*Generado por Sistema GEX Analytics*\n"
    
    def _slugify(self, text: str) -> str:
        return text.lower().replace(" ", "-").replace(":", "")