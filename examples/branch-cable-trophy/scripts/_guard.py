#!/usr/bin/env python3
"""Shared live-API gate for the Branch Cable Trophy example CLI scripts.

Every example script that talks to the live Onshape API gates BEFORE its first
request — LIVE_API_ENABLED (the protocol's top constraint: real requests must
be explicit, not a script default), the passive rate-limit hold, and the
annual-quota preflight. All three checks are zero network cost.

Import AFTER _paths (it puts the project root on sys.path, which the
onshape_fs_mcp imports below need):

    import _paths  # noqa: E402
    import _guard  # noqa: E402
    _guard.require_live(3, "upload_feature_studio")
"""

from onshape_fs_mcp.budget import live_blocker


def require_live(estimate_calls: int, label: str) -> None:
    """Exit with a clear message if the live operation must not run."""
    blocker = live_blocker(estimate_calls, label)
    if blocker:
        raise SystemExit(f"refusing to run {label}: {blocker}")
