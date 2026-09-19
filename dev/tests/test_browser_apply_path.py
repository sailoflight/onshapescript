#!/usr/bin/env python3
"""Offline tests for the Part Studio custom-feature apply path.

The apply path used to end in three fixed sleeps (3s, 10s, 15s): slow enough to
make a passing run feel broken, and still too short when a workbench regenerates
slowly. It now waits on bounded browser conditions and reports what it waited
for, and `inserted` means the feature actually appeared in the feature tree
rather than that a click landed.

Everything here is offline: a fake page records the waits and answers the
`evaluate` calls by intent. No browser, no session, no Onshape REST call.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from onshape_browser_mode import actions, interaction, semantic, selectors  # noqa: E402


class FakeItem:
    """One element: a menu row, a dialog button, or a feature-list row."""

    def __init__(self, text: str = "", *, visible: bool = True, page: "FakePage | None" = None,
                 selector: str = "") -> None:
        self.text = text
        self.visible = visible
        self.page = page
        self.selector = selector
        self.click_calls: list[dict] = []
        self.wait_calls: list[dict] = []

    def is_visible(self) -> bool:
        return self.visible

    def inner_text(self) -> str:
        return self.text

    def click(self, **kwargs) -> None:
        self.click_calls.append(kwargs)

    def wait_for(self, **kwargs) -> None:
        self.wait_calls.append(kwargs)
        if self.page is not None:
            self.page.waits.append({"selector": self.selector, **kwargs})
            if self.page.waits_fail_for and self.selector in self.page.waits_fail_for:
                raise TimeoutError(f"{self.selector} never reached state {kwargs.get('state')!r}")


class FakeLocator:
    def __init__(self, items: list[FakeItem], *, page: "FakePage", selector: str) -> None:
        self.items = items
        self.page = page
        self.selector = selector
        self.filter_text: str | None = None

    @property
    def first(self) -> FakeItem:
        return self.nth(0)

    def nth(self, index: int) -> FakeItem:
        if 0 <= index < len(self.items):
            return self.items[index]
        return FakeItem("", page=self.page, selector=self.selector)

    def filter(self, has_text: str = "") -> "FakeLocator":
        self.filter_text = has_text
        filtered = [
            item for item in self.items if str(has_text).lower() in item.text.lower()
        ]
        return FakeLocator(filtered, page=self.page, selector=self.selector)

    def count(self) -> int:
        return len(self.items)


class FakePage:
    """A page that answers `evaluate` by intent and records bounded waits."""

    def __init__(self, *, menu_items=("Bc",), features=None, accept=True,
                 tabs=("Feature Studio 1", "Part Studio 1"), menu_opens=True) -> None:
        self.url = "https://cad.onshape.com/documents/d1/w/w1/e/e1"
        self.menu_items = [FakeItem(text, page=self, selector=selectors.CUSTOM_FEATURE_MENU_ITEM)
                           for text in menu_items]
        self.features = features if features is not None else {
            "headerText": "特征",
            "features": [{"name": "Bc", "isUserFeature": True}],
            "partsText": "零件数 (1) Bc",
        }
        self.accept = accept
        self.tabs = [{"id": f"e{index}", "name": name, "active": index == 1}
                     for index, name in enumerate(tabs)]
        self.menu_opens = menu_opens
        self.waits_fail_for: set[str] = set()
        if not menu_opens:
            # "never opens" means a visibility wait on the dropdown times out.
            self.waits_fail_for.add(selectors.CUSTOM_FEATURE_MENU_ITEM)
        self.waits: list[dict] = []
        self.timeouts: list[int] = []
        self.evaluate_calls: list[str] = []
        self.accept_clicks: list[dict] = []
        self.keyboard = mock.Mock()

    # -- locator surface -------------------------------------------------
    def locator(self, selector: str) -> FakeLocator:
        if selector == selectors.CUSTOM_FEATURE_MENU_ITEM and not self.menu_opens:
            return FakeLocator([], page=self, selector=selector)
        if selector == selectors.CUSTOM_FEATURE_MENU_ITEM:
            return FakeLocator(self.menu_items, page=self, selector=selector)
        if selector == selectors.PARTSTUDIO_FEATURE_ITEM:
            return FakeLocator(
                [FakeItem(str(row.get("name", "")), page=self, selector=selector)
                 for row in self.features.get("features", [])],
                page=self,
                selector=selector,
            )
        return FakeLocator([], page=self, selector=selector)

    def wait_for_timeout(self, milliseconds: int) -> None:
        self.timeouts.append(milliseconds)

    # -- evaluate surface ------------------------------------------------
    def evaluate(self, expression: str, *args):
        self.evaluate_calls.append(expression)
        if args:
            # dismiss_stale_context_menu
            return {"present": False, "blocking": False}
        if "workspace-custom-features button not found" in expression:
            return {"clicked": True}
        if "accept button not found" in expression:
            self.accept_clicks.append({})
            return {"clicked": self.accept} if self.accept else {
                "clicked": False, "reason": "accept button not found",
            }
        if "ns-user-feature" in expression:
            return self.features
        if "os-tab-bar-tab" in expression:
            return {"tabs": self.tabs, "hasDocumentTabsToolButton": False}
        raise AssertionError(f"unexpected evaluate: {expression.strip()[:60]}")


class InsertCustomFeatureTest(unittest.TestCase):
    def apply(self, page: FakePage, **kwargs) -> dict:
        return actions.insert_custom_feature(page, kwargs.pop("feature_name", "Bc"), **kwargs)

    def test_apply_waits_on_conditions_instead_of_fixed_sleeps(self) -> None:
        page = FakePage()
        result = self.apply(page)
        self.assertTrue(result["inserted"])
        self.assertTrue(result["listed"])
        self.assertEqual(result["waits"]["menu"]["waited"], True)
        self.assertEqual(result["waits"]["dialog"]["waited"], True)
        self.assertEqual(result["waits"]["regeneration"]["waited"], True)
        # No blind sleep survives on the path.
        self.assertEqual(page.timeouts, [])
        # Each wait is bounded and uses a real selector from selectors.py.
        by_selector = {wait["selector"]: wait for wait in page.waits}
        self.assertEqual(
            set(by_selector),
            {selectors.CUSTOM_FEATURE_MENU_ITEM, selectors.FEATURE_DIALOG_OK,
             selectors.PARTSTUDIO_FEATURE_ITEM},
        )
        self.assertEqual(
            by_selector[selectors.CUSTOM_FEATURE_MENU_ITEM]["timeout"],
            actions.CUSTOM_FEATURE_MENU_TIMEOUT_MS,
        )
        self.assertEqual(
            by_selector[selectors.FEATURE_DIALOG_OK]["timeout"],
            actions.FEATURE_DIALOG_TIMEOUT_MS,
        )
        self.assertEqual(
            by_selector[selectors.PARTSTUDIO_FEATURE_ITEM]["timeout"],
            actions.PARTSTUDIO_REGENERATE_TIMEOUT_MS,
        )
        # The regeneration wait is scoped to this feature, not any user feature.
        self.assertEqual(by_selector[selectors.PARTSTUDIO_FEATURE_ITEM]["state"], "visible")
        self.assertEqual(len(page.accept_clicks), 1)

    def test_all_waits_are_longer_than_the_sleeps_they_replaced(self) -> None:
        self.assertGreater(actions.CUSTOM_FEATURE_MENU_TIMEOUT_MS, 3_000)
        self.assertGreater(actions.FEATURE_DIALOG_TIMEOUT_MS, 10_000)
        self.assertGreater(actions.PARTSTUDIO_REGENERATE_TIMEOUT_MS, 15_000)

    def test_dropdown_that_never_opens_is_an_explicit_non_success(self) -> None:
        page = FakePage(menu_opens=False)
        result = self.apply(page)
        self.assertFalse(result["inserted"])
        self.assertIn("did not open", result["reason"])
        self.assertNotIn("waits", result)
        self.assertFalse(result["menu"]["waited"])
        # Nothing was clicked inside a dropdown that never appeared.
        self.assertEqual([item.click_calls for item in page.menu_items], [[]])
        self.assertEqual(page.accept_clicks, [])

    def test_feature_name_must_match_exactly_one_menu_item(self) -> None:
        for items, expected in ((("Bc", "Bc"), "exactly one"), (("Other",), "exactly one")):
            page = FakePage(menu_items=items)
            result = self.apply(page)
            self.assertFalse(result["inserted"])
            self.assertIn(expected, result["reason"])
            self.assertEqual(page.accept_clicks, [])

    def test_a_rejected_accept_is_never_reported_as_inserted(self) -> None:
        page = FakePage(accept=False)
        result = self.apply(page)
        self.assertFalse(result["inserted"])
        self.assertFalse(result["accepted"]["clicked"])
        self.assertTrue(result["listed"])

    def test_a_feature_that_never_regenerates_is_reported_as_not_listed(self) -> None:
        page = FakePage(features={"headerText": "", "features": [], "partsText": ""})
        page.waits_fail_for = {selectors.PARTSTUDIO_FEATURE_ITEM}
        result = self.apply(page)
        self.assertFalse(result["inserted"])
        self.assertFalse(result["listed"])
        self.assertFalse(result["waits"]["regeneration"]["waited"])
        self.assertTrue(result["accepted"]["clicked"])

    def test_part_studio_tab_must_exist(self) -> None:
        page = FakePage(tabs=("Feature Studio 1",))
        result = self.apply(page, part_studio_tab="Part Studio 9")
        self.assertFalse(result["inserted"])
        self.assertIn("not found", result["reason"])

    def test_tab_switch_waits_for_the_feature_panel(self) -> None:
        page = FakePage()
        result = self.apply(page, part_studio_tab="Part Studio 1")
        self.assertTrue(result["inserted"])
        self.assertIn(".features-title", [wait["selector"] for wait in page.waits])


class FeatureListedTest(unittest.TestCase):
    def test_matching_requires_a_user_feature_and_a_non_empty_name(self) -> None:
        features = {"features": [
            {"name": "Bc (custom)", "isUserFeature": True},
            {"name": "BcDefault", "isUserFeature": False},
        ]}
        self.assertTrue(actions.feature_listed(features, "bc"))
        self.assertTrue(actions.feature_listed(features, "BC (CUSTOM)"))
        # A default feature whose name contains the text is not the custom feature.
        self.assertFalse(actions.feature_listed(features, "BcDefault"))
        # An empty name is never a match, even when user features exist.
        self.assertFalse(actions.feature_listed(features, ""))
        self.assertFalse(actions.feature_listed(features, "   "))
        self.assertFalse(actions.feature_listed(features, None))

    def test_malformed_feature_lists_are_not_matches(self) -> None:
        self.assertFalse(actions.feature_listed(None, "Bc"))
        self.assertFalse(actions.feature_listed({}, "Bc"))
        self.assertFalse(actions.feature_listed({"features": "Bc"}, "Bc"))
        self.assertFalse(actions.feature_listed({"features": [None, 5]}, "Bc"))


class BuildPartAcceptanceTest(unittest.TestCase):
    """`built` needs all three signals: the insert, the feature row, a part."""

    def build(self, inserted: dict, features: dict) -> dict:
        with mock.patch.object(actions, "insert_custom_feature", return_value=inserted), \
             mock.patch.object(actions, "read_partstudio_features", return_value=features):
            return semantic.build_part(mock.Mock(), "Bc")

    def test_built_requires_the_insert_the_feature_and_a_part(self) -> None:
        result = self.build(
            {"inserted": True, "features": {"features": [{"name": "Bc", "isUserFeature": True}],
                                            "partsText": "零件数 (2) a  b"}},
            {},
        )
        self.assertTrue(result["built"])
        self.assertTrue(result["featurePresent"])
        self.assertEqual(result["parts"], 2)

    def test_zero_parts_is_not_built(self) -> None:
        result = self.build(
            {"inserted": True, "features": {"features": [{"name": "Bc", "isUserFeature": True}],
                                            "partsText": "零件数 (0)"}},
            {},
        )
        self.assertFalse(result["built"])
        self.assertTrue(result["featurePresent"])
        self.assertEqual(result["parts"], 0)

    def test_a_failed_insert_is_not_built_even_when_parts_exist(self) -> None:
        result = self.build(
            {"inserted": False, "reason": "dropdown did not open",
             "features": {"features": [], "partsText": "零件数 (3) a  b  c"}},
            {},
        )
        self.assertFalse(result["built"])
        self.assertFalse(result["featurePresent"])
        self.assertIn("did not open", result["insert"]["reason"])

    def test_a_missing_feature_row_is_not_built(self) -> None:
        result = self.build(
            {"inserted": True, "features": {"features": [{"name": "Other", "isUserFeature": True}],
                                            "partsText": "零件数 (1) x"}},
            {},
        )
        self.assertFalse(result["built"])
        self.assertFalse(result["featurePresent"])

    def test_a_feature_row_without_a_part_count_is_not_built(self) -> None:
        result = self.build(
            {"inserted": True, "features": {"features": [{"name": "Bc", "isUserFeature": True}],
                                            "partsText": "无可读文本"}},
            {},
        )
        self.assertFalse(result["built"])
        self.assertTrue(result["featurePresent"])


class WaitConditionTextFilterTest(unittest.TestCase):
    """`text` must narrow a visibility wait to the matching element."""

    class _Locator:
        def __init__(self, *, fails: bool = False) -> None:
            self.fails = fails
            self.filter_text: str | None = None
            self.wait_calls: list[dict] = []

        def filter(self, has_text: str = "") -> "WaitConditionTextFilterTest._Locator":
            self.filter_text = has_text
            return self

        def nth(self, _index: int) -> "WaitConditionTextFilterTest._Locator":
            return self

        @property
        def first(self) -> "WaitConditionTextFilterTest._Locator":
            return self

        def wait_for(self, **kwargs) -> None:
            self.wait_calls.append(kwargs)
            if self.fails:
                raise TimeoutError("never visible")

    class _Page:
        def __init__(self, locator) -> None:
            self._locator = locator
            self.url = "https://cad.onshape.com/documents/d1/w/w1/e/e1"

        def locator(self, _selector: str):
            return self._locator

    def test_text_filters_the_target_and_is_reported(self) -> None:
        locator = self._Locator()
        result = interaction.wait_for_condition(
            self._Page(locator), condition="visible", selector=".os-list-item",
            text="Bc", timeout_ms=1_234,
        )
        self.assertTrue(result["waited"])
        self.assertEqual(result["targetText"], "Bc")
        self.assertEqual(locator.filter_text, "Bc")
        self.assertEqual(locator.wait_calls, [{"state": "visible", "timeout": 1_234}])

    def test_without_text_the_first_match_is_waited_on_unchanged(self) -> None:
        locator = self._Locator()
        result = interaction.wait_for_condition(
            self._Page(locator), condition="attached", selector=".os-list-item", timeout_ms=500,
        )
        self.assertTrue(result["waited"])
        self.assertNotIn("targetText", result)
        self.assertIsNone(locator.filter_text)

    def test_a_timeout_is_returned_as_data(self) -> None:
        locator = self._Locator(fails=True)
        result = interaction.wait_for_condition(
            self._Page(locator), condition="visible", selector=".os-list-item",
            text="Bc", timeout_ms=500,
        )
        self.assertFalse(result["waited"])
        self.assertIn("TimeoutError", result["error"])
        self.assertIn("elapsedMs", result)

    def test_a_missing_selector_still_raises(self) -> None:
        with self.assertRaises(ValueError):
            interaction.wait_for_condition(self._Page(self._Locator()), condition="visible")


if __name__ == "__main__":
    unittest.main()
