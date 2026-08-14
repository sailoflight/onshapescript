#!/usr/bin/env python3
"""Upload, instantiate, gate, and render the detailed default model."""

import runpy
from pathlib import Path

import _paths  # noqa: E402  (puts ROOT on sys.path; see _paths.py)

scripts = Path(__file__).resolve().parent
for name in [
    "upload_feature_studio.py",
    "create_validation_part_studio.py",
    "instantiate_feature.py",
    "check_model.py",
    "render_previews.py",
]:
    print(f"\n== {name} ==")
    runpy.run_path(str(scripts / name), run_name="__main__")
