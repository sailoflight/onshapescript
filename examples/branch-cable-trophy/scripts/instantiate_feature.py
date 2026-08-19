#!/usr/bin/env python3
"""Instantiate the workspace custom feature using a JSON parameter set."""

import argparse
import json
from pathlib import Path

import _paths  # noqa: E402  (puts ROOT on sys.path; see _paths.py)
import _guard  # noqa: E402

from onshape_rest_api_mode.client import DEFAULT_PARAMETERS_PATH, load_json
from onshape_rest_api_mode.operations import PARAMETER_PATHS, instantiate_feature

parser = argparse.ArgumentParser()
parser.add_argument("--parameters", type=Path, default=DEFAULT_PARAMETERS_PATH)
args = parser.parse_args()

parameter_set = next(
    (name for name, path in PARAMETER_PATHS.items()
     if args.parameters.resolve() == path.resolve()),
    None,
)
_guard.require_live(2, "instantiate_feature")
if parameter_set is None:
    summary = instantiate_feature("default", overrides=load_json(args.parameters))
else:
    summary = instantiate_feature(parameter_set)
print(json.dumps(summary, indent=2, ensure_ascii=False))
