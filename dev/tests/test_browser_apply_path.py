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

import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from onshape_browser_mode import actions, interaction, semantic, selectors, transactions  # noqa: E402


class FakeItem:
    """One element: a menu row, a dialog button, or a feature-list row."""

    def __init__(self, text: str = "", *, visible: bool = True, page: "FakePage | None" = None,
                 selector: str = "", label: str = "") -> None:
        self.text = text
        self.visible = visible
        self.page = page
        self.selector = selector
        # A workspace row renders a two-letter Feature Studio badge before the
        # label, so its innerText is "Bf\nBounded fillet" while the NAME lives
        # in the `.tool-label` child. `label` models that child; "" models a row
        # with no label element, which is what the text fallback must handle.
        self.label = label
        self.click_calls: list[dict] = []
        self.wait_calls: list[dict] = []

    def is_visible(self) -> bool:
        return self.visible

    def inner_text(self) -> str:
        return self.text

    def locator(self, selector: str) -> "FakeLocator":
        if selector == selectors.CUSTOM_FEATURE_MENU_LABEL and self.label:
            return FakeLocator(
                [FakeItem(self.label, page=self.page, selector=selector)],
                page=self.page,
                selector=selector,
            )
        return FakeLocator([], page=self.page, selector=selector)

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

    def __init__(self, *, menu_items=("Bc",), menu_labels=None, features=None, accept=True,
                 tabs=("Feature Studio 1", "Part Studio 1"), menu_opens=True,
                 features_before_insert=None, features_after_reload=None,
                 reload_fails=False) -> None:
        self.url = "https://cad.onshape.com/documents/d1/w/w1/e/e1"
        labels = list(menu_labels) if menu_labels is not None else [""] * len(menu_items)
        self.menu_items = [
            FakeItem(text, page=self, selector=selectors.CUSTOM_FEATURE_MENU_ITEM,
                     label=labels[index])
            for index, text in enumerate(menu_items)
        ]
        # `features_before_insert` is the Part Studio BEFORE the click (the commit
        # baseline); `features` is the DOM after the accept click; a reload may
        # then reveal `features_after_reload`. Modelling the three separately is
        # what lets a test tell "the row this call created" from "a row that was
        # already there".
        self.features_before_insert = features_before_insert if features_before_insert is not None else {
            "headerText": "特征 (0)",
            "features": [],
            "partsText": "零件数 (0)",
        }
        self.inserted_features = features if features is not None else {
            "headerText": "特征",
            "features": [{"name": "Bc", "isUserFeature": True}],
            "partsText": "零件数 (1) Bc",
        }
        self.features = self.features_before_insert
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
        # The commit-verify reload: `features_after_reload` models the workspace
        # truth a reload reveals (None keeps the post-insert list), and
        # `reload_fails` models a navigation that never completes.
        self.features_after_reload = features_after_reload
        self.reload_fails = reload_fails
        self.reload_calls: list[dict] = []
        self.load_states: list[dict] = []
        self.wait_function_calls: list[dict] = []
        self.never_satisfied_minimum: int | None = None

    # -- reload surface (the commit-verify step) -------------------------
    def reload(self, **kwargs) -> None:
        self.reload_calls.append(kwargs)
        if self.reload_fails:
            raise RuntimeError("navigation interrupted")
        if self.features_after_reload is not None:
            self.features = self.features_after_reload

    def wait_for_load_state(self, state: str = "load", **kwargs) -> None:
        self.load_states.append({"state": state, **kwargs})

    # -- in-page count predicate -----------------------------------------
    def wait_for_function(
        self,
        expression: str,
        *,
        arg=None,
        timeout=None,
        polling=None,
    ) -> bool:
        """Mirror the real signature: Playwright makes ``arg`` keyword-only.

        Getting this wrong live is exactly how the first count-based wait
        shipped a ``TypeError`` (2026-09-20); the double must not be more
        permissive than the client it stands in for.
        """
        self.wait_function_calls.append(
            {
                "expression": expression,
                "arg": arg,
                "timeout": timeout,
                "polling": polling,
            }
        )
        minimum = int((arg or {}).get("minimum", 1))
        if self.never_satisfied_minimum is not None and minimum >= self.never_satisfied_minimum:
            raise TimeoutError(f"row count never reached {minimum}")
        # Two different in-page predicates reach this method, and the double
        # dispatches on the same thing the page does: which rows the JS counts.
        # `ns-user-feature` is the user-row count (regeneration, survival);
        # anything else is the panel-readiness row count, which includes the
        # default planes, the part list and the count markers.
        if "ns-user-feature" in expression:
            wanted = str((arg or {}).get("text", "")).strip().lower()
            seen = self._matching_rows(wanted)
        else:
            seen = len(self.features.get("features", []))
        if seen >= minimum:
            return True
        raise TimeoutError(f"row count never reached {minimum}")

    def _matching_rows(self, wanted: str = "bc") -> int:
        """Matching user rows in the current list, mirroring the JS predicate."""
        rows = 0
        for item in self.features.get("features", []):
            if not item.get("isUserFeature"):
                continue
            text = str(item.get("name", "")).lower()
            if not wanted or wanted in text:
                rows += 1
        return rows

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
            if not self.accept:
                return {"clicked": False, "reason": "accept button not found"}
            # A landed accept makes the new row appear in the workbench DOM.
            self.features = self.inserted_features
            return {"clicked": True}
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
        features_read = 0  # the default fake page starts with no custom features
        result = self.apply(page)
        self.assertTrue(result["inserted"])
        self.assertTrue(result["listed"])
        self.assertEqual(result["waits"]["menu"]["waited"], True)
        self.assertEqual(result["waits"]["dialog"]["waited"], True)
        self.assertEqual(result["waits"]["regeneration"]["waited"], True)
        # No blind sleep survives on the path.
        self.assertEqual(page.timeouts, [])
        # Each bounded wait uses a real selector from selectors.py.
        by_selector = {wait["selector"]: wait for wait in page.waits}
        self.assertEqual(
            set(by_selector),
            {selectors.CUSTOM_FEATURE_MENU_ITEM, selectors.FEATURE_DIALOG_OK},
        )
        self.assertEqual(
            by_selector[selectors.CUSTOM_FEATURE_MENU_ITEM]["timeout"],
            actions.CUSTOM_FEATURE_MENU_TIMEOUT_MS,
        )
        self.assertEqual(
            by_selector[selectors.FEATURE_DIALOG_OK]["timeout"],
            actions.FEATURE_DIALOG_TIMEOUT_MS,
        )
        self.assertEqual(len(page.accept_clicks), 1)
        # Two in-page count waits (regeneration, then survival), both asking for
        # one row more than the baseline, each on its own adaptive budget (the
        # double reports one custom feature, so the budget is base + 1 step).
        self.assertEqual(
            [call["timeout"] for call in page.wait_function_calls],
            [
                actions.partstudio_wait_budget_ms(
                    actions.PARTSTUDIO_REGENERATE_WAIT, features_read
                ),
                actions.partstudio_wait_budget_ms(
                    actions.PARTSTUDIO_RELOAD_WAIT, features_read
                ),
            ],
        )
        self.assertEqual(
            [call["arg"]["minimum"] for call in page.wait_function_calls], [1, 1]
        )
        self.assertEqual(result["baselineRows"], 0)
        self.assertEqual(
            result["budgets"],
            {
                "customFeaturesRead": features_read,
                "regenerationMs": page.wait_function_calls[0]["timeout"],
                "commitSurvivalMs": page.wait_function_calls[1]["timeout"],
            },
        )
        # And the insert is confirmed by exactly one bounded reload.
        self.assertEqual(
            page.reload_calls, [{"wait_until": "commit", "timeout": 15000}]
        )
        self.assertEqual(
            page.load_states, [{"state": "domcontentloaded", "timeout": 15000}]
        )

    def test_the_wait_budgets_grow_with_the_custom_feature_count(self) -> None:
        """A bigger element needs a bigger post-insert budget.

        The live measurement (5 custom features, 18 431 ms of a fixed 30 000 ms
        budget) is the reason: the same reload on a Part Studio with 40 custom
        features spends far more, and a fixed budget would call a committed
        feature missing.
        """
        many = [
            {"name": f"Sr Spiral ridge {index}", "isUserFeature": True}
            for index in range(1, 41)
        ]
        before = {
            "headerText": "特征 (45)",
            "features": many + [{"name": "Origin", "isUserFeature": False}],
            "partsText": "零件数 (40)",
        }
        page = FakePage(features_before_insert=before)
        result = self.apply(page)
        self.assertTrue(result["inserted"])
        self.assertEqual(result["budgets"]["customFeaturesRead"], 40)
        self.assertEqual(result["budgets"]["regenerationMs"], 110_000)
        self.assertEqual(result["budgets"]["commitSurvivalMs"], 350_000)
        self.assertEqual(
            [call["timeout"] for call in page.wait_function_calls],
            [result["budgets"]["regenerationMs"], result["budgets"]["commitSurvivalMs"]],
        )

    def test_an_unreadable_feature_count_keeps_the_previous_fixed_budget(self) -> None:
        """A read taken mid-render must not shorten either wait."""
        page = FakePage(
            features_before_insert={"headerText": "", "features": None, "partsText": ""}
        )
        result = self.apply(page)
        self.assertTrue(result["inserted"])
        self.assertEqual(result["budgets"]["customFeaturesRead"], 0)
        for key in ("regenerationMs", "commitSurvivalMs"):
            self.assertEqual(
                result["budgets"][key], actions.PARTSTUDIO_RELOAD_TIMEOUT_MS
            )

    def test_all_waits_are_longer_than_the_sleeps_they_replaced(self) -> None:
        self.assertGreater(actions.CUSTOM_FEATURE_MENU_TIMEOUT_MS, 3_000)
        self.assertGreater(actions.FEATURE_DIALOG_TIMEOUT_MS, 10_000)
        # A budget with no feature count is the previous fixed budget, so the
        # adaptive change can never shorten a wait.
        for profile in (actions.PARTSTUDIO_REGENERATE_WAIT, actions.PARTSTUDIO_RELOAD_WAIT):
            self.assertGreater(actions.partstudio_wait_budget_ms(profile, 0), 15_000)
            self.assertEqual(
                actions.partstudio_wait_budget_ms(profile, 0),
                actions.PARTSTUDIO_RELOAD_TIMEOUT_MS,
            )

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
        # No accept means no new row, so the pre-click list is still what is there.
        self.assertFalse(result["listed"])
        self.assertIn("accept click did not land", result["reason"])

    def test_row_badge_does_not_hide_the_feature_name(self) -> None:
        """A live row's innerText is "Bf\\nBounded fillet", not the name.

        Measured 2026-09-19: `<div class="tool-initials-icon">Bf</div>` precedes
        `<span class="tool-label">Bounded fillet</span>`, so exact equality
        against the row text never matched a real workspace feature.
        """
        page = FakePage(
            menu_items=("Bf\nBounded fillet",),
            menu_labels=("Bounded fillet",),
            features={
                "headerText": "特征",
                "features": [{"name": "Bf Bounded fillet 1", "isUserFeature": True, "hasError": False}],
                "partsText": "零件数 (1) Spiral ridge cylinder",
            },
        )
        result = actions.insert_custom_feature(page, "Bounded fillet")
        self.assertTrue(result["inserted"])
        self.assertEqual(len(page.menu_items[0].click_calls), 1)
        self.assertEqual(page.accept_clicks, [{}])

    def test_a_row_without_a_label_element_falls_back_to_its_last_line(self) -> None:
        page = FakePage(
            menu_items=("Sr\nSpiral ridge",),
            features={
                "headerText": "特征",
                "features": [{"name": "Sr Spiral ridge 1", "isUserFeature": True, "hasError": False}],
                "partsText": "零件数 (1) Spiral ridge cylinder",
            },
        )
        result = actions.insert_custom_feature(page, "Spiral ridge")
        self.assertTrue(result["inserted"])
        self.assertEqual(len(page.menu_items[0].click_calls), 1)

    def test_a_non_match_reports_the_labels_that_were_available(self) -> None:
        page = FakePage(
            menu_items=("Bf\nBounded fillet", "Bh\nBounded hole"),
            menu_labels=("Bounded fillet", "Bounded hole"),
        )
        result = self.apply(page, feature_name="Bounded chamfer")
        self.assertFalse(result["inserted"])
        self.assertIn("exactly one", result["reason"])
        self.assertEqual(result["available"], ["Bounded fillet", "Bounded hole"])
        self.assertEqual(page.accept_clicks, [])

    def test_two_rows_sharing_a_label_are_never_guessed(self) -> None:
        page = FakePage(
            menu_items=("Bf\nBounded fillet", "Bf\nBounded fillet"),
            menu_labels=("Bounded fillet", "Bounded fillet"),
        )
        result = actions.insert_custom_feature(page, "Bounded fillet")
        self.assertFalse(result["inserted"])
        self.assertIn("exactly one", result["reason"])
        self.assertEqual([item.click_calls for item in page.menu_items], [[], []])
        self.assertEqual(page.accept_clicks, [])

    def test_a_feature_that_never_regenerates_is_reported_as_not_listed(self) -> None:
        page = FakePage(features={"headerText": "", "features": [], "partsText": ""})
        page.never_satisfied_minimum = 1
        result = self.apply(page)
        self.assertFalse(result["inserted"])
        self.assertFalse(result["listed"])
        self.assertFalse(result["waits"]["regeneration"]["waited"])
        self.assertEqual(result["waits"]["regeneration"]["condition"],
                         "user_feature_row_count")
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
        # The switch also waits for the rows and the toolbar button before using
        # either: live 2026-09-20 a switched-to Part Studio produced a
        # "workspace-custom-features button not found" click and a baseline read
        # of 0 rows on an element holding 8 custom features.
        self.assertEqual(result["panelReady"]["condition"], "partstudio_row_count")
        self.assertTrue(result["toolbarReady"]["waited"])
        self.assertTrue(result["toolbarReady"]["selector"].startswith(".tool[title="))

    def test_a_panel_that_rendered_its_rows_is_read_as_the_baseline(self) -> None:
        before = {
            "headerText": "特征 (3)",
            "features": [
                {"name": "默认几何图元", "isUserFeature": False},
                {"name": "Bc 1", "isUserFeature": True},
                {"name": "Bc 2", "isUserFeature": True},
            ],
            "partsText": "零件数 (2)",
        }
        after = {
            "headerText": "特征 (4)",
            "features": [
                {"name": "默认几何图元", "isUserFeature": False},
                {"name": "Bc 1", "isUserFeature": True},
                {"name": "Bc 2", "isUserFeature": True},
                {"name": "Bc 3", "isUserFeature": True},
            ],
            "partsText": "零件数 (3)",
        }
        page = FakePage(
            features_before_insert=before, features=after, features_after_reload=after
        )
        result = self.apply(page, part_studio_tab="Part Studio 1")
        self.assertTrue(result["panelReady"]["waited"])
        self.assertEqual(result["panelReady"]["minimum"], 1)
        # The baseline is the count read AFTER the readiness wait, not a zero.
        self.assertEqual(result["baselineRows"], 2)
        self.assertEqual(result["budgets"]["customFeaturesRead"], 2)
        self.assertEqual(
            [call["arg"]["minimum"] for call in page.wait_function_calls
             if "ns-user-feature" in call["expression"]],
            [3, 3],
        )

    def test_a_panel_that_never_renders_rows_is_reported_not_guessed(self) -> None:
        page = FakePage(
            features_before_insert={"headerText": "", "features": [], "partsText": ""}
        )
        result = self.apply(page, part_studio_tab="Part Studio 1")
        self.assertFalse(result["panelReady"]["waited"])
        self.assertIn("TimeoutError", result["panelReady"]["error"])
        # Readiness is evidence, not a gate: the rest of the transaction ran and
        # the commit check still decided the result.
        self.assertTrue(result["inserted"])
        self.assertTrue(result["commit"]["committed"])

    def test_without_a_tab_switch_no_readiness_wait_is_spent(self) -> None:
        page = FakePage()
        result = self.apply(page)
        self.assertIsNone(result["panelReady"])
        self.assertIsNone(result["toolbarReady"])
        self.assertEqual(
            len([call for call in page.wait_function_calls
                 if "ns-user-feature" in call["expression"]]),
            2,
            "only the regeneration and survival waits",
        )


class AdaptiveWaitBudgetTest(unittest.TestCase):
    """The post-insert budgets scale with the element's recompute load."""

    def test_a_zero_or_unreadable_count_reproduces_the_previous_budget(self) -> None:
        for profile in (actions.PARTSTUDIO_REGENERATE_WAIT, actions.PARTSTUDIO_RELOAD_WAIT):
            for count in (0, None, "nope", -5, []):
                with self.subTest(profile=profile["baseMs"], count=count):
                    self.assertEqual(
                        actions.partstudio_wait_budget_ms(profile, count),
                        actions.PARTSTUDIO_RELOAD_TIMEOUT_MS,
                    )

    def test_the_budget_is_linear_then_capped(self) -> None:
        profile = actions.PARTSTUDIO_RELOAD_WAIT
        self.assertEqual(actions.partstudio_wait_budget_ms(profile, 1), 38_000)
        self.assertEqual(actions.partstudio_wait_budget_ms(profile, 10), 110_000)
        self.assertEqual(
            actions.partstudio_wait_budget_ms(profile, 1_000_000), profile["maxMs"]
        )
        self.assertEqual(actions.partstudio_wait_budget_ms(profile, "7"), 86_000)

    def test_the_measured_live_case_now_has_a_real_margin(self) -> None:
        # The live survival wait needed 18 431 ms of the old fixed 30 000 ms
        # budget on 5 custom features; the scaled budget must be well clear of it.
        budget = actions.partstudio_wait_budget_ms(actions.PARTSTUDIO_RELOAD_WAIT, 5)
        self.assertGreaterEqual(budget, 18_431 * 2)

    def test_count_custom_features_ignores_parts_defaults_and_garbage(self) -> None:
        features = {
            "features": [
                {"name": "默认几何图元", "isUserFeature": False},
                {"name": "Sr Spiral ridge 1", "isUserFeature": True},
                {"name": "Sr Spiral ridge 2", "isUserFeature": True},
                {"name": "零件数 (2)", "isUserFeature": False},
                {"name": "Spiral ridge cylinder", "isUserFeature": False},
                {"name": "曲线数 (2)", "isUserFeature": False},
            ]
        }
        self.assertEqual(actions.count_custom_features(features), 2)
        self.assertEqual(actions.count_custom_features({"features": None}), 0)
        self.assertEqual(actions.count_custom_features(None), 0)
        self.assertEqual(actions.count_custom_features({"features": ["nope", 5]}), 0)


class InsertCommitVerificationTest(unittest.TestCase):
    """``inserted`` means the workspace KEPT the feature, not that a row showed.

    Measured 2026-09-20: a browser-inserted custom feature is absent from the
    element's REST feature list until the page is reloaded, while a REST-added
    feature appears immediately. A visible row is therefore not a commit, and the
    confirming reload is what separates the two. Evidence:
    ``onshape_docs/verification/browser-rest-handoff-2026-09-20.json``.

    Both waits compare a row COUNT against the pre-click baseline, because the
    same day's live run showed the name-only forms failing in both directions: a
    Part Studio that already held two `Spiral ridge` rows satisfied the old
    regeneration wait in 12 ms (false success), and a read taken right after the
    reload saw the title before the rows (false failure, on an insert that had in
    fact committed).
    """

    def test_the_post_reload_read_is_what_the_result_reports(self) -> None:
        after = {
            "headerText": "特征 (1)",
            "features": [{"name": "Bc 1", "isUserFeature": True, "hasError": False}],
            "partsText": "零件数 (1) Bc",
        }
        page = FakePage(features_after_reload=after)
        result = actions.insert_custom_feature(page, "Bc")
        self.assertIs(result["features"], after)
        self.assertTrue(result["commit"]["verified"])
        self.assertTrue(result["commit"]["committed"])
        self.assertTrue(result["inserted"])
        self.assertNotIn("reason", result)

    def test_a_same_named_row_that_was_already_there_is_not_the_new_feature(self) -> None:
        """The live false-success: two existing rows satisfied a name-only wait.

        The Part Studio already showed `Bc 1` and `Bc 2`; the accept lands but the
        workspace keeps nothing, so after the reload the count is still the
        baseline of two and the insert must NOT be reported as committed.
        """
        existing = {
            "headerText": "特征 (7)",
            "features": [
                {"name": "Bc 1", "isUserFeature": True, "hasError": False},
                {"name": "Bc 2", "isUserFeature": True, "hasError": False},
            ],
            "partsText": "零件数 (2) Bc Bc",
        }
        page = FakePage(
            features_before_insert=existing,
            features=existing,
            features_after_reload=existing,
        )
        page.never_satisfied_minimum = 3
        result = actions.insert_custom_feature(page, "Bc")
        self.assertEqual(result["baselineRows"], 2)
        self.assertFalse(result["inserted"])
        self.assertFalse(result["commit"]["committed"])
        self.assertTrue(result["commit"]["verified"])
        self.assertIn("did not survive", result["reason"])

    def test_a_third_row_beyond_two_existing_ones_is_a_commit(self) -> None:
        before = {
            "headerText": "特征 (7)",
            "features": [
                {"name": "Bc 1", "isUserFeature": True},
                {"name": "Bc 2", "isUserFeature": True},
            ],
            "partsText": "零件数 (2) Bc Bc",
        }
        after = {
            "headerText": "特征 (8)",
            "features": [
                {"name": "Bc 1", "isUserFeature": True},
                {"name": "Bc 2", "isUserFeature": True},
                {"name": "Bc 3", "isUserFeature": True},
            ],
            "partsText": "零件数 (3) Bc Bc Bc",
        }
        page = FakePage(
            features_before_insert=before, features=after, features_after_reload=after
        )
        result = actions.insert_custom_feature(page, "Bc")
        self.assertEqual(result["baselineRows"], 2)
        self.assertEqual(
            [call["arg"]["minimum"] for call in page.wait_function_calls], [3, 3]
        )
        self.assertTrue(result["inserted"])

    def test_the_survival_wait_absorbs_a_slow_post_reload_render(self) -> None:
        """The live false-failure: the title renders before the rows.

        A read taken the instant the panel appears is empty. The survival wait is
        what makes that safe, so the check must pass on a page whose rows appear
        only after the wait has been entered.
        """
        before = {"headerText": "特征 (0)", "features": [], "partsText": "零件数 (0)"}
        after = {
            "headerText": "特征 (1)",
            "features": [{"name": "Bc 1", "isUserFeature": True}],
            "partsText": "零件数 (1) Bc",
        }
        page = FakePage(
            features_before_insert=before, features=after, features_after_reload=after
        )
        result = actions.insert_custom_feature(page, "Bc")
        self.assertTrue(result["inserted"])
        self.assertEqual(
            page.wait_function_calls[-1]["arg"]["minimum"], 1,
            "the survival wait must ask for the baseline plus one",
        )
        self.assertEqual(
            page.wait_function_calls[-1]["timeout"],
            actions.partstudio_wait_budget_ms(actions.PARTSTUDIO_RELOAD_WAIT, 0),
        )
        self.assertTrue(result["waits"]["commitSurvival"]["waited"])

    def test_a_row_that_does_not_survive_the_reload_is_not_an_insert(self) -> None:
        page = FakePage(features_after_reload={
            "headerText": "特征 (0)", "features": [], "partsText": "",
        })
        page.never_satisfied_minimum = 1
        result = actions.insert_custom_feature(page, "Bc")
        self.assertFalse(result["inserted"])
        self.assertTrue(result["commit"]["verified"])
        self.assertFalse(result["commit"]["committed"])
        self.assertFalse(result["listed"])
        self.assertIn("did not survive", result["reason"])

    def test_a_failed_reload_is_unverified_rather_than_a_success(self) -> None:
        page = FakePage(reload_fails=True)
        result = actions.insert_custom_feature(page, "Bc")
        self.assertFalse(result["inserted"])
        self.assertFalse(result["commit"]["verified"])
        self.assertFalse(result["commit"]["committed"])
        self.assertIn("did not complete", result["reason"])
        # The pre-reload row survives as evidence, never as acceptance.
        self.assertTrue(result["listed"])
        self.assertIsNone(result["commit"]["survived"])

    def test_a_row_that_never_appeared_is_not_confirmed_with_a_reload(self) -> None:
        page = FakePage(features={"headerText": "", "features": [], "partsText": ""})
        page.never_satisfied_minimum = 1
        result = actions.insert_custom_feature(page, "Bc")
        self.assertFalse(result["inserted"])
        # No reload is spent on a feature the workbench never showed.
        self.assertEqual(page.reload_calls, [])
        self.assertFalse(result["commit"]["verified"])
        self.assertIn("never appeared", result["reason"])

    def test_the_verifier_alone_reports_uncommitted_and_unverified(self) -> None:
        listed = {
            "headerText": "特征 (1)",
            "features": [{"name": "Bc 1", "isUserFeature": True}],
            "partsText": "零件数 (1) Bc",
        }
        page = FakePage(features_before_insert=listed)
        uncommitted = actions.verify_insert_committed(page, "Bc", minimum=1)
        self.assertFalse(uncommitted["verified"])
        self.assertFalse(uncommitted["committed"])
        self.assertIsNone(uncommitted["reload"])
        self.assertEqual(page.reload_calls, [])
        committed = actions.verify_insert_committed(
            page, "Bc", minimum=1, appeared=True
        )
        self.assertTrue(committed["verified"])
        self.assertTrue(committed["committed"])
        self.assertEqual(len(page.reload_calls), 1)
        self.assertTrue(committed["reload"]["reloaded"])
        self.assertTrue(committed["survived"]["waited"])

    def test_the_survival_wait_reports_its_own_timeout_as_evidence(self) -> None:
        page = FakePage()
        page.never_satisfied_minimum = 1
        outcome = actions.wait_for_feature_rows(page, "Bc", 1, 30_000)
        self.assertFalse(outcome["waited"])
        self.assertEqual(outcome["condition"], "user_feature_row_count")
        self.assertEqual(outcome["minimum"], 1)
        self.assertEqual(outcome["timeoutMs"], 30_000)
        self.assertIn("TimeoutError", outcome["error"])
        self.assertEqual(
            page.wait_function_calls[0]["arg"],
            {"selector": selectors.PARTSTUDIO_FEATURE_ITEM, "text": "Bc", "minimum": 1},
        )

    def test_an_errored_row_still_reports_its_error_after_the_reload(self) -> None:
        page = FakePage(features_after_reload={
            "headerText": "特征 (1)",
            "features": [{"name": "Bc 1", "isUserFeature": True, "hasError": True}],
            "partsText": "",
        })
        result = actions.insert_custom_feature(page, "Bc")
        self.assertTrue(result["listed"])
        self.assertTrue(result["errored"])
        self.assertIn("unresolved error", result["reason"])


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
        self.assertTrue(result["featureComputed"])
        self.assertFalse(result["featureError"])
        self.assertEqual(result["reason"], "")
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
        self.assertEqual(result["reason"], "the Part Studio reports no computed parts")

    def test_a_not_computed_row_is_not_built_even_with_parts(self) -> None:
        """The recorded failure mode: a `not-computed` row is still a row, so
        presence alone would report success once other features supply geometry."""
        result = self.build(
            {"inserted": True, "features": {"features": [
                {"name": "Bc Branch cable trophy display 1", "isUserFeature": True,
                 "hasError": True, "className": "os-list-item ns-user-feature not-computed"},
            ], "partsText": "零件数 (132) base  plaqueInsert_blank"}},
            {},
        )
        self.assertFalse(result["built"])
        self.assertTrue(result["featurePresent"])
        self.assertFalse(result["featureComputed"])
        self.assertTrue(result["featureError"])
        self.assertEqual(
            result["featureRows"],
            [{"name": "Bc Branch cable trophy display 1", "hasError": True}],
        )
        self.assertIn("unresolved error", result["reason"])
        self.assertEqual(result["parts"], 132)

    def test_a_failed_insert_is_not_built_even_when_parts_exist(self) -> None:
        result = self.build(
            {"inserted": False, "reason": "dropdown did not open",
             "features": {"features": [], "partsText": "零件数 (3) a  b  c"}},
            {},
        )
        self.assertFalse(result["built"])
        self.assertFalse(result["featurePresent"])
        self.assertIn("did not open", result["reason"])
        self.assertIn("did not open", result["insert"]["reason"])

    def test_a_missing_feature_row_is_not_built(self) -> None:
        result = self.build(
            {"inserted": True, "features": {"features": [{"name": "Other", "isUserFeature": True}],
                                            "partsText": "零件数 (1) x"}},
            {},
        )
        self.assertFalse(result["built"])
        self.assertFalse(result["featurePresent"])
        self.assertIn("is not present in the Feature List", result["reason"])

    def test_a_feature_row_without_a_part_count_is_not_built(self) -> None:
        result = self.build(
            {"inserted": True, "features": {"features": [{"name": "Bc", "isUserFeature": True}],
                                            "partsText": "无可读文本"}},
            {},
        )
        self.assertFalse(result["built"])
        self.assertTrue(result["featurePresent"])
        self.assertEqual(result["reason"], "the Part Studio reports no computed parts")


class FeatureStateTest(unittest.TestCase):
    """Presence and computedness come from one matching rule."""

    def test_presence_and_error_are_separate_signals(self) -> None:
        features = {"features": [
            {"name": "Other", "isUserFeature": True},
            {"name": "Bc 1", "isUserFeature": True},
            {"name": "Bc 2", "isUserFeature": True, "hasError": True},
        ]}
        state = actions.feature_state(features, "Bc")
        self.assertTrue(state["listed"])
        self.assertTrue(state["errored"])
        self.assertEqual(state["names"], ["Bc 1", "Bc 2"])
        self.assertEqual(state["rows"], [
            {"name": "Bc 1", "hasError": False},
            {"name": "Bc 2", "hasError": True},
        ])
        self.assertTrue(actions.feature_listed(features, "Bc"))

    def test_a_clean_row_is_listed_and_not_errored(self) -> None:
        self.assertEqual(
            actions.feature_state(
                {"features": [{"name": "Bc 1", "isUserFeature": True, "hasError": False}]}, "Bc",
            ),
            {
                "listed": True, "errored": False, "names": ["Bc 1"],
                "rows": [{"name": "Bc 1", "hasError": False}],
            },
        )

    def test_default_features_are_not_matches(self) -> None:
        state = actions.feature_state(
            {"features": [{"name": "Bc origin", "isUserFeature": False, "hasError": True}]}, "Bc",
        )
        self.assertFalse(state["listed"])
        self.assertFalse(state["errored"])

    def test_empty_names_and_malformed_lists_are_never_matches(self) -> None:
        for features, name in (
            ({"features": [{"name": "Bc", "isUserFeature": True}]}, ""),
            ({"features": [{"name": "Bc", "isUserFeature": True}]}, "   "),
            ({"features": "Bc"}, "Bc"),
            ({}, "Bc"),
            (None, "Bc"),
            ([{"name": "Bc"}], "Bc"),
            ({"features": [None, "Bc"]}, "Bc"),
        ):
            with self.subTest(features=features, name=name):
                state = actions.feature_state(features, name)
                self.assertFalse(state["listed"])
                self.assertFalse(state["errored"])
                self.assertFalse(actions.feature_listed(features, name))


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


class FakeDialogLocator:
    """Locator double whose counts come from the page's own model of the DOM.

    That is the point: ``read_features`` models what a READ reports and
    ``locator_user_rows`` models what the row locator counts, so a test can make
    the two disagree exactly as they did live on 2026-09-20.
    """

    def __init__(self, page: "FakeDialogPage", selector: str, index: int | None = None) -> None:
        self.page = page
        self.selector = selector
        self.index = index

    def _parameter_key(self) -> str | None:
        match = re.search(r'(?:data-parameter-id|parameter-id|name)="([^"]+)"', self.selector)
        return match.group(1) if match else None

    def count(self) -> int:
        if self.selector == selectors.PS_USER_FEATURE:
            return self.page.locator_user_rows
        if self.selector == selectors.PS_FEATURE_DIALOG:
            return 1 if self.page.dialog_visible else 0
        if self.selector == selectors.PS_FEATURE_DIALOG_ACCEPT:
            return 1
        key = self._parameter_key()
        if key is None or not self.page.locator_sees_parameter:
            return 0
        return 1 if key in self.page.parameter_fields else 0

    def locator(self, selector: str) -> "FakeDialogLocator":
        return FakeDialogLocator(self.page, selector)

    def filter(self, **kwargs: object) -> "FakeDialogLocator":
        return self

    def nth(self, index: int) -> "FakeDialogLocator":
        return FakeDialogLocator(self.page, self.selector, index)

    @property
    def first(self) -> "FakeDialogLocator":
        return self

    def dblclick(self) -> None:
        assert self.index is not None, "the edit path must click a known row index"
        self.page.dblclicks.append(self.index)
        if self.page.dialog_opens:
            self.page.dialog_visible = True

    def wait_for(self, state: str | None = None, timeout: float | None = None) -> bool:
        self.page.dialog_waits.append({"state": state, "timeout": timeout})
        if self.selector == selectors.PS_FEATURE_DIALOG and not self.page.dialog_visible:
            raise TimeoutError("dialog not visible")
        return True

    def fill(self, value: str) -> None:
        key = self._parameter_key()
        self.page.fills.append({"key": key, "value": value})
        if key:
            self.page.dialog_values[key] = str(value)

    def click(self, **kwargs: object) -> None:
        if self.selector == selectors.PS_FEATURE_DIALOG_ACCEPT:
            # Accepting starts a regeneration; the dialog stays on screen until
            # the condition wait observes it gone. Closing it here would make the
            # timeout fallback look like a success.
            self.page.accept_clicks.append(True)

    def is_checked(self) -> bool:
        return False


class FakeDialogPage:
    """Page double for the feature-dialog edit path (offline, no session).

    ``rows`` are the NAMED custom-feature rows in DOM order and ``nameless_rows``
    models the extra ``.os-list-item.ns-user-feature`` node that carries no text.
    Measured live 2026-09-20, that node is on every Part Studio: a READ that drops
    empty names saw 1 and 11 rows where the row locator counted 2 and 12. The
    double therefore holds ONE node list, ``dom_rows``, and answers both the
    enumeration and the locator from it — so a test cannot quietly model the two
    views as different sets again, which is the defect class being pinned here.
    """

    def __init__(
        self,
        *,
        rows: tuple[str, ...] = ("Sr Spiral ridge 5", "Sr Spiral ridge 6", "Sr Spiral ridge 7"),
        nameless_rows: int = 1,
        locator_delta: int = 0,
        panel_renders: bool = True,
        dialog_opens: bool = True,
        dialog_closes: bool = True,
        parameter_fields: tuple[str, ...] = ("baseRadius",),
        locator_sees_parameter: bool = True,
    ) -> None:
        self.rows = list(rows)
        self.nameless_rows = nameless_rows
        # The nameless node sits FIRST, the worst case for a click index computed
        # from a names-only list — which is exactly what the live defect did.
        self.dom_rows = [""] * nameless_rows + list(self.rows)
        # `locator_delta` is the only way to make the two views disagree, and it
        # models a DOM change between the enumeration and the click (a stale read),
        # not the live +1, which was a read-side filter.
        self.locator_user_rows = len(self.dom_rows) + locator_delta
        self.read_features = {
            "headerText": "特征 (%d)" % len(self.rows),
            # A READ filters nameless nodes out; the enumeration does not. Keeping
            # both in the double is what pins that difference.
            "features": [
                {"name": name, "isUserFeature": True, "hasError": False} for name in self.rows
            ],
            "partsText": "零件数 (1)",
            "partItems": [],
        }
        self.panel_renders = panel_renders
        self.dialog_opens = dialog_opens
        self.dialog_closes = dialog_closes
        self.parameter_fields = tuple(parameter_fields)
        self.locator_sees_parameter = locator_sees_parameter
        self.dialog_values = {field: "10 mm" for field in self.parameter_fields}
        self.dialog_visible = False
        self.url = "https://cad.onshape.com/documents/d1/w/w1/e/e1"
        self.dblclicks: list[int] = []
        self.fills: list[dict] = []
        self.accept_clicks: list[bool] = []
        self.dialog_waits: list[dict] = []
        self.wait_calls: list[dict] = []
        #: A fixed sleep here would misreport a successful edit as a failure, so
        #: every sleep is recorded and the accept test asserts this stays empty.
        self.timeouts: list[int] = []
        self.keyboard = mock.Mock()

    def evaluate(self, expression: str, arg: object = None) -> dict:
        if expression == actions._USER_FEATURE_ROWS_JS:
            # Names and count from one node list, nameless nodes included, exactly
            # as `querySelectorAll` returns them.
            return {"count": len(self.dom_rows), "names": list(self.dom_rows)}
        if ".feature-dialog" in expression:
            return dict(self.dialog_values) if self.dialog_visible else {}
        return self.read_features

    def wait_for_function(self, expression: str, *, arg: object = None, timeout: float | None = None,
                          polling: object = None) -> bool:
        self.wait_calls.append({"expression": expression, "arg": arg, "timeout": timeout})
        if arg == selectors.PS_FEATURE_DIALOG:
            if not self.dialog_closes:
                raise TimeoutError("dialog stayed open")
            self.dialog_visible = False
            return True
        if isinstance(arg, dict) and arg.get("selector") == selectors.PARTSTUDIO_FEATURE_ITEM:
            if self.panel_renders and self.rows:
                return True
            raise TimeoutError("panel never rendered a row")
        return True

    def wait_for_timeout(self, milliseconds: int) -> None:
        self.timeouts.append(milliseconds)

    def locator(self, selector: str) -> FakeDialogLocator:
        return FakeDialogLocator(self, selector)


class EditFeatureParametersTest(unittest.TestCase):
    """The edit path takes its row NAME and its CLICK INDEX from one enumeration.

    Two live measurements on 2026-09-20, both on the real Windows browser, drove
    this class. First: on a Part Studio whose read listed nine user-feature rows,
    ``page.locator('.os-list-item.ns-user-feature').filter(has_text='Sr Spiral
    ridge 7')`` reported a count other than one for the row that read returned as
    its single match — deterministically, over four attempts and two page reloads.
    Second, after comparing the read against the counting locator instead: the read
    drops a row whose ``innerText`` and ``textContent`` are both empty while the
    locator counts it, so the two counts differed by exactly one on EVERY element
    (1 against 2, 11 against 12) and the tool refused everywhere. A set difference
    is not a page change, so comparing a filtered read with a counting locator can
    never be a valid precondition.

    These tests pin the replacement: names and click index from the same node list,
    the locator count as a staleness check, both counts reported on disagreement,
    and an accept that waits on the dialog closing rather than on a sleep.
    """

    TARGET = "Sr Spiral ridge 7"

    def _edit(self, page: FakeDialogPage, value: str = "12 mm") -> dict:
        return transactions.edit_feature_parameters(page, self.TARGET, {"baseRadius": value})

    def test_a_nameless_node_does_not_shift_the_clicked_row(self):
        """The live +1 node must be harmless: the index comes from the same list."""
        page = FakeDialogPage()
        result = self._edit(page)
        # Four DOM nodes, nameless one first: the target is node 3. An index taken
        # from a names-only list would be 2 and would open a different row.
        self.assertEqual(page.dblclicks, [3, 3], "click the enumerated row, then reopen it")
        self.assertEqual(result["featureRow"]["featureRows"], ["", *page.rows])
        self.assertEqual(result["featureRow"]["matchedRows"], [self.TARGET])
        self.assertEqual(result["featureRow"]["locatorRows"], 4)
        self.assertTrue(result["featureRow"]["panelReady"]["waited"])
        self.assertTrue(result["parametersApplied"])

    def test_without_a_nameless_node_the_index_is_the_plain_one(self):
        page = FakeDialogPage(nameless_rows=0)
        result = self._edit(page)
        self.assertEqual(page.dblclicks, [2, 2])
        self.assertEqual(result["featureRow"]["featureRows"], page.rows)
        self.assertEqual(result["featureRow"]["locatorRows"], 3)
        self.assertTrue(result["parametersApplied"])

    def test_only_a_page_change_between_the_two_queries_refuses_the_click(self):
        """A DOM change between enumerating and clicking is the only valid refusal."""
        page = FakeDialogPage(locator_delta=1)
        result = self._edit(page)
        self.assertFalse(result["parametersApplied"])
        self.assertEqual(page.dblclicks, [], "no click without agreement")
        self.assertEqual(result["featureRow"]["locatorRows"], 5)
        self.assertEqual(len(result["featureRow"]["featureRows"]), 4)
        self.assertIn("refusing to click", result["reason"])

    def test_a_name_that_matches_nothing_reports_the_rows_it_could_have_matched(self):
        page = FakeDialogPage()
        result = transactions.edit_feature_parameters(page, "Bc", {"baseRadius": "12 mm"})
        self.assertFalse(result["parametersApplied"])
        self.assertEqual(page.dblclicks, [])
        self.assertEqual(result["featureRow"]["matchedRows"], [])
        self.assertIn("matched 0 of 4", result["reason"])
        self.assertEqual(result["featureRow"]["featureRows"], ["", *page.rows])

    def test_a_name_that_matches_several_rows_is_reported_not_guessed(self):
        page = FakeDialogPage(rows=("Sr Spiral ridge 1", "Sr Spiral ridge 2"))
        result = transactions.edit_feature_parameters(page, "Spiral ridge", {"baseRadius": "12 mm"})
        self.assertFalse(result["parametersApplied"])
        self.assertEqual(page.dblclicks, [])
        self.assertIn("matched 2 of 3", result["reason"])
        self.assertEqual(
            result["featureRow"]["matchedRows"], ["Sr Spiral ridge 1", "Sr Spiral ridge 2"]
        )

    def test_the_panel_is_waited_for_before_the_enumeration(self):
        page = FakeDialogPage(rows=(), nameless_rows=0, panel_renders=False)
        result = self._edit(page)
        self.assertFalse(result["parametersApplied"])
        self.assertEqual(page.dblclicks, [])
        self.assertFalse(result["featureRow"]["panelReady"]["waited"])
        self.assertIn("no custom-feature row is on screen", result["reason"])
        self.assertIn("never rendered rows", result["reason"])
        self.assertTrue(
            any(
                isinstance(call["arg"], dict)
                and call["arg"].get("selector") == selectors.PARTSTUDIO_FEATURE_ITEM
                for call in page.wait_calls
            ),
            "the panel readiness wait must query the feature-item selector",
        )

    def test_the_accept_step_waits_on_the_dialog_closing_not_on_a_sleep(self):
        page = FakeDialogPage()
        result = self._edit(page)
        self.assertTrue(result["accepted"])
        self.assertTrue(result["accept"]["clicked"])
        self.assertTrue(result["accept"]["waited"])
        self.assertGreaterEqual(result["accept"]["waitMs"], 0)
        self.assertEqual(page.timeouts, [], "the accept step must not sleep")
        self.assertTrue(
            any(call["arg"] == selectors.PS_FEATURE_DIALOG for call in page.wait_calls),
            "the accept step must wait on the dialog closing",
        )
        self.assertTrue(result["readbackOk"])
        self.assertTrue(result["regenerationOk"])
        self.assertTrue(result["persistenceOk"])

    def test_an_accept_that_never_closes_is_evidence_not_a_crash(self):
        page = FakeDialogPage(dialog_closes=False)
        result = self._edit(page)
        self.assertFalse(result["accepted"])
        self.assertFalse(result["parametersApplied"])
        self.assertFalse(result["accept"]["waited"])
        self.assertIn("timeoutMs", result["accept"])

    def test_a_dialog_that_never_opens_reports_the_row_evidence_too(self):
        page = FakeDialogPage(dialog_opens=False)
        result = self._edit(page)
        self.assertFalse(result["parametersApplied"])
        self.assertIn("feature dialog did not open", result["reason"])
        self.assertEqual(result["featureRow"]["matchedRows"], [self.TARGET])

    def test_a_parameter_field_that_is_not_found_is_reported_as_missing(self):
        page = FakeDialogPage(locator_sees_parameter=False)
        result = self._edit(page)
        self.assertFalse(result["parametersApplied"])
        self.assertEqual(result["missing"], ["baseRadius"])
        self.assertEqual(page.fills, [])
        self.assertEqual(page.accept_clicks, [], "never accept with a field unfilled")

    def test_the_row_is_never_identified_by_a_text_filter(self):
        """One enumeration; a filtered read is never compared with a counting locator."""
        source = Path(transactions.__file__).read_text(encoding="utf-8")
        self.assertNotIn("filter(has_text=feature_name)", source)
        locator_source = source.split("def _locate_feature_row", 1)[1].split("\ndef ", 1)[0]
        # Drop the docstring: it deliberately NAMES the two defects it documents,
        # so only the executable body may carry the invariant.
        body = locator_source.rsplit('"""', 1)[-1]
        self.assertIn("rows.nth(", body)
        self.assertIn("enumerate_user_feature_rows", body)
        self.assertIn("match_user_feature_row_indices", body)
        self.assertNotIn(
            "read_partstudio_features",
            body,
            "a read that FILTERS nameless rows and a locator that COUNTS them are "
            "different sets; comparing them refused on every element live",
        )


if __name__ == "__main__":
    unittest.main()
