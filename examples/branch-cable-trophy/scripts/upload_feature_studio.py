#!/usr/bin/env python3
"""Upload the local FeatureScript and require the expected compiled spec."""

import json
import sys

import _paths  # noqa: E402  (puts ROOT on sys.path; see _paths.py)
import _guard  # noqa: E402

from onshape_rest_api_mode.client import ROOT, STATE_PATH, load_json
from onshape_rest_api_mode.operations import upload_feature_studio

# A syntactically bad upload still costs quota with no diagnostics (featurespecs
# comes back empty), so run the zero-cost local checker first — it intercepts
# the exact failure classes that burned quota during live verification.
sys.path.insert(0, str(ROOT / "scripts"))
import fs_local_check  # noqa: E402  (scripts/ is not a package)

source = ROOT / load_json(STATE_PATH).get("featureScriptFile", "branchCableTrophyDisplay.fs")
result = fs_local_check.check_file(source)
for warning in result.warnings:
    print(f"WARN {warning}", file=sys.stderr)
if result.errors:
    raise SystemExit(
        "refusing upload: scripts/fs_local_check.py found structural errors:\n  "
        + "\n  ".join(result.errors)
    )

_guard.require_live(3, "upload_feature_studio")
print(json.dumps(upload_feature_studio(), indent=2))
