#!/usr/bin/env python3
"""Upload the local FeatureScript and require the expected compiled spec."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from onshape_tools.operations import upload_feature_studio

print(json.dumps(upload_feature_studio(), indent=2))
