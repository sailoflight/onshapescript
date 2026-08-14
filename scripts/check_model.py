#!/usr/bin/env python3
"""Gate the detailed model against feature, part, name, and bounds invariants."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from onshape_tools.client import REPORT_DIR
from onshape_tools.operations import check_model

report = check_model("detailed")
REPORT_DIR.mkdir(parents=True, exist_ok=True)
(REPORT_DIR / "model-check.json").write_text(
    json.dumps(report, indent=2) + "\n",
    encoding="utf-8",
)
print(json.dumps(report, indent=2))
if not report["ok"]:
    raise SystemExit(1)
