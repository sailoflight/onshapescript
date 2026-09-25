"""Transport-independent FDM analysis contracts.

This package is a local library. It does not register MCP tools and does not know
about browser sessions, Onshape IDs, REST credentials, or quota.

Re-exports are LAZY (PEP 562), and that is a deliberate dependency adjustment, not a
micro-optimisation. A package ``__init__`` runs before any of its submodules, so the
former eager re-exports made every ``fdm_analysis.X`` import pull the whole pipeline:
a caller that only wanted ``file_sha256`` from ``.contracts`` -- which is exactly what
the Onshape STEP export does -- loaded 16 submodules including ``slicers.bambu_studio``
and ``slicers.execution`` (measured 2026-09-25). Lazy attributes keep the same public
names while making the cost proportional to what the caller actually imports.

Add a name to ``_LAZY_EXPORTS`` when adding a public re-export; ``__all__`` stays the
single advertised list.
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "FdmBackends",
    "GeometryBackends",
    "MeshArtifact",
    "SliceArtifact",
    "SliceProfile",
    "StepArtifact",
    "WindowsToWslDelivery",
    "WorkspaceDeliveryTarget",
    "WslLocalDelivery",
    "build_fdm_package",
    "build_geometry_package",
]

#: Public name -> defining submodule. Keep in sync with ``__all__``.
_LAZY_EXPORTS: dict[str, str] = {
    "MeshArtifact": ".contracts",
    "SliceArtifact": ".contracts",
    "SliceProfile": ".contracts",
    "StepArtifact": ".contracts",
    "WindowsToWslDelivery": ".delivery",
    "WorkspaceDeliveryTarget": ".delivery",
    "WslLocalDelivery": ".delivery",
    "GeometryBackends": ".geometry_pipeline",
    "build_geometry_package": ".geometry_pipeline",
    "FdmBackends": ".pipeline",
    "build_fdm_package": ".pipeline",
}


def __getattr__(name: str) -> Any:
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(module_name, __name__), name)
    globals()[name] = value  # resolve once, then ordinary lookup takes over
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))
