"""Onshape browser page objects."""

from onshape_browser_mode.pages.base import (
    AmbiguousFrameError, BasePage, FrameNotFoundError, resolve_scope, scope_url,
)
from onshape_browser_mode.pages.models import (
    AssemblyPage,
    DocumentsPage,
    DrawingPage,
    FeatureStudioPage,
    PartStudioPage,
)

__all__ = [
    "AmbiguousFrameError",
    "AssemblyPage",
    "BasePage",
    "DocumentsPage",
    "DrawingPage",
    "FeatureStudioPage",
    "FrameNotFoundError",
    "PartStudioPage",
    "resolve_scope",
    "scope_url",
]
