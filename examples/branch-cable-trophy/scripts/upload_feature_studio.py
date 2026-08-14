#!/usr/bin/env python3
"""Upload the local FeatureScript and require the expected compiled spec."""

import json

import _paths  # noqa: E402  (puts ROOT on sys.path; see _paths.py)

from onshape_fs_mcp.operations import upload_feature_studio

print(json.dumps(upload_feature_studio(), indent=2))
