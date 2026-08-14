#!/usr/bin/env python3
"""Vendor the live Onshape REST API OpenAPI definition into reference/raw/onshape-api/.

Pulls the spec Onshape serves at /api/openapi (the same URL their official
`onshape-public/openapi` CI workflow downloads from), authenticated with the
local onshape-credentials.json. This is the *live* definition for the running
deployment, so it is always current — no stale third-party snapshot.

Afterwards run scripts/build_onshape_api_index.py to rebuild the JSON indexes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from onshape_fs_mcp.client import OnshapeClient  # noqa: E402

ONSHAPE_API_DIR = ROOT / "reference" / "raw" / "onshape-api"
OPENAPI_PATH = ONSHAPE_API_DIR / "openapi.json"
OPENAPI_URL = "https://cad.onshape.com/api/openapi"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true", help="only print the sha256")
    args = parser.parse_args()

    client = OnshapeClient()
    spec = client.request("GET", "/api/openapi", timeout=300)
    info = spec.get("info", {})
    if not args.quiet:
        print(f"Fetching {OPENAPI_URL} (api version {info.get('version')})")
    ONSHAPE_API_DIR.mkdir(parents=True, exist_ok=True)
    # Compact: this file is a machine source, not for reading.
    OPENAPI_PATH.write_text(
        json.dumps(spec, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    digest = sha256_of(OPENAPI_PATH)
    print(f"  ok   openapi.json ({OPENAPI_PATH.stat().st_size} bytes) sha256 = {digest}")
    if not args.quiet:
        print(f"  spec version {info.get('version')} "
              f"| {len(spec.get('paths', {}))} paths | "
              f"{len(spec.get('tags', []))} tags")
    return 0


if __name__ == "__main__":
    sys.exit(main())
