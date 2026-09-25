"""Import shape: an Onshape-only entry point must not pull the FDM pipeline.

Owner decision 2026-09-25 (issue #1 follow-up): ``fdm_analysis`` SHIPS with the
artifact, because the geometry/FDM capabilities are exposed as MCP tools. What was
adjusted is the dependency SHAPE, not the file list:

* ``mcp_main/win/mcp/server.py`` no longer imports the geometry/step_export modules
  at module scope, so importing the server no longer loads ``fdm_analysis`` at all;
* ``fdm_analysis/__init__.py`` re-exports lazily (PEP 562), so a caller that only
  needs a contract from a submodule does not load the slicer/delivery pipeline.

Both facts are measured in a FRESH interpreter. Doing it in-process would be a lie:
this test module and its siblings import ``fdm_analysis`` eagerly, so ``sys.modules``
would already be populated by the time any assertion ran.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_FDM_PREFIX = "fdm_analysis"

#: Prints the ``fdm_analysis`` modules the imported target pulled in.
_LOADED_PROBE = textwrap.dedent(
    """
    import json, sys
    __import__(sys.argv[1])
    loaded = sorted(
        name for name in sys.modules
        if name == "fdm_analysis" or name.startswith("fdm_analysis.")
    )
    print(json.dumps(loaded))
    """
)

#: Prints the resolved type name of every advertised re-export.
_REEXPORT_PROBE = textwrap.dedent(
    """
    import json, sys
    import fdm_analysis
    resolved = {name: type(getattr(fdm_analysis, name)).__name__ for name in fdm_analysis.__all__}
    print(json.dumps(resolved))
    """
)


def _run_probe(probe: str, *argv: str) -> str:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-c", probe, *argv],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"probe failed ({completed.returncode}): {completed.stderr.strip()}"
        )
    return completed.stdout.strip().splitlines()[-1]


class FdmDependencyShapeTest(unittest.TestCase):
    def test_the_contracts_module_does_not_load_the_slicer_pipeline(self) -> None:
        loaded = json.loads(_run_probe(_LOADED_PROBE, "fdm_analysis.contracts"))
        # `file_sha256` is the only FDM symbol the Onshape STEP export needs, and
        # before the lazy `__init__` this same import pulled 16 submodules.
        self.assertEqual(loaded, ["fdm_analysis", "fdm_analysis.contracts"])

    def test_the_mcp_server_module_does_not_load_the_fdm_package_at_all(self) -> None:
        loaded = json.loads(_run_probe(_LOADED_PROBE, "mcp_main.win.mcp.server"))
        self.assertEqual(
            [name for name in loaded if name == _FDM_PREFIX or name.startswith(_FDM_PREFIX + ".")],
            [],
            "the server reintroduced a module-scope import of the FDM package",
        )

    def test_every_advertised_reexport_still_resolves(self) -> None:
        resolved = json.loads(_run_probe(_REEXPORT_PROBE))
        self.assertEqual(
            set(resolved),
            {
                "FdmBackends",
                "GeometryBackends",
                "MeshArtifact",
                "SliceArtifact",
                "SliceProfile",
                "StepArtifact",
                "WindowsToWslDelivery",
                "WorkspaceDeliveryTarget",
                "WslLocalDelivery",
                "build_fdm_package",
                "build_geometry_package",
            },
        )
        # Lazy attributes must resolve to the real objects, never to a submodule.
        self.assertNotIn("module", set(resolved.values()))
        self.assertEqual(resolved["StepArtifact"], "type")
        self.assertEqual(resolved["build_fdm_package"], "function")

    def test_an_unknown_attribute_still_raises_attribute_error(self) -> None:
        import fdm_analysis

        with self.assertRaises(AttributeError) as caught:
            fdm_analysis.NotAnExport
        self.assertIn("NotAnExport", str(caught.exception))

    def test_lazy_reexports_cover_the_advertised_names(self) -> None:
        import fdm_analysis

        self.assertEqual(set(fdm_analysis._LAZY_EXPORTS), set(fdm_analysis.__all__))


if __name__ == "__main__":
    unittest.main()
