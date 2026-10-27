"""Check the direction of the dependencies between the layers of the package.

common <- extract <- transform <- load <- analytics: a module may only import
from its own layer or from the layers on its left, so that no circular import
can appear between the steps of the ETL, and the ETL never depends on the
analyses of its data.
"""

import ast

from pathlib import Path

import pytest

PACKAGE_DIR = Path(__file__).resolve().parents[1] / "src" / "access_it"
LAYERS = ["common", "etl.extract", "etl.transform", "etl.load", "analytics"]


def layer_of(module: str) -> int | None:
    """Index of the layer of a module of the package, None outside the layers."""
    for index, layer in enumerate(LAYERS):
        prefix = f"access_it.{layer}"
        if module == prefix or module.startswith(prefix + "."):
            return index
    return None


def imported_modules(path: Path) -> set[str]:
    """Modules of the package imported by a file, at any level of the code."""
    modules = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return {module for module in modules if module.startswith("access_it")}


FILES = [
    (path, index)
    for index, layer in enumerate(LAYERS)
    for path in sorted((PACKAGE_DIR / layer.replace(".", "/")).glob("*.py"))
]


@pytest.mark.parametrize("path, index", FILES, ids=[str(p.relative_to(PACKAGE_DIR)) for p, _ in FILES])
def test_no_import_from_a_later_layer(path, index):
    later = [
        module for module in imported_modules(path)
        if (layer_of(module) or 0) > index
    ]
    assert later == [], f"{path.name} imports from a later layer: {later}"
