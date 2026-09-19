"""Pruebas de caracterización de las nuevas fronteras arquitectónicas."""

import ast
import numpy as np
from pathlib import Path

from gex.domain.options.greeks import call_delta, gamma
from gex.domain.gex import metrics


ROOT = Path(__file__).parents[1]


def _imports_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _assert_no_import_prefixes(root: Path, forbidden: tuple[str, ...]) -> None:
    violations: list[str] = []
    for path in _python_files(root):
        for imported in _imports_in(path):
            if imported.startswith(forbidden):
                violations.append(f"{path.relative_to(ROOT)} imports {imported}")

    assert violations == []


def test_domain_greeks_are_available_without_presentation():
    assert np.isfinite(call_delta(100, 100, 0.25, 0.04, 0.2))
    assert gamma(100, 100, 0.25, 0.04, 0.2) > 0


def test_domain_gex_facade_exposes_existing_calculations():
    assert callable(metrics.exposure_by_strike)
    assert callable(metrics.zero_gamma)


def test_package_root_is_limited_to_bootstrap_files():
    root = ROOT / "gex"
    assert {path.name for path in root.glob("*.py")} == {
        "__init__.py", "__main__.py", "legacy.py", "main.py",
    }


def test_domain_does_not_import_ui_or_presentation_layers():
    _assert_no_import_prefixes(
        ROOT / "gex" / "domain",
        (
            "dash",
            "flask",
            "matplotlib",
            "plotly",
            "tkinter",
            "gex.presentation",
        ),
    )


def test_market_intelligence_models_are_ui_free():
    for path in (
        ROOT / "gex" / "domain" / "market" / "intelligence.py",
        ROOT / "gex" / "domain" / "market" / "interaction.py",
        ROOT / "gex" / "domain" / "market" / "reports.py",
        ROOT / "gex" / "domain" / "market" / "scenarios.py",
        ROOT / "gex" / "domain" / "market" / "state.py",
    ):
        imports = _imports_in(path)

        assert not any(
            imported.startswith(("dash", "flask", "plotly", "gex.presentation", "gex.adapters"))
            for imported in imports
        )


def test_options_flow_application_stays_independent_of_ui_and_adapters():
    _assert_no_import_prefixes(
        ROOT / "gex" / "application" / "options_flow",
        (
            "dash",
            "flask",
            "plotly",
            "gex.presentation",
            "gex.adapters",
        ),
    )


def test_market_intelligence_application_stays_independent_of_ui_and_adapters():
    _assert_no_import_prefixes(
        ROOT / "gex" / "application" / "market_intelligence",
        (
            "dash",
            "flask",
            "plotly",
            "gex.presentation",
            "gex.adapters",
        ),
    )


def test_options_overlay_renderer_does_not_import_adapters():
    imports = _imports_in(ROOT / "gex" / "presentation" / "dashboard" / "options_overlay.py")

    assert not any(imported.startswith("gex.adapters") for imported in imports)
