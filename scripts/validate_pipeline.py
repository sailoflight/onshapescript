#!/usr/bin/env python3
"""Upload, instantiate, gate, and render the detailed default model."""

import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
