#!/usr/bin/env python3
"""Upload the local FeatureScript and require the expected compiled spec.

The zero-cost local check runs inside ``upload_feature_studio`` and is advisory:
when it finds structural errors the operation returns an
``acknowledgementRequired`` result *before* spending its three API calls. Pass
``--acknowledge-local-findings`` to proceed anyway, which is deliberately a
second, explicit decision rather than a silent default.
"""

import json
import sys

import _paths  # noqa: E402  (puts ROOT on sys.path; see _paths.py)
import _guard  # noqa: E402

from onshape_docs.query.fs_check import ACKNOWLEDGEMENT_ARGUMENT
from onshape_rest_api_mode.operations import upload_feature_studio

acknowledge = "--acknowledge-local-findings" in sys.argv[1:]

_guard.require_live(3, "upload_feature_studio")
result = upload_feature_studio(acknowledge_local_findings=acknowledge)
print(json.dumps(result, indent=2))
if result.get("acknowledgementRequired"):
    print(
        "Local check found structural findings (listed in localFindings above). "
        f"Re-run with --acknowledge-local-findings, or fix the source.\n"
        f"API argument name: {ACKNOWLEDGEMENT_ARGUMENT}",
        file=sys.stderr,
    )
    raise SystemExit(1)
