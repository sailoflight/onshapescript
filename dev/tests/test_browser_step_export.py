from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from onshape_browser_mode import selectors
from onshape_browser_mode.project import run_project
from onshape_browser_mode.step_export import (
    export_browser_step,
    plan_browser_step_export,
    register_downloaded_browser_step,
)


class FakeLocator:
    def __init__(self, *, count=1, checked=False):
        self._count = count
        self.checked = checked
        self.clicks = []
        self.fills = []
        self.selections = []
        self.waits = []

    @property
    def first(self):
        return self

    def filter(self, **kwargs):
        self.filter_args = kwargs
        return self

    def count(self):
        return self._count

    def click(self, **kwargs):
        self.clicks.append(kwargs)
        if not kwargs.get("button"):
            self.checked = not self.checked

    def fill(self, value):
        self.fills.append(value)

    def select_option(self, **kwargs):
        self.selections.append(kwargs)

    def is_checked(self):
        return self.checked

    def wait_for(self, **kwargs):
        self.waits.append(kwargs)


class FakeDownload:
    def __init__(self, suggested="fixture.step", failure=None):
        self.suggested_filename = suggested
        self._failure = failure
        self.saved = []

    def failure(self):
        return self._failure

    def save_as(self, path):
        self.saved.append(path)
        Path(path).write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="ascii")


class DownloadContext:
    def __init__(self, download):
        self.value = download

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakePage:
    def __init__(self, download=None):
        self.url = "https://cad.onshape.com/documents/doc1/w/workspace1/e/element1"
        self.download = download or FakeDownload()
        self.locators = {
            selectors.TAB_BAR_TAB: FakeLocator(),
            selectors.TAB_CONTEXT_MENU_ITEM: FakeLocator(),
            selectors.EXPORT_DIALOG: FakeLocator(),
            selectors.EXPORT_FILENAME: FakeLocator(),
            selectors.EXPORT_FORMAT: FakeLocator(),
            selectors.EXPORT_LATEST_VERSION: FakeLocator(checked=True),
            selectors.EXPORT_STEP_VERSION: FakeLocator(),
            selectors.EXPORT_CUSTOM_STEP_UNITS: FakeLocator(checked=False),
            selectors.EXPORT_STEP_UNITS: FakeLocator(),
            selectors.EXPORT_OPTIONS: FakeLocator(),
            selectors.EXPORT_INDIVIDUAL_FILES: FakeLocator(checked=True),
            selectors.EXPORT_HIDDEN_ENTITIES: FakeLocator(checked=False),
            selectors.EXPORT_SUBMIT: FakeLocator(),
        }
        self.download_timeouts = []

    def locator(self, selector):
        return self.locators[selector]

    def expect_download(self, *, timeout):
        self.download_timeouts.append(timeout)
        return DownloadContext(self.download)


class BrowserStepExportTest(unittest.TestCase):
    def test_field_validation_project_is_a_valid_l6_dry_run(self):
        plan = run_project("browser-step-export-field-validation", dry_run=True)
        self.assertTrue(plan["dryRun"])
        self.assertEqual(plan["schemaVersion"], 2)
        self.assertEqual(plan["deliverables"][0]["id"], "canonical-step")

    def test_dry_run_is_local_and_declares_exact_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = plan_browser_step_export(
                source_tab="Part Studio 1",
                export_id="export1",
                output_root=Path(tmp),
            )
        self.assertTrue(plan["dryRun"])
        self.assertEqual(plan["configuration"]["format"], "STEP")
        self.assertEqual(plan["configuration"]["version"], "AP242")
        self.assertEqual(plan["configuration"]["unit"], "Millimeter")
        self.assertEqual(plan["configuration"]["option"], "下载")
        self.assertFalse(plan["configuration"]["individualFiles"])
        self.assertEqual(plan["estimatedApiRequests"], 0)

    def test_export_configures_dialog_downloads_and_registers_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            page = FakePage()
            result = export_browser_step(
                page,
                source_tab="Part Studio 1",
                export_id="export1",
                document_id="doc1",
                workspace_id="workspace1",
                element_id="element1",
                output_root=root,
            )
            manifest = json.loads(Path(result["stepManifestPath"]).read_text(encoding="utf-8"))
        self.assertTrue(result["exported"])
        self.assertEqual(result["apiRequests"], 0)
        self.assertFalse(result["bambuIncluded"])
        self.assertEqual(page.locators[selectors.TAB_BAR_TAB].clicks, [{}, {"button": "right"}])
        self.assertEqual(page.locators[selectors.EXPORT_FILENAME].fills, ["export1"])
        self.assertEqual(page.locators[selectors.EXPORT_FORMAT].selections, [{"label": "STEP"}])
        self.assertEqual(page.locators[selectors.EXPORT_STEP_VERSION].selections, [{"label": "AP242"}])
        self.assertEqual(page.locators[selectors.EXPORT_STEP_UNITS].selections, [{"label": "Millimeter"}])
        self.assertEqual(page.locators[selectors.EXPORT_OPTIONS].selections, [{"label": "下载"}])
        self.assertFalse(page.locators[selectors.EXPORT_INDIVIDUAL_FILES].checked)
        self.assertFalse(page.locators[selectors.EXPORT_HIDDEN_ENTITIES].checked)
        self.assertEqual(manifest["exportId"], "export1")
        self.assertEqual(manifest["artifact"]["source"]["mode"], "browser")
        self.assertEqual(manifest["artifact"]["units"], "mm")
        self.assertEqual(manifest["artifact"]["path"], "model.step")

    def test_non_step_download_fails_before_creating_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(RuntimeError, "non-STEP"):
                export_browser_step(
                    FakePage(FakeDownload("fixture.zip")),
                    source_tab="Part Studio 1",
                    export_id="export1",
                    document_id="doc1",
                    workspace_id="workspace1",
                    element_id="element1",
                    output_root=root,
                )
            self.assertFalse((root / "export1").exists())

    def test_registration_rejects_secret_bearing_page_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = root / "export1"
            staging.mkdir()
            (staging / "model.step").write_text("ISO-10303-21;\n", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "credential-free HTTPS"):
                register_downloaded_browser_step(
                    export_id="export1",
                    file_name="model.step",
                    page_url="https://cad.onshape.com/documents/doc?token=secret",
                    document_id="doc1",
                    workspace_id="workspace1",
                    element_id="element1",
                    output_root=root,
                )


if __name__ == "__main__":
    unittest.main()
