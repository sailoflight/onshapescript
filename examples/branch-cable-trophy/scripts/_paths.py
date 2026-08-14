#!/usr/bin/env python3
"""Shared preamble for the Branch Cable Trophy example CLI scripts.

Putting the project root on sys.path and pointing the output directory at this
example must happen before `onshape_fs_mcp` is imported, because the client
package reads these locations at import time.

Import first in every example script, before any onshape_fs_mcp import:

    from pathlib import Path
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _paths  # noqa: E402  (sets ROOT on sys.path and example outputs dir)

The parameter sets and target document state are shared with the MCP server and
live in the project root `config/`; see examples/branch-cable-trophy/README.md.
"""

import os
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
EXAMPLE_DIR = SCRIPTS_DIR.parent
ROOT = EXAMPLE_DIR.parent.parent

os.environ.setdefault("ONSHAPE_OUTPUTS_DIR", str(EXAMPLE_DIR / "outputs"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
