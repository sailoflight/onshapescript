#!/usr/bin/env python3
"""Render the model's standard visual-review views."""

import json

import _paths  # noqa: E402  (puts ROOT on sys.path; see _paths.py)

from onshape_fs_mcp.operations import render_all_previews

print(json.dumps({"created": render_all_previews()}, indent=2))
