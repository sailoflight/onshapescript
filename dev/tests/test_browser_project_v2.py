from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from onshape_browser_mode import project


ROOT = Path(__file__).resolve().parents[2]


class ProjectV2Test(unittest.TestCase):
    def test_committed_multi_deliverable_fixture_dry_run(self):
        result = project.run_project("module-interface-deliverables", dry_run=True)
        self.assertEqual(result["schemaVersion"], 2)
        self.assertEqual(result["stepCount"], 6)
        self.assertEqual(result["deliverableCount"], 5)
        self.assertEqual(
            [item["id"] for item in result["deliverables"]],
            ["rail-part", "groove-part", "assembly", "rail-drawing", "groove-drawing"],
        )
        self.assertEqual(result["deliverables"][2]["dependsOn"], ["rail-part", "groove-part"])

    def test_multi_deliverable_execution_writes_independent_manifests(self):
        calls = []

        def executor(tool, args):
            calls.append(tool)
            if tool == "browser_create_document":
                return {"created": True, "documentId": "doc"}
            if tool == "browser_deploy_and_apply_featurescript":
                return {
                    "built": True,
                    "parts": 1,
                    "partStudio": {"name": args["part_studio_tab"], "elementId": args["part_studio_tab"]},
                }
            if tool == "browser_assemble":
                return {
                    "assembled": True,
                    "configurationTriggered": True,
                    "assembly": {"name": args["assembly_tab"], "elementId": "assembly"},
                }
            if tool == "browser_drawing_insert_views":
                return {
                    "viewsInserted": True,
                    "drawingState": {"drawingTab": f"{args['part_name']} Drawing", "viewEvidence": True},
                }
            raise AssertionError(tool)

        with tempfile.TemporaryDirectory() as tmp:
            result = project.run_project(
                "module-interface-deliverables",
                executor=executor,
                checkpoint_dir=Path(tmp),
            )
            checkpoint = json.loads(Path(result["checkpointPath"]).read_text(encoding="utf-8"))
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["completedDeliverables"]), 5)
        self.assertEqual(set(result["deliverableManifests"]), set(result["completedDeliverables"]))
        self.assertEqual(checkpoint["version"], 2)
        self.assertEqual(len(checkpoint["deliverableManifests"]), 5)
        for manifest in result["deliverableManifests"].values():
            self.assertEqual(manifest["semanticLevel"], "L6")
            self.assertEqual(manifest["semanticName"], "deliverable_recipe")
            self.assertTrue(manifest["accepted"])
            self.assertTrue(manifest["outputs"][0]["present"])
            self.assertEqual(manifest["fixtureSha256"], result["deliverableManifests"][manifest["deliverableId"]]["fixtureSha256"])
        self.assertEqual(calls[0], "browser_create_document")
        self.assertLess(calls.index("browser_assemble"), calls.index("browser_drawing_insert_views"))

    def test_single_deliverable_project_is_valid(self):
        fixture = {
            "schemaVersion": 2,
            "name": "single",
            "deliverables": [
                {
                    "id": "part",
                    "kind": "part_studio",
                    "depends_on": [],
                    "steps": [
                        {"id": "build", "tool": "browser_build_part", "args": {"feature_name": "Part"}}
                    ],
                    "assertions": [{"step": "build", "key": "built", "equals": True}],
                    "outputs": [
                        {
                            "name": "part-studio",
                            "step": "build",
                            "key": "partStudio",
                            "mediaType": "application/vnd.onshape.partstudio",
                        }
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "projects"
            checkpoints = Path(tmp) / "checkpoints"
            projects.mkdir()
            (projects / "single.json").write_text(json.dumps(fixture), encoding="utf-8")
            result = project.run_project(
                "single",
                projects_dir=projects,
                checkpoint_dir=checkpoints,
                executor=lambda tool, args: {
                    "built": True,
                    "partStudio": {"name": "Part Studio 1", "elementId": "ps"},
                },
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["completedDeliverables"], ["part"])
        self.assertTrue(result["deliverableManifests"]["part"]["accepted"])

    def test_v2_rejects_missing_outputs_and_dependency_cycles(self):
        base = {
            "schemaVersion": 2,
            "name": "invalid",
            "deliverables": [
                {
                    "id": "a",
                    "kind": "part_studio",
                    "depends_on": [],
                    "steps": [{"id": "a-step", "tool": "browser_build_part", "args": {}}],
                    "assertions": [{"step": "a-step", "key": "built", "equals": True}],
                    "outputs": [],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp)
            path = projects / "invalid.json"
            path.write_text(json.dumps(base), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "requires manifest outputs"):
                project.load_project("invalid", projects)
            base["deliverables"][0]["outputs"] = [
                {
                    "name": "part",
                    "step": "a-step",
                    "key": "partStudio",
                    "mediaType": "application/vnd.onshape.partstudio",
                }
            ]
            base["deliverables"][0]["depends_on"] = ["a"]
            path.write_text(json.dumps(base), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "dependency cycle"):
                project.load_project("invalid", projects)

    def test_rejected_output_does_not_mark_deliverable_complete(self):
        fixture = {
            "schemaVersion": 2,
            "name": "missing-output",
            "deliverables": [
                {
                    "id": "part",
                    "kind": "part_studio",
                    "depends_on": [],
                    "steps": [{"id": "build", "tool": "browser_build_part", "args": {}}],
                    "assertions": [{"step": "build", "key": "built", "equals": True}],
                    "outputs": [
                        {
                            "name": "part",
                            "step": "build",
                            "key": "partStudio",
                            "mediaType": "application/vnd.onshape.partstudio",
                        }
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "projects"
            checkpoints = Path(tmp) / "checkpoints"
            projects.mkdir()
            (projects / "missing-output.json").write_text(json.dumps(fixture), encoding="utf-8")
            result = project.run_project(
                "missing-output",
                projects_dir=projects,
                checkpoint_dir=checkpoints,
                executor=lambda tool, args: {"built": True, "partStudio": None},
            )
        self.assertFalse(result["ok"])
        self.assertEqual(result["completedDeliverables"], [])
        self.assertFalse(result["failedDeliverable"]["manifest"]["accepted"])


if __name__ == "__main__":
    unittest.main()


class ProjectThinFeatureBuildTest(unittest.TestCase):
    """A project must be able to CREATE a thin row already carrying its numbers.

    A thin, native-shaped custom feature is exactly a row of a few numbers, so the
    only way one project can build a feature tree of them without a browser
    transaction per row is a tool that inserts with parameters. Before this the
    closed set held no such tool, and the closed set's rule is that an unlisted
    tool is refused rather than run.
    """

    def test_insert_with_parameters_is_allowed_and_has_an_outcome_key(self):
        self.assertIn("browser_insert_custom_feature", project.ALLOWED_PROJECT_TOOLS)
        self.assertEqual(
            project.TOOL_OUTCOME_KEYS["browser_insert_custom_feature"], "inserted"
        )

    def test_every_allowed_tool_binds_an_outcome_key(self):
        """The closed set and the outcome table must not drift apart."""
        missing = sorted(project.ALLOWED_PROJECT_TOOLS - set(project.TOOL_OUTCOME_KEYS))
        self.assertEqual(missing, [])

    def test_every_allowed_tool_can_actually_serve_a_step(self):
        """The closed set must not name a tool the runner cannot resolve.

        A tool can be listed here, carry an outcome key, be registered with the
        server, and still be refused at run time: a step's tool is resolved from the
        browser module, which looks in BROWSER_HANDLERS for the handler and then in
        BROWSER_TOOLS for the definition. A tool known only to the server's own tool
        list is therefore refused on its first step with "Project tool has no
        registered schema", which is what happened to
        browser_insert_custom_feature. Importing the server runs install(), which is
        the step that completes BROWSER_TOOLS.
        """
        from mcp_main.win.mcp import browser_tools, server  # noqa: F401 - install() fills the table

        handlers = set(browser_tools.BROWSER_HANDLERS) | browser_tools.PROJECT_INLINE_TOOLS
        schemas = {tool["name"] for tool in browser_tools.BROWSER_TOOLS}
        self.assertEqual(sorted(project.ALLOWED_PROJECT_TOOLS - handlers), [])
        self.assertEqual(
            sorted(project.ALLOWED_PROJECT_TOOLS - schemas - browser_tools.PROJECT_INLINE_TOOLS),
            [],
        )

    def test_a_step_that_inserts_with_parameters_runs_and_reports_its_evidence(self):
        seen: list[tuple[str, dict]] = []

        def executor(tool, args):
            seen.append((tool, args))
            if tool == "browser_deploy_and_apply_featurescript":
                return {"built": True}
            return {
                "inserted": True,
                "parameters": {"updated": ["width"], "missing": [], "readbackOk": True},
            }

        fixture = {
            "schemaVersion": 1,
            "name": "thin-row-build",
            "steps": [
                {"id": "refresh-fs", "tool": "browser_deploy_and_apply_featurescript",
                 "args": {"script_file": "dev/fixtures-capture/thin-native-features.fs",
                          "apply": False}},
                {"id": "body-sketch", "tool": "browser_insert_custom_feature",
                 "args": {"feature_name": "Thin Sketch Rectangle",
                          "parameters": {"width": "84 mm", "height": "84 mm"}}},
                {"id": "body-extrude", "tool": "browser_insert_custom_feature",
                 "args": {"feature_name": "Thin Extrude", "parameters": {"depth": "10 mm"}}},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            projects = Path(directory)
            (projects / "thin-row-build.json").write_text(
                json.dumps(fixture), encoding="utf-8"
            )
            result = project.run_project(
                "thin-row-build",
                executor=executor,
                projects_dir=projects,
                checkpoint_dir=projects,
            )
        self.assertTrue(result["ok"])
        self.assertEqual([tool for tool, _ in seen],
                         ["browser_deploy_and_apply_featurescript",
                          "browser_insert_custom_feature",
                          "browser_insert_custom_feature"])
        self.assertEqual(seen[1][1]["parameters"], {"width": "84 mm", "height": "84 mm"})

    def test_an_insert_that_did_not_land_stops_the_project(self):
        def executor(tool, args):
            if tool == "browser_deploy_and_apply_featurescript":
                return {"built": True}
            return {"inserted": False, "reason": "the parameter dialog was not filled exactly"}

        fixture = {
            "schemaVersion": 1,
            "name": "thin-row-refused",
            "steps": [
                {"id": "refresh-fs", "tool": "browser_deploy_and_apply_featurescript",
                 "args": {"script_file": "dev/fixtures-capture/thin-native-features.fs",
                          "apply": False}},
                {"id": "body-sketch", "tool": "browser_insert_custom_feature",
                 "args": {"feature_name": "Thin Sketch Rectangle",
                          "parameters": {"width": "84 mm"}}},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            projects = Path(directory)
            (projects / "thin-row-refused.json").write_text(
                json.dumps(fixture), encoding="utf-8"
            )
            result = project.run_project(
                "thin-row-refused",
                executor=executor,
                projects_dir=projects,
                checkpoint_dir=projects,
            )
        self.assertFalse(result["ok"])
        self.assertEqual(result["failed"]["id"], "body-sketch")
