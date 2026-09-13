"""Generador de PDFs profesionales desde Markdown."""
import markdown
from weasyprint import HTML, CSS

class PDFGenerator:
    def __init__(self):
        self.css_template = """
        @page { size: A4; margin: 2cm; }
        body { font-family: 'Inter', sans-serif; font-size: 11pt; line-height: 1.6; color: #1e293b; }
        h1 { color: #0f172a; border-bottom: 2px solid #5b9bd5; padding-bottom: 0.5em; }
        h2 { color: #334155; border-bottom: 1px solid #cbd5e1; padding-bottom: 0.3em; margin-top: 1.5em; }
        table { border-collapse: collapse; width: 100%; margin: 1em 0; }
        th, td { border: 1px solid #cbd5e1; padding: 0.5em; text-align: left; }
        th { background-color: #f1f5f9; font-weight: 600; }
        .positive { color: #16a34a; font-weight: 600; }
        .negative { color: #dc2626; font-weight: 600; }
        """
    
    def generate_pdf(self, markdown_content: str, output_path: str):
        html_content = markdown.markdown(markdown_content, extensions=['tables'])
        full_html = f"<!DOCTYPE html><html><head><title>GEX Report</title></head><body>{html_content}</body></html>"
        HTML(string=full_html).write_pdf(output_path, stylesheets=[CSS(string=self.css_template)])