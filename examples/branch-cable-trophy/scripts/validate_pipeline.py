#!/usr/bin/env python3
"""Upload, instantiate, gate, and render the detailed default model."""

import runpy
from pathlib import Path

import _paths  # noqa: E402  (puts ROOT on sys.path; see _paths.py)
import _guard  # noqa: E402

# Gate the whole run once before stepping: upload(3) + create(1) + instantiate(2)
# + check_model(3) + render(5) = 14 calls. Each sub-script re-gates its own step.
_guard.require_live(14, "validation pipeline (render on)")

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
