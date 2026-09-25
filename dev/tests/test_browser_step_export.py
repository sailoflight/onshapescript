from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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


class TargetClosedError(RuntimeError):
    """Offline stand-in for playwright's ``TargetClosedError``."""


class FailingDialogWaitLocator(FakeLocator):
    """A dialog locator that loses its target while waiting for one state.

    The export waits twice on the export dialog: ``visible`` right after the
    context action, and ``hidden`` once the download exists. Issue #8 died on the
    second wait, so only that state fails by default and the artifact really does
    reach disk before the failure.
    """

    def __init__(self, fail_state="hidden"):
        super().__init__()
        self.fail_state = fail_state

    def wait_for(self, **kwargs):
        self.waits.append(kwargs)
        if kwargs.get("state") == self.fail_state:
            raise TargetClosedError("Target page, context or browser has been closed")


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


class FakePageHandle:
    """A page target in the export context, e.g. Edge's downloads-hub page."""

    def __init__(self, url):
        self.url = url
        self.closed = False
        self.close_calls = 0

    def is_closed(self):
        return self.closed

    def close(self):
        self.close_calls += 1
        self.closed = True


class FakeContext:
    def __init__(self, pages=()):
        self.pages = list(pages)


class ExplodingContext:
    @property
    def pages(self):
        raise RuntimeError("no native context")


class FakePage:
    def __init__(self, download=None, context=None, tabs=None, closed=False):
        self.url = "https://cad.onshape.com/documents/doc1/w/workspace1/e/element1"
        self.download = download or FakeDownload()
        self.context = context if context is not None else FakeContext()
        self._closed = closed
        self.tab_selectors = []
        self.evaluations = []
        self.tabs_payload = tabs if tabs is not None else {
            "tabs": [
                {
                    "id": "element1",
                    "name": "Part Studio 1",
                    "elementType": "PARTSTUDIO",
                    "active": True,
                }
            ],
            "hasDocumentTabsToolButton": True,
        }
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
        if selector.startswith(selectors.TAB_BAR_TAB):
            # The exact-name path clicks the matched tab's own data-id, so every
            # tab-strip selector is recorded and shares the one tab locator.
            self.tab_selectors.append(selector)
            return self.locators[selectors.TAB_BAR_TAB]
        return self.locators[selector]

    def evaluate(self, expression, arg=None):
        self.evaluations.append(expression)
        return self.tabs_payload

    def is_closed(self):
        return self._closed

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

    def test_export_closes_browser_internal_downloads_page(self):
        calls = []

        def fake_devtools(port, path, timeout):
            calls.append(path)
            if path == "/json/list":
                return json.dumps([{"type": "page", "id": "T1", "url": "edge://downloads-hub/"}])
            return "Target is closing"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            internal = FakePageHandle("edge://downloads-hub/")
            app = FakePageHandle("https://cad.onshape.com/documents/doc1/w/workspace1/e/element1")
            page = FakePage(context=FakeContext([internal, app]))
            with mock.patch(
                "onshape_browser_mode.session._resident_cdp_port", return_value=9333
            ), mock.patch("onshape_browser_mode.session._devtools_http", side_effect=fake_devtools):
                result = export_browser_step(
                    page,
                    source_tab="Part Studio 1",
                    export_id="export1",
                    document_id="doc1",
                    workspace_id="workspace1",
                    element_id="element1",
                    output_root=root,
                )
        self.assertTrue(result["exported"])
        self.assertEqual(result["browserInternalPagesCloseRequested"], 1)
        # The fake lists the hub on every /json/list, which is what Edge really
        # does even after accepting the close: an accepted request is reported
        # as a request, never as a removed page.
        self.assertEqual(result["browserInternalPagesRemaining"], 1)
        self.assertIn("/json/close/T1", calls)
        # Playwright's close() on that target never returns, so it is never called.
        self.assertEqual(internal.close_calls, 0)
        self.assertFalse(internal.closed)
        self.assertFalse(app.closed)

    def test_export_tolerates_an_unreadable_page_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            page = FakePage(context=ExplodingContext())
            result = export_browser_step(
                page,
                source_tab="Part Studio 1",
                export_id="export1",
                document_id="doc1",
                workspace_id="workspace1",
                element_id="element1",
                output_root=root,
            )
        self.assertTrue(result["exported"])
        self.assertEqual(result["browserInternalPagesCloseRequested"], 0)
        # No readable context means no page list to inspect, so the export makes
        # no DevTools call at all and reports the target count as unknown.
        self.assertIsNone(result["browserInternalPagesRemaining"])

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

    def _tabs_payload(self, *rows):
        return {
            "tabs": [
                {"id": element_id, "name": name, "elementType": "PARTSTUDIO", "active": index == 0}
                for index, (element_id, name) in enumerate(rows)
            ],
            "hasDocumentTabsToolButton": True,
        }

    def _export(self, page, tmp, source_tab="Part Studio 1"):
        return export_browser_step(
            page,
            source_tab=source_tab,
            export_id="export1",
            document_id="doc1",
            workspace_id="workspace1",
            element_id="element1",
            output_root=Path(tmp),
        )

    def test_export_click_targets_the_exact_tab_not_a_name_prefix_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = FakePage(
                tabs=self._tabs_payload(
                    ("tab-old", "GF Thin Plate (old, 14 rows)"),
                    ("tab-plate", "GF Thin Plate"),
                )
            )
            result = self._export(page, tmp, source_tab="GF Thin Plate")
        self.assertTrue(result["exported"])
        # The tab is resolved once and both clicks (select then right-click) use
        # that one locator, which names the intended tab's own data-id; the
        # colliding tab is never addressed. A substring match plus .first picked
        # the first row instead.
        self.assertEqual(
            page.tab_selectors,
            [f'{selectors.TAB_BAR_TAB}[data-id="tab-plate"]'],
        )
        self.assertEqual(
            page.locators[selectors.TAB_BAR_TAB].clicks, [{}, {"button": "right"}]
        )
        self.assertFalse(any("tab-old" in selector for selector in page.tab_selectors))

    def test_export_refuses_an_ambiguous_exact_tab_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = FakePage(
                tabs=self._tabs_payload(("tab-a", "Part Studio 1"), ("tab-b", "Part Studio 1"))
            )
            with self.assertRaises(ValueError) as ctx:
                self._export(page, tmp)
            self.assertFalse((Path(tmp) / "export1").exists())
        self.assertIn("exactly one visible tab name", str(ctx.exception))
        self.assertIn("matchCount=2", str(ctx.exception))
        self.assertEqual(page.locators[selectors.TAB_BAR_TAB].clicks, [])
        self.assertEqual(page.tab_selectors, [])

    def test_export_refuses_a_tab_that_is_only_a_substring(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = FakePage(
                tabs=self._tabs_payload(("tab-old", "GF Thin Plate (old, 14 rows)"))
            )
            with self.assertRaises(ValueError) as ctx:
                self._export(page, tmp, source_tab="GF Thin Plate")
            self.assertFalse((Path(tmp) / "export1").exists())
        message = str(ctx.exception)
        self.assertIn("matchCount=0", message)
        # The refusal names what it saw, including the substring candidates.
        self.assertIn("GF Thin Plate (old, 14 rows)", message)
        self.assertEqual(page.locators[selectors.TAB_BAR_TAB].clicks, [])

    def test_export_refuses_a_matched_tab_without_a_data_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = FakePage(tabs=self._tabs_payload(("", "Part Studio 1")))
            with self.assertRaisesRegex(ValueError, "carries no data-id"):
                self._export(page, tmp)
            self.assertFalse((Path(tmp) / "export1").exists())
        self.assertEqual(page.locators[selectors.TAB_BAR_TAB].clicks, [])

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

    def _write_complete_staging(self, root: Path) -> Path:
        staging = root / "export1"
        staging.mkdir()
        (staging / "model.step").write_text(
            "ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="ascii"
        )
        register_downloaded_browser_step(
            export_id="export1",
            file_name="model.step",
            page_url="https://cad.onshape.com/documents/doc1/w/workspace1/e/element1",
            document_id="doc1",
            workspace_id="workspace1",
            element_id="element1",
            output_root=root,
        )
        return staging

    def test_export_reuses_a_complete_staged_export_instead_of_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = self._write_complete_staging(root)
            before = (staging / "model.step").read_bytes()
            page = FakePage()
            result = self._export(page, tmp)
            after = (staging / "model.step").read_bytes()
            manifest_exists = Path(result["stepManifestPath"]).is_file()
        self.assertTrue(result["exported"])
        self.assertTrue(result["alreadyStaged"])
        self.assertFalse(result["overwriteApplied"])
        # No page was touched: the artifact and manifest were reused as they were.
        self.assertFalse(result["browserActionPerformed"])
        self.assertEqual(before, after)
        self.assertEqual(page.download_timeouts, [])
        self.assertEqual(page.locators[selectors.EXPORT_SUBMIT].clicks, [])
        self.assertTrue(manifest_exists)
        files = {item["fileName"]: item for item in result["stagedArtifacts"]}
        self.assertEqual(set(files), {"model.step", "step-manifest.json"})
        self.assertEqual(files["model.step"]["bytes"], len(before))
        self.assertRegex(files["model.step"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(files["step-manifest.json"]["sha256"], r"^[0-9a-f]{64}$")

    def test_export_refuses_to_reuse_staging_belonging_to_another_target(self):
        """Reuse must be proved by provenance, never assumed from the artifact.

        The manifest records the document/workspace/element it was exported from.
        Without that check a caller passing a mismatched ``element_id`` would be
        handed another document's STEP and told the export succeeded.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = self._write_complete_staging(root)
            before = (staging / "model.step").read_bytes()
            page = FakePage()
            with self.assertRaisesRegex(ValueError, "different document/workspace/element"):
                export_browser_step(
                    page,
                    source_tab="Part Studio 1",
                    export_id="export1",
                    document_id="doc1",
                    workspace_id="workspace1",
                    element_id="element2",  # not the element the manifest recorded
                    output_root=root,
                )
            after = (staging / "model.step").read_bytes()
        # The refusal changed nothing and never touched the page.
        self.assertEqual(before, after)
        self.assertEqual(page.locators[selectors.EXPORT_SUBMIT].clicks, [])
        self.assertEqual(page.download_timeouts, [])

    def test_export_overwrite_replaces_staging_from_another_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_complete_staging(root)
            page = FakePage()
            # The page must really be the NEW target, or the later URL check
            # refuses before the re-export can record its provenance.
            page.url = "https://cad.onshape.com/documents/doc1/w/workspace1/e/element2"
            page.tabs_payload = {
                "tabs": [
                    {
                        "id": "element2",
                        "name": "Part Studio 1",
                        "elementType": "PARTSTUDIO",
                        "active": True,
                    }
                ],
                "hasDocumentTabsToolButton": True,
            }
            result = export_browser_step(
                page,
                source_tab="Part Studio 1",
                export_id="export1",
                document_id="doc1",
                workspace_id="workspace1",
                element_id="element2",
                output_root=root,
                overwrite=True,
            )
            manifest = json.loads(
                Path(result["stepManifestPath"]).read_text(encoding="utf-8")
            )
        self.assertTrue(result["exported"])
        self.assertFalse(result["alreadyStaged"])
        self.assertTrue(result["overwriteApplied"])
        # The replacement records the NEW target, not the old one.
        self.assertEqual(
            manifest["artifact"]["source"]["identifiers"]["elementId"], "element2"
        )

    def test_dry_run_does_not_advertise_a_reuse_that_provenance_forbids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_complete_staging(root)
            matching = plan_browser_step_export(
                source_tab="Part Studio 1",
                export_id="export1",
                output_root=root,
                document_id="doc1",
                workspace_id="workspace1",
                element_id="element1",
            )
            mismatched = plan_browser_step_export(
                source_tab="Part Studio 1",
                export_id="export1",
                output_root=root,
                document_id="doc1",
                workspace_id="workspace1",
                element_id="element2",
            )
            # Without the target ids the plan reports the artifact-level answer and says so.
            unchecked = plan_browser_step_export(
                source_tab="Part Studio 1",
                export_id="export1",
                output_root=root,
            )
        self.assertTrue(matching["stagingProvenanceChecked"])
        self.assertTrue(matching["stagingProvenanceMatches"])
        self.assertTrue(matching["alreadyStaged"])
        self.assertTrue(matching["destinationAvailable"])
        self.assertTrue(mismatched["stagingProvenanceChecked"])
        self.assertFalse(mismatched["stagingProvenanceMatches"])
        self.assertFalse(mismatched["alreadyStaged"])
        self.assertFalse(mismatched["destinationAvailable"])
        self.assertFalse(unchecked["stagingProvenanceChecked"])
        self.assertIsNone(unchecked["stagingProvenanceMatches"])

    def test_partial_staging_is_replaced_when_overwrite_is_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = root / "export1"
            staging.mkdir()
            stale = staging / "model.step"
            stale.write_text("stale partial artifact", encoding="ascii")
            page = FakePage()
            result = export_browser_step(
                page,
                source_tab="Part Studio 1",
                export_id="export1",
                document_id="doc1",
                workspace_id="workspace1",
                element_id="element1",
                output_root=root,
                overwrite=True,
            )
            replaced = stale.read_text(encoding="ascii")
            manifest = json.loads(
                Path(result["stepManifestPath"]).read_text(encoding="utf-8")
            )
        self.assertTrue(result["exported"])
        self.assertFalse(result["alreadyStaged"])
        self.assertTrue(result["overwriteApplied"])
        self.assertNotIn("stale", replaced)
        self.assertIn("ISO-10303-21", replaced)
        self.assertEqual(manifest["artifact"]["path"], "model.step")
        self.assertEqual(
            {item["fileName"] for item in result["stagedArtifacts"]},
            {"model.step", "step-manifest.json"},
        )

    def test_partial_staging_without_overwrite_still_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = root / "export1"
            staging.mkdir()
            stale = staging / "model.step"
            stale.write_text("stale partial artifact", encoding="ascii")
            page = FakePage()
            with self.assertRaisesRegex(ValueError, "staging destination already exists"):
                self._export(page, tmp)
            self.assertEqual(stale.read_text(encoding="ascii"), "stale partial artifact")
            self.assertFalse((staging / "step-manifest.json").exists())
        # The refusal stays pre-flight: no browser action and no download.
        self.assertEqual(page.download_timeouts, [])
        self.assertEqual(page.locators[selectors.EXPORT_SUBMIT].clicks, [])

    def test_dialog_wait_failure_reports_staged_step_and_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            page = FakePage()
            page.locators[selectors.EXPORT_DIALOG] = FailingDialogWaitLocator()
            result = self._export(page, tmp)
            manifest_on_disk = (root / "export1" / "step-manifest.json").is_file()
            # A retry under the SAME export_id now finds the complete staging and
            # reuses it instead of dying on the "destination already exists" raise.
            retry = self._export(FakePage(), tmp)
        self.assertFalse(result["exported"])
        self.assertTrue(result["browserActionPerformed"])
        self.assertEqual(result["failure"]["phase"], "wait_for_dialog_hidden")
        self.assertIn("TargetClosedError", result["failure"]["error"])
        # The dialog never reported itself hidden, but the STEP is on disk and now
        # carries its manifest, so it is a complete, reusable staging.
        self.assertTrue(result["stagingComplete"])
        self.assertTrue(result["alreadyStaged"])
        self.assertTrue(manifest_on_disk)
        self.assertEqual(
            {item["fileName"] for item in result["stagedArtifacts"]},
            {"model.step", "step-manifest.json"},
        )
        self.assertEqual(
            result["recovery"],
            [
                {"action": "retry_new_export_id"},
                {"action": "retry_same_export_id", "requires": "overwrite=true"},
                {"action": "browser_build_geometry_package", "requires": "stagingComplete"},
                {"action": "enable_live_api", "requires": "operator"},
                {"action": "human_export_dialog"},
            ],
        )
        self.assertEqual(result["apiRequests"], 0)
        self.assertFalse(result["bambuIncluded"])
        self.assertTrue(retry["exported"])
        self.assertTrue(retry["alreadyStaged"])

    def test_download_phase_failure_reports_an_incomplete_staging(self):
        class FailingSaveDownload(FakeDownload):
            def save_as(self, path):
                raise RuntimeError("disk went away before the artifact landed")

        with tempfile.TemporaryDirectory() as tmp:
            result = self._export(FakePage(FailingSaveDownload()), tmp)
        self.assertFalse(result["exported"])
        self.assertEqual(result["failure"]["phase"], "save_download")
        self.assertFalse(result["stagingComplete"])
        self.assertEqual(result["stagedArtifacts"], [])
        self.assertEqual(len(result["recovery"]), 5)

    def test_browser_liveness_is_reported_on_success_and_failure_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            success = self._export(FakePage(), tmp)
        with tempfile.TemporaryDirectory() as tmp:
            dead = FakePage()
            dead.locators[selectors.EXPORT_DIALOG] = FailingDialogWaitLocator()
            failure = self._export(dead, tmp)
        for result in (success, failure):
            self.assertIsInstance(result["browserAliveBefore"], bool)
            self.assertIsInstance(result["browserAliveAfter"], bool)
        self.assertTrue(success["browserAliveBefore"])
        self.assertTrue(success["browserAliveAfter"])
        self.assertTrue(failure["browserAliveBefore"])
        self.assertTrue(failure["browserAliveAfter"])

    def test_browser_liveness_probe_reports_a_closed_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._export(FakePage(closed=True), tmp)
        self.assertFalse(result["browserAliveBefore"])
        self.assertFalse(result["browserAliveAfter"])


if __name__ == "__main__":
    unittest.main()
