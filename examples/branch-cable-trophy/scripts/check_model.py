#!/usr/bin/env python3
"""Gate the detailed model against feature, part, name, and bounds invariants."""

import json

import _paths  # noqa: E402  (puts ROOT on sys.path; see _paths.py)
import _guard  # noqa: E402

from onshape_rest_api_mode.client import REPORT_DIR
from onshape_rest_api_mode.operations import check_model

_guard.require_live(3, "check_model")
report = check_model("detailed")
REPORT_DIR.mkdir(parents=True, exist_ok=True)
(REPORT_DIR / "model-check.json").write_text(
    json.dumps(report, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(report, indent=2))
if not report["ok"]:
    raise SystemExit(1)
