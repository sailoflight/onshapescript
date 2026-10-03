#!/usr/bin/env python3
"""Offline tests for the browser-leg STEP import (zero quota, no Playwright).

The live Import dialog has never been opened by this code, so what is tested here is the part that can
be: the PLAN's honesty, and the VERDICT RULE. The rule has one invariant worth stating twice -- a
finished translation is not an imported element, and the dialog's own UI is not evidence -- so the
tests drive fakes that can report a changed row list, an unchanged one, two new rows, or a failed read,
and assert that only the first of those ever becomes ``imported=True``.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from onshape_browser_mode import selectors, step_import  # noqa: E402


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


class FakePause:
    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.calls: list[int] = []

    def __call__(self, milliseconds: int) -> None:
        self.calls.append(milliseconds)
        self.clock.now += milliseconds / 1000.0


class FakeLocator:
    def __init__(self, page: "FakePage", selector: str) -> None:
        self.page = page
        self.selector = selector

    @property
    def first(self) -> "FakeLocator":
        return self

    def wait_for(self, state: str | None = None, timeout: int | None = None) -> bool:
        self.page.waits.append({"selector": self.selector, "state": state})
        if not self.page.present(self.selector):
            raise RuntimeError(f"locator not present: {self.selector}")
        return True

    def click(self, **kwargs) -> None:
        self.page.clicks.append(self.selector)
        if not self.page.present(self.selector):
            raise RuntimeError(f"cannot click missing locator: {self.selector}")

    def set_input_files(self, path: str) -> None:
        self.page.input_files.append({"selector": self.selector, "path": path})
        if not self.page.file_input_attachable:
            raise RuntimeError("file input is not attachable")


class FakePage:
    """A page whose proof-row reads are scripted, so each verdict path is reachable."""

    def __init__(
        self,
        *,
        tab_reads: list = None,
        feature_reads: list = None,
        entry_present: bool = True,
        file_input_attachable: bool = True,
        raise_on_read_after: int | None = None,
    ) -> None:
        self.url = "https://cad.onshape.com/documents/did/w/wid/e/eid"
        self.tab_reads = list(tab_reads or [])
        self.feature_reads = list(feature_reads or [])
        self.entry_present = entry_present
        self.file_input_attachable = file_input_attachable
        self.raise_on_read_after = raise_on_read_after
        self.evaluate_calls = 0
        self.clicks: list[str] = []
        self.waits: list[dict] = []
        self.input_files: list[dict] = []

    def present(self, selector: str) -> bool:
        if selector.startswith("text="):
            return self.entry_present
        if selector == selectors.IMPORT_FILE_INPUT or selector == "input[type=file]":
            return True
        if selector == selectors.IMPORT_SUBMIT:
            return True
        return True

    def get_by_text(self, text: str, exact: bool = False) -> FakeLocator:
        return FakeLocator(self, f"text={text}")

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self, selector)

    def evaluate(self, script: str):
        self.evaluate_calls += 1
        index = self.evaluate_calls - 1
        if self.raise_on_read_after is not None and index >= self.raise_on_read_after:
            raise RuntimeError("page read failed")
        if "os-tab-bar-tab" in script:
            reads = self.tab_reads
        else:
            reads = self.feature_reads
        if not reads:
            return []
        if index < len(reads):
            return reads[index]
        return reads[-1]


def _source(tmp: Path, name: str = "handoff.step") -> Path:
    path = tmp / name
    path.write_bytes(b"ISO-10303-21;\nHEADER;\nENDSEC;\nEND-ISO-10303-21;\n")
    return path


class PlanTest(unittest.TestCase):
    def test_plan_states_that_a_translation_is_not_a_landing(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = step_import.plan_browser_step_import(source_path=_source(Path(tmp)))
        self.assertTrue(plan["dryRun"])
        self.assertEqual(plan["operation"], "browser-step-import")
        self.assertEqual(plan["network"], "browser")
        self.assertEqual(plan["estimatedApiRequests"], 0)
        self.assertEqual(plan["maxApiRequests"], 0)
        self.assertTrue(plan["mutating"])
        self.assertIn("exactly one new tab row", plan["landingProof"]["rule"])
        self.assertIn(selectors.TAB_BAR_TAB, plan["landingProof"]["reads"])

    def test_plan_names_the_selectors_it_is_not_allowed_to_trust(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = step_import.plan_browser_step_import(source_path=_source(Path(tmp)))
        live = plan["liveAcceptance"]
        self.assertEqual(live["ledger"], step_import.LEDGER)
        self.assertEqual(live["checks"], list(step_import.LEDGER_CHECKS))
        self.assertEqual(live["status"], "pending-live-verification")
        self.assertEqual(set(live["unverifiedSelectors"]), {"importEntryLabels", "dialog", "fileInput", "submit"})
        # The proof anchors must NOT be in the unverified set: that separation is the whole design.
        self.assertNotIn("tabRow", live["unverifiedSelectors"])
        self.assertNotIn("userFeatureRow", live["unverifiedSelectors"])

    def test_source_facts_are_measured_locally(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _source(Path(tmp))
            plan = step_import.plan_browser_step_import(source_path=path)
            size = path.stat().st_size
        source = plan["source"]
        self.assertEqual(source["formatName"], "STEP")
        self.assertEqual(source["mediaType"], "model/step")
        self.assertEqual(source["byteCount"], size)
        self.assertFalse(source["sha256Stable"])
        self.assertEqual(len(source["sha256"]), 64)

    def test_non_step_sources_and_bad_arguments_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp) / "model.igs"
            other.write_bytes(b"x")
            with self.assertRaisesRegex(ValueError, "step or .stp"):
                step_import.plan_browser_step_import(source_path=other)
            with self.assertRaises(FileNotFoundError):
                step_import.plan_browser_step_import(source_path=Path(tmp) / "nope.step")
            with self.assertRaisesRegex(ValueError, "mode must be"):
                step_import.plan_browser_step_import(source_path=_source(Path(tmp)), mode="append")
            with self.assertRaisesRegex(ValueError, "timeout_ms"):
                step_import.plan_browser_step_import(source_path=_source(Path(tmp)), timeout_ms=10)
            with self.assertRaisesRegex(ValueError, "requires target_tab"):
                step_import.plan_browser_step_import(source_path=_source(Path(tmp)), mode="into-part-studio")
            with self.assertRaisesRegex(ValueError, "requires document_id"):
                step_import.plan_browser_step_import(
                    source_path=_source(Path(tmp)), mode="into-part-studio", target_tab="Part Studio 1"
                )
            with self.assertRaisesRegex(ValueError, "opaque identifier"):
                step_import.plan_browser_step_import(
                    source_path=_source(Path(tmp)), document_id="not an id"
                )


class ImportTest(unittest.TestCase):
    def _run(self, page: FakePage, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            clock = FakeClock()
            return step_import.import_browser_step(
                page,
                source_path=_source(Path(tmp)),
                pause=FakePause(clock),
                now=clock,
                timeout_ms=3000,
                **kwargs,
            )

    def test_one_new_tab_is_a_proven_import(self):
        page = FakePage(
            tab_reads=[
                [{"name": "Part Studio 1", "elementId": "eid1"}],
                [{"name": "Part Studio 1", "elementId": "eid1"}, {"name": "handoff", "elementId": "eid2"}],
            ]
        )
        result = self._run(page)
        self.assertTrue(result["imported"])
        self.assertEqual(result["reason"], "new_tab_landed")
        self.assertEqual(result["newElement"], {"name": "handoff", "elementId": "eid2"})
        self.assertEqual(result["spentQuota"], 0)
        self.assertEqual(result["spentApiRequests"], 0)
        self.assertEqual(page.input_files[0]["path"].endswith("handoff.step"), True)

    def test_an_unchanged_row_list_never_reads_as_success(self):
        page = FakePage(tab_reads=[[{"name": "Part Studio 1", "elementId": "eid1"}]])
        result = self._run(page)
        self.assertFalse(result["imported"])
        self.assertEqual(result["reason"], "no_new_element")
        self.assertEqual(result["translationCompleted"], "unknown")
        self.assertIn("may still be running", result["detail"])

    def test_two_new_rows_are_refused_rather_than_guessed(self):
        page = FakePage(
            tab_reads=[
                [{"name": "A", "elementId": "eid1"}],
                [{"name": "A", "elementId": "eid1"}, {"name": "B", "elementId": "eid2"},
                 {"name": "C", "elementId": "eid3"}],
            ]
        )
        result = self._run(page)
        self.assertFalse(result["imported"])
        self.assertEqual(result["reason"], "ambiguous_new_elements")

    def test_a_failed_after_read_is_not_a_success(self):
        page = FakePage(
            tab_reads=[
                [{"name": "A", "elementId": "eid1"}],
                [{"name": "A", "elementId": "eid1"}, {"name": "B", "elementId": "eid2"}],
            ],
            raise_on_read_after=1,
        )
        result = self._run(page)
        self.assertFalse(result["imported"])
        self.assertEqual(result["reason"], "element_read_failed")
        self.assertIn("page read failed", result["detail"])

    def test_a_failed_before_read_refuses_before_touching_the_page(self):
        page = FakePage(tab_reads=[], raise_on_read_after=0)
        result = self._run(page)
        self.assertEqual(result["reason"], "before_read_failed")
        self.assertEqual(page.clicks, [], "nothing may be clicked when landing cannot be judged")
        self.assertEqual(page.input_files, [])

    def test_a_missing_import_entry_reports_the_page_facts(self):
        page = FakePage(tab_reads=[[{"name": "Part Studio 1", "elementId": "eid1"}]], entry_present=False)
        result = self._run(page)
        self.assertEqual(result["reason"], "import_entry_missing")
        self.assertFalse(result["importEntry"]["clicked"])
        self.assertEqual(result["pageFacts"]["url"], page.url)
        self.assertEqual(result["pageFacts"]["tabNames"], ["Part Studio 1"])

    def test_an_unattachable_file_input_is_its_own_failure(self):
        page = FakePage(
            tab_reads=[
                [{"name": "A", "elementId": "eid1"}],
                [{"name": "A", "elementId": "eid1"}, {"name": "B", "elementId": "eid2"}],
            ],
            file_input_attachable=False,
        )
        result = self._run(page)
        self.assertEqual(result["reason"], "file_input_missing")
        self.assertFalse(result["imported"])
        self.assertEqual(result["importEntry"]["clicked"], True)

    def test_into_part_studio_without_a_name_match_is_unproven_not_true(self):
        page = FakePage(
            feature_reads=[["Base"], ["Base", "导入 1"]],
        )
        result = self._run(page, mode="into-part-studio", target_tab="Part Studio 1", document_id="did1")
        self.assertIsNone(result["imported"])
        self.assertEqual(result["reason"], "landing_unproven")
        matched = self._run(
            FakePage(feature_reads=[["Base"], ["Base", "导入 1"]]),
            mode="into-part-studio",
            target_tab="Part Studio 1",
            document_id="did1",
            expect_feature_name="导入",
        )
        self.assertTrue(matched["imported"])
        self.assertEqual(matched["reason"], "feature_row_matched")

    def test_into_part_studio_with_a_wrong_name_is_a_mismatch(self):
        page = FakePage(feature_reads=[["Base"], ["Base", "导入 1"]])
        result = self._run(
            page,
            mode="into-part-studio",
            target_tab="Part Studio 1",
            document_id="did1",
            expect_feature_name="fillet",
        )
        self.assertFalse(result["imported"])
        self.assertEqual(result["reason"], "feature_row_mismatch")

    def test_the_poll_is_bounded_by_the_injected_clock(self):
        clock = FakeClock()
        page = FakePage(tab_reads=[[{"name": "A", "elementId": "eid1"}]])
        with tempfile.TemporaryDirectory() as tmp:
            result = step_import.import_browser_step(
                page,
                source_path=_source(Path(tmp)),
                pause=FakePause(clock),
                now=clock,
                timeout_ms=2000,
            )
        self.assertFalse(result["imported"])
        self.assertLessEqual(result["polls"]["reads"], 5)


class RegisterTest(unittest.TestCase):
    def test_only_a_true_verdict_can_be_registered(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "imported=True"):
                step_import.register_imported_browser_step(
                    import_id="imp1", result={"imported": False}, document_id="did1", workspace_id="wid1",
                    output_root=Path(tmp),
                )

    def test_a_registered_manifest_carries_what_was_not_proven(self):
        result = {
            "imported": True,
            "reason": "new_tab_landed",
            "translationCompleted": "assumed",
            "source": {"sha256": "ab" * 32, "path": "/tmp/handoff.step"},
            "target": {"tab": None},
            "newElement": {"name": "handoff", "elementId": "eid2"},
            "landingProof": {"mode": "new-tab"},
            "pageFacts": {"url": "https://cad.onshape.com/..."},
            "unverifiedSelectors": ["dialog", "fileInput"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            out = step_import.register_imported_browser_step(
                import_id="imp1", result=result, document_id="did1", workspace_id="wid1",
                output_root=Path(tmp),
            )
            manifest = json.loads(Path(out["manifestPath"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["artifactType"], "imported-browser-step")
        self.assertEqual(manifest["provenance"]["spentQuota"], 0)
        self.assertEqual(manifest["provenance"]["unverifiedSelectors"], ["dialog", "fileInput"])
        self.assertEqual(manifest["verdict"]["translationCompleted"], "assumed")

    def test_registering_twice_is_refused(self):
        result = {"imported": True, "reason": "new_tab_landed", "target": {}, "source": {}}
        with tempfile.TemporaryDirectory() as tmp:
            step_import.register_imported_browser_step(
                import_id="imp1", result=result, document_id="did1", workspace_id="wid1",
                output_root=Path(tmp),
            )
            with self.assertRaisesRegex(ValueError, "already exists"):
                step_import.register_imported_browser_step(
                    import_id="imp1", result=result, document_id="did1", workspace_id="wid1",
                    output_root=Path(tmp),
                )


if __name__ == "__main__":
    unittest.main()
