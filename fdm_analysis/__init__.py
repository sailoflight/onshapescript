"""Transport-independent FDM analysis contracts.

This package is a local library. It does not register MCP tools and does not know
about browser sessions, Onshape IDs, REST credentials, or quota.
"""

from .contracts import MeshArtifact, SliceArtifact, SliceProfile, StepArtifact
from .delivery import WindowsToWslDelivery, WorkspaceDeliveryTarget, WslLocalDelivery
from .geometry_pipeline import GeometryBackends, build_geometry_package
from .pipeline import FdmBackends, build_fdm_package

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
