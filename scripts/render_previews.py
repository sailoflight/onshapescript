#!/usr/bin/env python3
"""Render the model's standard visual-review views."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from onshape_tools.operations import render_all_previews

print(json.dumps({"created": render_all_previews()}, indent=2))
