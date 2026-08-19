#!/usr/bin/env python3
"""Render the model's standard visual-review views."""

import json

import _paths  # noqa: E402  (puts ROOT on sys.path; see _paths.py)
import _guard  # noqa: E402

from onshape_rest_api_mode.operations import render_all_previews

_guard.require_live(5, "render_all_previews")
print(json.dumps({"created": render_all_previews()}, indent=2))
