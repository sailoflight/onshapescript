#!/usr/bin/env python3
"""Create a clean validation Part Studio and persist its ID."""

import json

import _paths  # noqa: E402  (puts ROOT on sys.path; see _paths.py)
import _guard  # noqa: E402

from onshape_fs_mcp.operations import create_validation_part_studio

_guard.require_live(1, "create_validation_part_studio")
print(json.dumps(create_validation_part_studio(), indent=2))
