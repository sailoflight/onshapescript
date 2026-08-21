"""Domain page objects for the Onshape browser UI."""

from __future__ import annotations

from typing import Any

from onshape_browser_mode.pages.base import BasePage
from onshape_browser_mode import selectors


class DocumentsPage(BasePage):
    """Documents-list selectors and navigation targets."""

    def search_box(self) -> Any:
        return self.scope.locator(selectors.DOCUMENTS_SEARCH_BOX).first

    def document_link(self, name: str) -> Any:
        return self.scope.locator(selectors.DOCUMENT_LINK).filter(has_text=name).first

    def create_button(self) -> Any:
        return self.scope.locator(selectors.DOCUMENTS_CREATE_BUTTON).first


class FeatureStudioPage(BasePage):
    """Feature Studio editor and commit controls."""

    def editor(self) -> Any:
        return self.scope.locator(selectors.ACE_EDITOR).first

    def commit_button(self) -> Any:
        return self.scope.locator(selectors.FS_COMMIT_BUTTON).first


class PartStudioPage(BasePage):
    """Part Studio feature tree and custom-feature controls."""

    def feature_rows(self) -> Any:
        return self.scope.locator(selectors.PS_FEATURE_LIST_ITEM)

    def part_list(self) -> Any:
        return self.scope.locator(selectors.PS_PART_LIST).first

    def workspace_custom_features(self) -> Any:
        return self.scope.locator(selectors.PS_WORKSPACE_CUSTOM_FEATURE_BTN).first


class AssemblyPage(BasePage):
    """Assembly insertion and instance-selection controls."""

    def insert_button(self) -> Any:
        return self.scope.locator(selectors.ASM_INSERT_BUTTON).first

    def insert_dialog(self) -> Any:
        return self.scope.locator(selectors.ASM_INSERT_DIALOG).first

    def insert_row(self, name: str) -> Any:
        return self.scope.locator(selectors.ASM_INSERT_ROW).filter(has_text=name).first

    def accept_insert(self) -> Any:
        return self.scope.locator(selectors.ASM_INSERT_ACCEPT).first

    def instance(self, name: str) -> Any:
        return self.scope.get_by_text(name, exact=False).first


class DrawingPage(BasePage):
    """Cross-origin drawing editor page object."""

    def __init__(self, page: Any, frame_url: str = selectors.DRAWING_FRAME_URL_PREFIX) -> None:
        super().__init__(page, frame_url)

    def state(self) -> dict[str, Any]:
        return self.scope.evaluate(
            """
            () => ({
              title: document.title,
              svgCount: document.querySelectorAll('svg').length,
              canvasCount: document.querySelectorAll('canvas').length,
              inputCount: document.querySelectorAll('input').length,
              text: (document.body && document.body.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 500),
            })
            """
        )
