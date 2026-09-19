#!/usr/bin/env python3
"""Command-line wrapper for the offline FeatureScript checker.

The analysis lives in ``onshape_docs/query/fs_check.py`` so the MCP runtime can
import it directly; this file keeps the documented command working:

    python3 onshape_docs/scripts/fs_local_check.py [FILE...]     # files or dirs
    Exit code: 0 all pass, 1 any structural error.

Structural findings are hard stops for a *human* upload decision because they
waste quota, but the checker itself is advisory: the MCP tool ``fs_check_script``
reports the same findings and never blocks a deploy.

The public names are re-exported so existing importers keep working.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from onshape_docs.query.fs_check import (  # noqa: E402,F401 - re-exported API
    INDEX_PATH,
    ROOT as DOCS_ROOT,
    FsFile,
    check_file,
    check_source,
    main,
)

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
