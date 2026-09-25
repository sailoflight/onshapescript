#!/usr/bin/env python3
"""Offline contracts for the built consumer Release artifact.

`test_consumer_release.py` pins the SPEC (what may ship). This file pins the
ARTIFACT (what building it actually produces), because a spec that passes while
the archive is missing a package is exactly the failure mode this project already
hit: `fdm_analysis/` was absent from the whitelist and the server could not be
imported at all.

The strongest check here is the smoke test: the archive is extracted to a temp
directory and the server is started over stdio FROM THAT DIRECTORY with
`PYTHONPATH` removed, so an artifact that depends on the checkout or on a
development-only path fails instead of passing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dev.tools import build_release  # noqa: E402
from dev.tools import consumer_release_spec as spec  # noqa: E402
from fdm_analysis.contracts import file_sha256  # noqa: E402
from mcp_main.win.mcp import server as mcp_server  # noqa: E402

#: Fixed so the artifact name does not depend on the working tree's git state.
TEST_REVISION = "testrev"
#: Entries the builder adds on top of the planned file set.
_ADDED = {"release-manifest.json", "SHA256SUMS", "RELEASE-NOTES.md"}


def _extract(artifact: Path, destination: Path) -> list[str]:
    with zipfile.ZipFile(artifact) as archive:
        names = archive.namelist()
        archive.extractall(destination)
    return names


class BuiltArtifactTest(unittest.TestCase):
    tmp: tempfile.TemporaryDirectory
    artifact: Path
    sidecar: Path

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        written = build_release.build(
            root=ROOT, destination=Path(cls.tmp.name), rev=TEST_REVISION
        )
        cls.artifact = written["artifact"]
        cls.sidecar = written["outerChecksum"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_the_builder_refuses_to_write_inside_the_checkout(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as inside:
            with self.assertRaises(ValueError) as caught:
                build_release.build(
                    root=ROOT, destination=Path(inside), rev=TEST_REVISION
                )
            self.assertIn("inside the checkout", str(caught.exception))

    def test_the_builder_refuses_a_spec_with_invariant_violations(self) -> None:
        with tempfile.TemporaryDirectory() as empty, tempfile.TemporaryDirectory() as out:
            # An empty root cannot satisfy the whitelist, so nothing may be built.
            with self.assertRaises(ValueError) as caught:
                build_release.build(
                    root=Path(empty), destination=Path(out), rev=TEST_REVISION
                )
            self.assertIn("invariant violations", str(caught.exception))
            self.assertEqual(list(Path(out).iterdir()), [])

    def test_the_outer_sidecar_matches_the_artifact(self) -> None:
        line = self.sidecar.read_text(encoding="utf-8").strip()
        digest, name = line.split("  ", 1)
        self.assertEqual(name, self.artifact.name)
        self.assertEqual(digest, file_sha256(self.artifact))

    def test_the_archive_contains_exactly_the_plan_plus_its_own_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            names = set(_extract(self.artifact, Path(tmp)))
        planned = {entry.path for entry in spec.plan(ROOT).files}
        self.assertEqual(names - _ADDED, planned)
        self.assertFalse(
            [name for name in names if spec.is_denied(name)],
            "a denylisted path reached the artifact",
        )
        self.assertEqual([name for name in names if name.endswith(".pyc")], [])

    def test_every_shipped_file_matches_the_plan_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _extract(self.artifact, Path(tmp))
            mismatched = [
                entry.path
                for entry in spec.plan(ROOT).files
                if file_sha256(Path(tmp) / entry.path) != entry.sha256
            ]
        self.assertEqual(mismatched, [])

    def test_the_inner_checksum_sidecar_covers_exactly_the_shipped_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _extract(self.artifact, root)
            rows = [
                line.split("  ", 1)
                for line in (root / spec.CHECKSUM_SIDECAR_NAME)
                .read_text(encoding="utf-8")
                .splitlines()
                if line
            ]
            self.assertEqual({relative for _, relative in rows}, {e.path for e in spec.plan(ROOT).files})
            bad = [rel for digest, rel in rows if file_sha256(root / rel) != digest]
        self.assertEqual(bad, [])

    def test_the_manifest_says_it_is_an_unsigned_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _extract(self.artifact, root)
            manifest = json.loads(
                (root / spec.MANIFEST_NAME).read_text(encoding="utf-8")
            )
        self.assertEqual(manifest["artifactStatus"], "built")
        self.assertEqual(manifest["artifactFormat"], "zip")
        self.assertFalse(manifest["signed"])
        self.assertEqual(manifest["sourceRevision"], TEST_REVISION)
        self.assertEqual(manifest["mcpServerVersion"], spec.MCP_SERVER_VERSION)
        expected = spec.plan(ROOT).files
        self.assertEqual(manifest["fileCount"], len(expected))
        self.assertEqual(
            [row["path"] for row in manifest["files"]], [e.path for e in expected]
        )
        # The preserved-state list is what an upgrade carries over, so it must be
        # the host-independent denylist -- not the subset that happens to exist in
        # this checkout, which would drop a state file the build machine lacks
        # (the machine-local geometry backend selection was exactly that).
        self.assertEqual(manifest["excludedPaths"], list(spec.DENYLIST))
        self.assertTrue(
            {"onshape_browser_mode/config/geometry-backend.json",
             "onshape_rest_api_mode/config/geometry-backend.json"}.issubset(
                set(manifest["excludedPaths"])
            )
        )

    def test_the_release_notes_name_the_artifact_and_the_open_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _extract(self.artifact, root)
            notes = (root / build_release.RELEASE_NOTES_NAME).read_text(encoding="utf-8")
        self.assertIn(self.artifact.name, notes)
        self.assertIn(spec.MCP_SERVER_VERSION, notes)
        self.assertIn("unsigned", notes.lower())
        self.assertIn("Code signing", notes)
        self.assertIn("Preserved state", notes)
        # The notes must not present the open items as settled.
        self.assertIn("Open items", notes)

    def test_the_build_is_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            one = build_release.build(
                root=ROOT, destination=Path(first), rev=TEST_REVISION
            )["artifact"]
            two = build_release.build(
                root=ROOT, destination=Path(second), rev=TEST_REVISION
            )["artifact"]
            self.assertEqual(one.name, two.name)
            self.assertEqual(file_sha256(one), file_sha256(two))

    def test_the_artifact_runs_standalone_over_stdio(self) -> None:
        """The acceptance proxy: extract, then call an offline tool with no checkout."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _extract(self.artifact, root)
            env = {
                "PATH": os.environ.get("PATH", ""),
                "PYTHONDONTWRITEBYTECODE": "1",
                # Deliberately NO PYTHONPATH: the artifact must stand alone.
            }
            for key in ("SYSTEMROOT", "TEMP", "TMP"):
                if key in os.environ:
                    env[key] = os.environ[key]
            proc = subprocess.Popen(
                [sys.executable, "-m", "mcp_main.win.mcp"],
                cwd=str(root),
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                def call(payload: dict) -> dict:
                    assert proc.stdin is not None and proc.stdout is not None
                    proc.stdin.write(json.dumps(payload) + "\n")
                    proc.stdin.flush()
                    line = proc.stdout.readline()
                    self.assertTrue(line, "the server closed stdout without answering")
                    return json.loads(line)

                init = call({
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "artifact-smoke", "version": "1"},
                    },
                })
                result = init.get("result", {})
                self.assertEqual(result.get("serverInfo", {}).get("version"), spec.MCP_SERVER_VERSION)
                self.assertTrue(result.get("instructions"), "runtime prompt was not delivered")

                proc.stdin.write(
                    json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
                )
                proc.stdin.flush()
                listing = call({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
                names = {tool["name"] for tool in listing["result"]["tools"]}
                self.assertIn("browser_session", names)

                catalog = call({
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "mcp_tool_catalog", "arguments": {"action": "status"}},
                })
                text = catalog["result"]["content"][0]["text"]
                status = json.loads(text)
                # Same tool surface as the checkout the artifact was built from:
                # a missing module would change this count or fail the import.
                self.assertEqual(status["registryCount"], len(mcp_server.TOOLS))

                geometry = call({
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "onshape_geometry_status", "arguments": {}},
                })
                report = json.loads(geometry["result"]["content"][0]["text"])
                # The geometry backend selection is operator state and does not
                # ship, so a fresh install has no live file: readiness must read
                # as "not configured" instead of failing the tool.
                for mode in ("rest", "browser"):
                    self.assertFalse(
                        report["backends"][mode]["configFilePresent"], mode
                    )
                    self.assertFalse(report["backends"][mode]["ready"], mode)
            finally:
                if proc.stdin:
                    proc.stdin.close()
                proc.terminate()
                try:
                    proc.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=20)
                stderr = proc.stderr.read() if proc.stderr else ""
                for stream in (proc.stdout, proc.stderr):
                    if stream:
                        stream.close()
            self.assertEqual(stderr.strip(), "", f"server wrote to stderr: {stderr[:400]}")


if __name__ == "__main__":
    unittest.main()
