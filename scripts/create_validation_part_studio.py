#!/usr/bin/env python3
"""Create a clean validation Part Studio and persist its ID."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from onshape_tools.operations import create_validation_part_studio

print(json.dumps(create_validation_part_studio(), indent=2))
