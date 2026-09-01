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
