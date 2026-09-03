"""Zero-quota browser actions for the FeatureScript editor.

These operate on the live Onshape page through Playwright. They never call the
Onshape REST API: reading/writing the Ace editor and clicking the Commit button
all happen in the browser UI, so deploying a FeatureScript script this way
spends 0 API calls.

All functions take a Playwright sync `page` object obtained from
``BrowserSession.start()``.
"""

from __future__ import annotations

import re
from typing import Any

from onshape_browser_mode.selectors import (
    ACE_EDITOR,
    CONTEXT_MENU_LAYER,
    FS_COMMIT_BUTTON,
    FS_MODULE_OUTLINE,
    FS_MODULE_OUTLINE_DROPDOWN,
    FS_MODULE_OUTLINE_ICON,
    FS_MODULE_OUTLINE_ITEM,
    FS_MODULE_OUTLINE_LIST,
    FS_MODULE_OUTLINE_NAME,
    FS_NOTICE_COLUMN,
    FS_NOTICE_CONTENT,
    FS_NOTICE_LINE,
    FS_NOTICE_MESSAGE,
    FS_NOTICE_TABLE,
    FS_NOTICE_TOGGLE,
    TIMEOUT_RECONNECT_LINK,
)

_ACE_GET_EDITOR_JS = """
() => {
  const el = document.querySelector('%s');
  if (!el) return null;
  const ed = (el.env && el.env.editor) || (window.ace && window.ace.edit(el));
  return ed || null;
}
""" % ACE_EDITOR


def read_featurescript_editor(page: Any) -> str | None:
    """Return the full FeatureScript source, or None if no Ace editor is open."""
    return page.evaluate(
        """
        () => {
          const el = document.querySelector('.ace_editor');
          if (!el) return null;
          const ed = (el.env && el.env.editor) || (window.ace && window.ace.edit(el));
          return ed ? ed.getValue() : null;
        }
        """
    )


def _read_featurescript_ace_annotations(page: Any) -> dict[str, Any]:
    """Read and normalize the active Ace session's annotations."""
    return page.evaluate(
        """
        () => {
          const el = document.querySelector('%s');
          if (!el) {
            return {
              found: false,
              annotationCount: 0,
              errors: [],
              reason: 'FeatureScript editor not found',
            };
          }
          const ed = (el.env && el.env.editor) || (window.ace && window.ace.edit(el));
          if (!ed || !ed.session || typeof ed.session.getAnnotations !== 'function') {
            return {
              found: false,
              annotationCount: 0,
              errors: [],
              reason: 'Ace annotation API unavailable',
            };
          }
          const annotations = ed.session.getAnnotations() || [];
          return {
            found: true,
            annotationCount: annotations.length,
            errors: annotations.map((item) => ({
              row: Number.isInteger(item.row) ? item.row : 0,
              col: Number.isInteger(item.column)
                ? item.column
                : (Number.isInteger(item.col) ? item.col : 0),
              text: String(item.text || ''),
              type: String(item.type || 'error'),
              source: 'aceAnnotation',
            })),
          };
        }
        """ % ACE_EDITOR
    )


def _read_featurescript_notice_snapshot(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """
        (selectors) => {
          const visible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' &&
              rect.width > 0 && rect.height > 0;
          };
          const text = (el) => (el ? (el.innerText || el.textContent || '').trim() : '');
          const integer = (el) => {
            const value = Number.parseInt(text(el), 10);
            return Number.isInteger(value) ? value : null;
          };
          const toggle = document.querySelector(selectors.toggle);
          const content = document.querySelector(selectors.content);
          const activeTab = Array.from(document.querySelectorAll('.os-tab-bar-tab'))
            .find((tab) => (tab.className || '').includes('active'));
          const activeTabName = text(activeTab && activeTab.querySelector('.os-tab-name'));
          const containers = content
            ? Array.from(content.querySelectorAll('.element-notice-set-container'))
            : [];
          const notices = [];
          for (const container of containers) {
            if (container.querySelector('.notices-out-of-date')) continue;
            const tabName = text(container.querySelector('.element-notice-title'));
            if (activeTabName && tabName && tabName !== activeTabName) continue;
            for (const table of container.querySelectorAll(selectors.table)) {
              const messages = Array.from(table.querySelectorAll(selectors.message))
                .map(text).filter(Boolean);
              if (!messages.length) continue;
              const line = integer(table.querySelector(selectors.line));
              const column = integer(table.querySelector(selectors.column));
              let severity = 'warning';
              if (table.querySelector('.fs-notice-error')) severity = 'error';
              else if (table.querySelector('.fs-notice-info')) severity = 'info';
              notices.push({
                severity,
                text: messages[0],
                line,
                column,
                row: line === null ? 0 : Math.max(0, line - 1),
                col: column === null ? 0 : Math.max(0, column - 1),
                tabName,
              });
            }
          }
          return {
            found: !!toggle || !!content,
            indicatorPresent: visible(toggle),
            paneOpen: !!(toggle && toggle.querySelector('.flyout-toggle-button.os-expanded')),
            activeTabName,
            noticeCount: notices.length,
            notices,
          };
        }
        """,
        {
            "toggle": FS_NOTICE_TOGGLE,
            "content": FS_NOTICE_CONTENT,
            "table": FS_NOTICE_TABLE,
            "message": FS_NOTICE_MESSAGE,
            "line": FS_NOTICE_LINE,
            "column": FS_NOTICE_COLUMN,
        },
    )


def read_featurescript_notices(page: Any) -> dict[str, Any]:
    """Read active-tab FeatureScript notices and restore the notice pane state."""
    try:
        snapshot = _read_featurescript_notice_snapshot(page)
    except Exception as exc:  # noqa: BLE001 - fail closed with structured evidence
        return {
            "found": False,
            "complete": False,
            "indicatorPresent": False,
            "noticeCount": 0,
            "notices": [],
            "openedForRead": False,
            "restored": True,
            "reason": f"FeatureScript notice snapshot failed: {type(exc).__name__}: {exc}",
        }
    if not isinstance(snapshot, dict):
        return {
            "found": False,
            "complete": False,
            "noticeCount": 0,
            "notices": [],
            "reason": "FeatureScript notice snapshot was not an object",
        }

    opened_for_read = False
    restored = True
    reason = ""
    if (
        snapshot.get("indicatorPresent")
        and not snapshot.get("paneOpen")
        and not snapshot.get("notices")
    ):
        toggle = page.locator(FS_NOTICE_TOGGLE).first
        try:
            if toggle.count() != 1:
                raise RuntimeError("FeatureScript notice toggle was not found uniquely")
            toggle.click()
            opened_for_read = True
            page.locator(FS_NOTICE_CONTENT).first.wait_for(
                state="visible", timeout=5_000
            )
            refreshed = _read_featurescript_notice_snapshot(page)
            if isinstance(refreshed, dict):
                snapshot = refreshed
            else:
                reason = "FeatureScript notice snapshot was not an object after opening"
        except Exception as exc:  # noqa: BLE001 - return bounded browser evidence
            reason = f"FeatureScript notice pane unavailable: {type(exc).__name__}: {exc}"
        finally:
            if opened_for_read:
                try:
                    toggle.click()
                except Exception as exc:  # noqa: BLE001 - status evidence remains usable
                    restored = False
                    if not reason:
                        reason = f"FeatureScript notice pane could not be restored: {type(exc).__name__}: {exc}"

    complete = bool(
        not snapshot.get("indicatorPresent")
        or snapshot.get("paneOpen")
        or snapshot.get("notices")
    ) and not (reason and not snapshot.get("notices"))
    return {
        **snapshot,
        "complete": complete,
        "openedForRead": opened_for_read,
        "restored": restored,
        **({"reason": reason} if reason else {}),
    }


def read_featurescript_compile_status(page: Any) -> dict[str, Any]:
    """Combine Ace annotations with the active FeatureScript notice pane."""
    try:
        ace = _read_featurescript_ace_annotations(page)
    except Exception as exc:  # noqa: BLE001 - deployment must retain failure evidence
        return {
            "found": False,
            "compiled": False,
            "annotationCount": 0,
            "noticeCount": 0,
            "errors": [{
                "row": 0,
                "col": 0,
                "text": f"Ace annotation read failed: {type(exc).__name__}: {exc}",
                "type": "error",
                "source": "compileObservation",
            }],
            "notices": [],
            "noticeReadComplete": False,
            "reason": f"Ace annotation read failed: {type(exc).__name__}: {exc}",
        }
    if not isinstance(ace, dict) or not ace.get("found"):
        return {
            "found": False,
            "compiled": False,
            "annotationCount": int((ace or {}).get("annotationCount", 0)),
            "noticeCount": 0,
            "errors": list((ace or {}).get("errors", [])),
            "notices": [],
            "noticeReadComplete": False,
            "reason": (ace or {}).get("reason", "FeatureScript annotations unavailable"),
        }

    notice_status = read_featurescript_notices(page)
    notices = [item for item in notice_status.get("notices", []) if isinstance(item, dict)]
    blocking_notices = [
        item for item in notices if str(item.get("severity", "warning")).lower() != "info"
    ]
    notice_errors = [
        {
            "row": int(item.get("row", 0)),
            "col": int(item.get("col", 0)),
            "line": item.get("line"),
            "column": item.get("column"),
            "text": str(item.get("text", "")),
            "type": str(item.get("severity", "warning")),
            "source": "featureScriptNotice",
            "tabName": str(item.get("tabName", "")),
        }
        for item in blocking_notices
    ]
    ace_errors = [item for item in ace.get("errors", []) if isinstance(item, dict)]
    notice_complete = bool(notice_status.get("complete"))
    errors = [*ace_errors, *notice_errors]
    result = {
        "found": True,
        "compiled": not errors and notice_complete,
        "annotationCount": int(ace.get("annotationCount", len(ace_errors))),
        "noticeCount": len(notices),
        "errorCount": sum(1 for item in errors if str(item.get("type", "")).lower() == "error"),
        "warningCount": sum(1 for item in errors if str(item.get("type", "")).lower() == "warning"),
        "errors": errors,
        "notices": notices,
        "noticeReadComplete": notice_complete,
        "noticePaneOpenedForRead": bool(notice_status.get("openedForRead")),
        "noticePaneRestored": bool(notice_status.get("restored", True)),
    }
    if not notice_complete:
        result["reason"] = str(
            notice_status.get("reason", "FeatureScript notice indicator present but notices were not readable")
        )
    return result


def _featurescript_symbol_kind(icon: str) -> str:
    """Map the Module-outline glyph to a stable public symbol kind."""
    if icon == "C":
        return "const"
    if icon == "Φ":
        return "feature"
    return "function"


def read_featurescript_symbols(page: Any) -> dict[str, Any]:
    """Open Module outline and return its normalized top-level symbols."""
    dropdown = page.locator(FS_MODULE_OUTLINE_DROPDOWN).first
    try:
        visible = dropdown.count() > 0 and dropdown.is_visible()
        if not visible:
            button = page.locator(FS_MODULE_OUTLINE).first
            if button.count() == 0:
                return {
                    "found": False,
                    "symbolCount": 0,
                    "symbols": [],
                    "reason": "Module outline button not found",
                }
            button.click()
            page.locator(FS_MODULE_OUTLINE_LIST).first.wait_for(
                state="visible", timeout=10_000
            )
    except Exception as exc:  # noqa: BLE001 - structured browser failure
        return {
            "found": False,
            "symbolCount": 0,
            "symbols": [],
            "reason": f"Module outline unavailable: {type(exc).__name__}: {exc}",
        }

    raw = page.evaluate(
        """
        (selectors) => ({
          found: true,
          items: Array.from(document.querySelectorAll(selectors.item)).map((item) => ({
            rawIcon: (item.querySelector(selectors.icon)?.textContent || '').trim(),
            displayName: (item.querySelector(selectors.name)?.textContent || '').trim(),
          })),
        })
        """,
        {
            "item": FS_MODULE_OUTLINE_ITEM,
            "icon": FS_MODULE_OUTLINE_ICON,
            "name": FS_MODULE_OUTLINE_NAME,
        },
    )
    if not isinstance(raw, dict) or not raw.get("found"):
        return {
            "found": False,
            "symbolCount": 0,
            "symbols": [],
            "reason": "Module outline symbols could not be read",
        }
    symbols = []
    for item in raw.get("items", []):
        if not isinstance(item, dict):
            continue
        display_name = str(item.get("displayName", "")).strip()
        name = display_name.split("(", 1)[0].strip()
        if not name:
            continue
        raw_icon = str(item.get("rawIcon", "")).strip()
        symbols.append({
            "kind": _featurescript_symbol_kind(raw_icon),
            "name": name,
            "displayName": display_name,
            "rawIcon": raw_icon,
        })
    return {
        "found": True,
        "symbolCount": len(symbols),
        "symbols": symbols,
    }


def write_featurescript_editor(page: Any, text: str) -> dict[str, Any]:
    """Replace the FeatureScript editor content in place.

    Uses the Ace API (not DOM textarea) so Onshape's change detection sees the
    edit and enables the Commit button.
    """
    return page.evaluate(
        """
        (text) => {
          const el = document.querySelector('.ace_editor');
          if (!el) return {ok: false, error: 'no .ace_editor on page'};
          const ed = (el.env && el.env.editor) || (window.ace && window.ace.edit(el));
          if (!ed) return {ok: false, error: 'ace editor API unavailable'};
          ed.setValue(text);
          ed.clearSelection();
          ed.moveCursorTo(0, 0);
          return {ok: true, length: text.length, lineCount: text.split('\\n').length};
        }
        """,
        text,
    )


def commit_button_state(page: Any) -> dict[str, Any]:
    """Report whether the FeatureScript Commit button exists and is enabled."""
    return page.evaluate(
        """
        () => {
          const btn = Array.from(document.querySelectorAll('.tool.is-activatable.is-button'))
            .find(b => (b.innerText || '').trim() === '提交');
          if (!btn) return {found: false};
          return {
            found: true,
            disabled: btn.className.includes('disabled'),
            cls: (typeof btn.className === 'string' ? btn.className : '').slice(0, 120),
          };
        }
        """
    )


def click_commit(page: Any) -> dict[str, Any]:
    """Click the FeatureScript Commit button and report the new button state."""
    before = commit_button_state(page)
    if not before.get("found"):
        return {"clicked": False, "before": before, "error": "commit button not found"}
    try:
        page.locator(FS_COMMIT_BUTTON).first.click()
        page.wait_for_timeout(3000)
    except Exception as exc:  # noqa: BLE001 - surface as structured result
        return {"clicked": False, "before": before, "error": f"{type(exc).__name__}: {exc}"}
    after = commit_button_state(page)
    return {"clicked": True, "before": before, "after": after}


_DOCUMENT_URL_RE = re.compile(r"/documents/([^/]+)(?:/w/([^/]+))?(?:/e/([^/]+))?")


def parse_document_url(url: str) -> dict[str, str | None]:
    """Extract documentId/workspaceId/elementId from an Onshape URL.

    Handles both the documents-list form (``/documents/<did>``) and the opened
    tab form (``/documents/<did>/w/<wid>/e/<eid>``). Unknown shapes return all
    None values, never raise.
    """
    match = _DOCUMENT_URL_RE.search(url or "")
    if not match:
        return {"documentId": None, "workspaceId": None, "elementId": None}
    return {
        "documentId": match.group(1) or None,
        "workspaceId": match.group(2) or None,
        "elementId": match.group(3) or None,
    }


def create_document(page: Any, name: str = "") -> dict[str, Any]:
    """Create a new Onshape document from the documents page (0 API quota).

    Goes to the documents list, opens the Create menu, clicks "文档…", fills the
    document-name input (default "无标题文档" when empty), and clicks "创建".
    Returns the new document URL and parsed document/workspace ids.
    """
    try:
        page.goto(
            "https://cad.onshape.com/documents",
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        page.wait_for_timeout(4000)
        page.locator("#create-new-type").first.click()
        page.wait_for_timeout(1000)
        page.locator(".create-new-document").first.click()
        page.wait_for_timeout(2000)
        if name:
            page.locator("#document-name-input").first.fill(name)
            page.wait_for_timeout(500)
        page.locator(".new-document-dialog .btn-primary").first.click()
        page.wait_for_timeout(8000)
    except Exception as exc:  # noqa: BLE001 - surface as structured result
        return {"created": False, "error": f"{type(exc).__name__}: {exc}", "pageUrl": page.url}

    url = page.url
    return {"created": True, "pageUrl": url, **parse_document_url(url)}


def create_document_tab(page: Any, tab_type: str = "Feature Studio") -> dict[str, Any]:
    """Create a new document tab (Feature Studio / Part Studio / Assembly /
    Drawing) via the tabs menu.

    The dropdown items are present but hidden until the menu opens; a plain
    Playwright click on a hidden item fails, so the item is clicked in page
    JavaScript. Adding a tab creates an Onshape document element (a cloud
    mutation) but spends zero REST API quota.
    """
    try:
        before_state = list_document_tabs(page)
        before_names = {tab.get("name", "") for tab in before_state.get("tabs", [])}
        before_tabs_readable = True
    except Exception:  # noqa: BLE001 - creation can still be attempted
        before_names = set()
        before_tabs_readable = False

    create_item_text = {
        "Feature Studio": "创建 Feature Studio",
        "Part Studio": "创建 Part Studio",
        "Assembly": "创建装配体",
        "Drawing": "创建工程图",
    }
    needle = create_item_text.get(tab_type, "创建 " + tab_type)

    clicked_item = page.evaluate(
        """
        (needle) => {
          const items = Array.from(document.querySelectorAll('a.dropdown-item, .dropdown-item, li.dropdown-item'));
          const item = items.find(el => ((el.textContent || '').replace(/\\s+/g, ' ')).includes(needle.replace(/\\s+/g, ' ')));
          if (!item) {
            return {clicked: false, reason: 'dropdown item not found',
                    items: items.map(el => (el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 80))};
          }
          item.click();
          return {clicked: true, text: (item.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 80)};
        }
        """,
        needle,
    )
    if not clicked_item.get("clicked"):
        return {
            **clicked_item,
            "triggered": False,
            "created": False,
            "tabType": tab_type,
            "pageUrl": page.url,
        }
    page.wait_for_timeout(8000)

    try:
        tab_state = list_document_tabs(page)
        after_tabs = tab_state.get("tabs", [])
        new_tabs = [tab for tab in after_tabs if tab.get("name", "") not in before_names]
        tab_read_error = None
    except Exception as exc:  # noqa: BLE001 - return a structured partial result
        tab_state = {"tabs": [], "hasDocumentTabsToolButton": None}
        new_tabs = []
        tab_read_error = f"{type(exc).__name__}: {exc}"

    created = before_tabs_readable and bool(new_tabs)
    result = {
        "triggered": True,
        "created": created,
        "beforeTabsReadable": before_tabs_readable,
        "tabType": tab_type,
        "clickedItem": clicked_item.get("text", ""),
        "newTabs": new_tabs,
        **tab_state,
        "pageUrl": page.url,
    }
    if tab_read_error:
        result["tabReadError"] = tab_read_error
    if not before_tabs_readable:
        result["reason"] = "creation flow triggered but the previous tab state was unreadable; creation is unverified"
    elif not created:
        result["reason"] = "creation flow triggered but no new tab is visible; complete any open dialog"
    return result


def rename_tab(page: Any, name: str, new_name: str) -> dict[str, Any]:
    """Rename a document tab (Feature Studio / Part Studio) by its visible name.

    Right-clicks the tab, picks 重命名 from the context menu, fills the rename
    input with the new name and commits with Enter. Uses real Playwright input
    (trusted events) so Angular processes the rename. Zero Onshape API quota.
    """
    from onshape_browser_mode.selectors import (
        TAB_BAR_TAB,
        TAB_CONTEXT_MENU_ITEM,
        TAB_RENAME_INPUT,
    )

    new_name = (new_name or "").strip()
    if not new_name:
        return {"renamed": False, "reason": "new_name must be non-empty", "pageUrl": page.url}

    # 1. Right-click the tab and pick 重命名.
    try:
        tab = page.locator(TAB_BAR_TAB).filter(has_text=name)
        if tab.count() == 0:
            return {"renamed": False, "reason": f"tab {name!r} not found", "pageUrl": page.url}
        dismiss_stale_context_menu(page)
        tab.first.click(button="right")
        page.wait_for_timeout(2000)
        item = page.locator(TAB_CONTEXT_MENU_ITEM).filter(has_text="重命名")
        if item.count() == 0:
            return {"renamed": False, "reason": "重命名 menu item not found", "pageUrl": page.url}
        item.first.click()
        page.wait_for_timeout(1500)
    except Exception as exc:  # noqa: BLE001 - surface as structured result
        return {"renamed": False, "reason": f"rename-menu click failed: {exc}", "pageUrl": page.url}

    # 2. Fill the rename input and commit with Enter (trusted Playwright input).
    try:
        input_locator = page.locator(TAB_RENAME_INPUT)
        if input_locator.count() == 0:
            return {"renamed": False, "reason": "rename input not found", "pageUrl": page.url}
        input_locator.first.click()
        input_locator.first.fill(new_name)
        input_locator.first.press("Enter")
        page.wait_for_timeout(3000)
    except Exception as exc:  # noqa: BLE001 - surface as structured result
        return {"renamed": False, "reason": f"rename input failed: {exc}", "pageUrl": page.url}

    tabs = list_document_tabs(page)
    renamed = any(t.get("name") == new_name for t in tabs.get("tabs", []))
    return {"renamed": renamed, **tabs, "pageUrl": page.url}


def _tab_locators_by_id(page: Any, element_id: str) -> list[Any]:
    """Return exact data-id matches without interpolating caller text into CSS."""
    from onshape_browser_mode.selectors import TAB_BAR_TAB

    rows = page.locator(TAB_BAR_TAB)
    matches = []
    for index in range(rows.count()):
        row = rows.nth(index)
        try:
            if row.get_attribute("data-id") == element_id:
                matches.append(row)
        except Exception:
            continue
    return matches


def delete_element_by_id(page: Any, element_id: str) -> dict[str, Any]:
    """Delete exactly one visible tab by observed data-id and verify detachment."""
    from onshape_browser_mode.selectors import DIALOG_ACCEPT, TAB_CONTEXT_MENU_ITEM

    matches = _tab_locators_by_id(page, element_id)
    if len(matches) != 1:
        return {
            "deleted": False,
            "elementId": element_id,
            "matchCount": len(matches),
            "reason": "element data-id must match exactly one visible tab",
            "pageUrl": page.url,
        }
    tab = matches[0]
    try:
        dismiss_stale_context_menu(page)
        tab.click(button="right")
        candidates = page.locator(TAB_CONTEXT_MENU_ITEM)
        exact_visible = []
        for index in range(candidates.count()):
            candidate = candidates.nth(index)
            try:
                if candidate.is_visible() and candidate.inner_text().strip() == "删除":
                    exact_visible.append(candidate)
            except Exception:
                continue
        if len(exact_visible) != 1:
            return {
                "deleted": False,
                "elementId": element_id,
                "reason": "exact unique visible 删除 menu item not found",
                "pageUrl": page.url,
            }
        exact_visible[0].click()
        confirm = page.locator(DIALOG_ACCEPT)
        if confirm.count() > 0:
            confirm.first.click()
        tab.wait_for(state="detached", timeout=30_000)
    except Exception as exc:  # noqa: BLE001
        return {"deleted": False, "elementId": element_id, "reason": str(exc), "pageUrl": page.url}
    tabs = list_document_tabs(page)
    deleted = not _tab_locators_by_id(page, element_id)
    return {"deleted": deleted, "elementId": element_id, **tabs, "pageUrl": page.url}


def delete_tab(page: Any, name: str) -> dict[str, Any]:
    """Compatibility wrapper: resolve one exact visible name, then delete by ID."""
    tabs = list_document_tabs(page)
    exact = [tab for tab in tabs.get("tabs", []) if tab.get("name") == name]
    if len(exact) != 1:
        return {
            "deleted": False,
            "name": name,
            "matchCount": len(exact),
            "reason": "tab name must match exactly one visible tab; prefer browser_delete_element",
            **tabs,
            "pageUrl": page.url,
        }
    element_id = exact[0].get("id")
    if not isinstance(element_id, str) or not element_id:
        return {
            "deleted": False,
            "name": name,
            "reason": "exact tab has no observable data-id; use browser_delete_element when ID is available",
            **tabs,
            "pageUrl": page.url,
        }
    return {**delete_element_by_id(page, element_id), "resolvedName": name, "compatibilityWrapper": True}


def open_document_by_name(
    page: Any,
    document_name: str,
    entry_url: str | None = None,
) -> dict[str, Any]:
    """Open a document from the documents list by its visible name.

    This is read-only navigation (no Onshape data is created or changed): go to
    the documents list, click the matching document link, and wait for the SPA
    to settle. Returns the resulting URL and parsed ids.
    """
    from onshape_browser_mode.session import _is_onshape_app_url

    try:
        current = page.url
    except Exception:
        current = None

    if not _is_onshape_app_url(current) or read_featurescript_editor(page) is not None:
        pass  # keep going through the list entry to reach the named document

    try:
        page.goto(
            entry_url or "https://cad.onshape.com/documents",
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        page.wait_for_timeout(4000)
    except Exception as exc:
        return {"opened": False, "error": f"navigate to documents failed: {exc}", "pageUrl": page.url}

    try:
        locator = page.get_by_text(document_name, exact=False)
        count = locator.count()
        if count == 0:
            return {"opened": False, "error": f"document not found: {document_name!r}", "pageUrl": page.url}
        locator.first.click()
        page.wait_for_timeout(5000)
    except Exception as exc:
        return {"opened": False, "error": f"click document failed: {exc}", "pageUrl": page.url}

    url = page.url
    return {
        "opened": True,
        "pageUrl": url,
        **parse_document_url(url),
    }


def read_partstudio_features(page: Any) -> dict[str, Any]:
    """Read the Part Studio feature tree and part list (read-only, 0 quota).

    Returns the feature-list header, each feature item with its user/default
    classification, and the part-list text (e.g. "零件数 (132) base ...").
    A custom feature present in the list means its FeatureScript compiled and
    was instantiated successfully.
    """
    return page.evaluate(
        """
        () => {
          const features = Array.from(document.querySelectorAll('.os-list-item')).map(el => {
            const icon = el.querySelector('.os-list-item-icon');
            const cls = el.className || '';
            return {
              name: (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 100),
              isUserFeature: cls.includes('ns-user-feature'),
              isDefault: cls.includes('ns-default-feature'),
              className: String(cls).slice(0, 180),
              hasError: /error|not-computed|未计算|错误/i.test(cls + ' ' + (el.innerText || el.textContent || '')),
              iconCls: icon ? (typeof icon.className === 'string' ? icon.className : '').slice(0, 90) : '',
            };
          }).filter(f => f.name);
          const header = document.querySelector('.features-title');
          const partsEl = document.querySelector('.part-list-container');
          return {
            headerText: header ? (header.innerText || header.textContent || '').trim() : '',
            features,
            partsText: partsEl ? (partsEl.innerText || partsEl.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 400) : '',
          };
        }
        """
    )


def list_document_tabs(page: Any) -> dict[str, Any]:
    """List the document tabs (e.g. Feature Studio / Part Studio) on screen.

    Read-only and 0 quota. Returns each tab's name and whether it is the active
    tab, plus the page URL. Used to find the Part Studio tab to insert into or
    the Feature Studio tab to deploy to.
    """
    return page.evaluate(
        """
        () => {
          const tabs = Array.from(document.querySelectorAll('.os-tab-bar-tab')).map(el => {
            const nameEl = el.querySelector('.os-tab-name');
            const name = (nameEl ? (nameEl.innerText || nameEl.textContent || '') : (el.innerText || el.textContent || '')).trim().replace(/\\s+/g, ' ');
            const cls = el.className || '';
            const elementType = el.getAttribute('data-element-type') || el.getAttribute('data-type') || '';
            return {
              id: el.getAttribute('data-id') || '',
              name,
              elementType,
              active: cls.includes('active'),
            };
          });
          const documentTabsToolButton = document.querySelector('.document-tabs-button');
          return { tabs, hasDocumentTabsToolButton: !!documentTabsToolButton };
        }
        """
    )


def dismiss_stale_context_menu(page: Any) -> dict[str, Any]:
    """Dismiss a pointer-blocking context-menu layer before a tab click."""
    expression = """
        (selector) => {
          const layer = document.querySelector(selector);
          if (!layer) return {present: false, blocking: false};
          const rect = layer.getBoundingClientRect();
          const style = window.getComputedStyle(layer);
          return {
            present: true,
            blocking: style.pointerEvents !== 'none' && rect.width > 0 && rect.height > 0,
            childCount: layer.childElementCount,
          };
        }
    """
    before = page.evaluate(expression, CONTEXT_MENU_LAYER)
    if not isinstance(before, dict) or not before.get("blocking"):
        return {"attempted": False, "dismissed": False, "before": before}
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(100)
        after = page.evaluate(expression, CONTEXT_MENU_LAYER)
    except Exception as exc:  # noqa: BLE001 - structured browser failure
        return {
            "attempted": True,
            "dismissed": False,
            "before": before,
            "reason": f"{type(exc).__name__}: {exc}",
        }
    return {
        "attempted": True,
        "dismissed": isinstance(after, dict) and not after.get("blocking", False),
        "before": before,
        "after": after,
    }


def reload_page(page: Any) -> dict[str, Any]:
    """Reload the current page with bounded waits and best-effort state."""
    warnings = []
    reloaded = True
    try:
        page.reload(wait_until="commit", timeout=15000)
    except Exception as exc:  # noqa: BLE001 - navigation may still have started
        reloaded = False
        warnings.append(f"reload: {type(exc).__name__}: {exc}")

    try:
        page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception as exc:  # noqa: BLE001 - report partial recovery state
        warnings.append(f"domcontentloaded: {type(exc).__name__}: {exc}")

    try:
        current_url = page.url
    except Exception as exc:  # noqa: BLE001 - best effort after reload
        current_url = None
        warnings.append(f"url: {type(exc).__name__}: {exc}")

    try:
        tab_state = {"tabsReadable": True, **list_document_tabs(page)}
    except Exception as exc:  # noqa: BLE001 - execution context may be rebuilding
        tab_state = {"tabs": [], "hasDocumentTabsToolButton": None, "tabsReadable": False}
        warnings.append(f"tabs: {type(exc).__name__}: {exc}")

    return {
        "reloadAttempted": True,
        "reloaded": reloaded,
        "warnings": warnings,
        "pageUrl": current_url,
        **tab_state,
    }


def open_insert_custom_feature_dialog(page: Any) -> dict[str, Any]:
    """Click the Part Studio toolbar's "添加自定义特征" button to open the dialog.

    The toolbar label span is hidden (``.tool-label.hide-in-toolbar``), so the
    click targets the visible ``.tool.is-button`` inside the toolbar item whose
    textContent contains 添加自定义特征.
    """
    clicked = page.evaluate(
        """
        () => {
          const items = Array.from(document.querySelectorAll('.toolbar-item'));
          const item = items.find(el => (el.textContent || '').includes('添加自定义特征'));
          if (!item) return {clicked: false, reason: 'toolbar item not found'};
          const btn = item.querySelector('.tool.is-button');
          if (!btn) return {clicked: false, reason: 'toolbar button not found'};
          btn.click();
          return {clicked: true};
        }
        """
    )
    page.wait_for_timeout(2500)
    dialog = page.evaluate(
        """
        () => {
          const dlg = document.querySelector('.feature-studio-insert-dialog');
          return { present: !!dlg, text: dlg ? (dlg.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 200) : '' };
        }
        """
    )
    return {**clicked, "dialog": dialog}


def read_insert_dialog(page: Any) -> dict[str, Any]:
    """Read the insert-custom-feature dialog state (read-only)."""
    return page.evaluate(
        """
        () => {
          const dlg = document.querySelector('.feature-studio-insert-dialog');
          if (!dlg) return { present: false };
          const tabs = Array.from(dlg.querySelectorAll('.os-dialog-tab')).map(
            el => ({ text: (el.innerText || el.textContent || '').trim(), active: (el.className || '').includes('active') })
          );
          const docNameEl = dlg.querySelector('.select-item-dialog-document-name');
          const warning = dlg.querySelector('.select-item-warning');
          const prompt = dlg.querySelector('.select-item-prompt-save-version');
          return {
            present: true,
            tabs,
            docName: docNameEl ? (docNameEl.innerText || docNameEl.textContent || '').trim() : '',
            warning: warning ? (warning.innerText || warning.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 200) : '',
            promptSaveVersion: !!prompt,
          };
        }
        """
    )


def insert_custom_feature(
    page: Any,
    feature_name: str,
    part_studio_tab: str | None = None,
) -> dict[str, Any]:
    """Apply a custom FeatureScript feature into a Part Studio (0 API quota).

    The Part Studio must MANUALLY apply the feature: clicking the toolbar button
    whose tooltip is 此工作区中的自定义特征 opens a dropdown of the workspace's
    custom features; clicking the feature applies it and opens its parameter
    dialog; clicking the checkmark (button-ok) accepts and computes the model.
    The 添加自定义特征 picker alone only inserts a not-computed row.
    """
    if part_studio_tab:
        tabs = list_document_tabs(page).get("tabs", [])
        matched = next((tab for tab in tabs if tab.get("name") == part_studio_tab), None)
        if not matched:
            return {"inserted": False, "reason": f"part studio tab {part_studio_tab!r} not found"}
        tab_id = matched.get("id", "")
        selector = f'.os-tab-bar-tab[data-id="{tab_id}"]' if tab_id else ".os-tab-bar-tab"
        tab = page.locator(selector)
        if not tab_id:
            tab = tab.filter(has_text=part_studio_tab)
        try:
            dismiss_stale_context_menu(page)
            tab.first.click()
            page.locator(".features-title").first.wait_for(state="visible", timeout=30_000)
        except Exception as exc:  # noqa: BLE001 - structured missing/unready tab
            return {"inserted": False, "reason": f"part studio tab did not become ready: {exc}"}

    # 1. Click the toolbar button titled 此工作区中的自定义特征.
    clicked = page.evaluate(
        """
        () => {
          const btn = Array.from(document.querySelectorAll('.tool')).find(
            el => (el.getAttribute('title') || el.getAttribute('data-bs-original-title') || '') === '此工作区中的自定义特征'
          );
          if (!btn) return {clicked: false, reason: 'workspace-custom-features button not found'};
          btn.click();
          return {clicked: true};
        }
        """
    )
    if not clicked.get("clicked"):
        return {**clicked, "inserted": False}
    page.wait_for_timeout(3000)

    # 2. Click the specific feature ITEM inside the dropdown (the dropdown may
    #    hold several workspace features; clicking the container hits whichever
    #    item sits at its centre, so scope the text match to the item rows).
    try:
        items = page.locator(".os-tool-dropdown-content .tool")
        matches = [
            items.nth(index)
            for index in range(items.count())
            if items.nth(index).is_visible() and items.nth(index).inner_text().strip() == feature_name
        ]
        if len(matches) != 1:
            return {"inserted": False, "reason": f"feature {feature_name!r} must match exactly one workspace dropdown item"}
        matches[0].click()
        page.wait_for_timeout(10000)
    except Exception as exc:  # noqa: BLE001 - surface as structured result
        return {"inserted": False, "reason": f"feature dropdown click failed: {exc}"}

    # 3. Accept the parameter dialog (checkmark) to finalize and compute.
    accepted = page.evaluate(
        """
        () => {
          const ok = document.querySelector('.ns-dialog-button-ok.button-ok');
          if (!ok) return {clicked: false, reason: 'accept button not found'};
          ok.click();
          return {clicked: true};
        }
        """
    )
    page.wait_for_timeout(15000)

    features = read_partstudio_features(page)
    return {
        "inserted": bool(accepted.get("clicked")),
        "accepted": accepted,
        "features": features,
        "pageUrl": page.url,
    }


def create_document_version(page: Any, name: str = "") -> dict[str, Any]:
    """Create a document version so custom features become insertable.

    The Feature Studio must be committed and the insert dialog shows a
    "创建一个版本" prompt until a version exists. This clicks that prompt,
    unchecks the publish-custom-features checkbox (publishing has extra
    requirements we do not need for in-document insertion), optionally fills
    the version name, and clicks 创建. Returns the new version label.
    """
    info = read_insert_dialog(page)
    if info.get("present") and not info.get("promptSaveVersion"):
        return {"created": False, "reason": "no version prompt; a version may already exist", "dialog": info}

    # Click the version-create prompt (opens .version-or-workspace-dialog).
    clicked = page.evaluate(
        """
        () => {
          const prompt = document.querySelector('.select-item-prompt-save-version');
          if (!prompt) return {clicked: false, reason: 'no version prompt'};
          (prompt.querySelector('a') || prompt).click();
          return {clicked: true};
        }
        """
    )
    if not clicked.get("clicked"):
        return {**clicked, "created": False}

    page.wait_for_timeout(4000)

    # Uncheck publish (extra requirements) and fill the optional name.
    page.evaluate(
        """
        (name) => {
          const modal = document.querySelector('.version-or-workspace-dialog');
          if (!modal) return {ok: false};
          const cb = modal.querySelector('.publish-custom-features-checkbox');
          if (cb && cb.checked) cb.click();
          if (name) {
            const input = modal.querySelector('input.form-control');
            if (input) {
              const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
              setter.call(input, name);
              input.dispatchEvent(new Event('input', {bubbles: true}));
            }
          }
          return {ok: true};
        }
        """,
        name,
    )
    page.wait_for_timeout(1000)

    # Click the plain 创建 button (its label is 创建 and发布 when publish is checked).
    clicked_create = page.evaluate(
        """
        () => {
          const modal = document.querySelector('.version-or-workspace-dialog');
          if (!modal) return {clicked: false, reason: 'no version modal'};
          const btns = Array.from(modal.querySelectorAll('button'));
          const btn = btns.find(b => (b.textContent || '').trim() === '创建');
          if (!btn) return {clicked: false, reason: 'no 创建 button', buttons: btns.map(b => (b.textContent || '').trim())};
          btn.click();
          return {clicked: true};
        }
        """
    )
    if not clicked_create.get("clicked"):
        return {**clicked_create, "created": False}

    page.wait_for_timeout(15000)

    version_label = page.evaluate(
        """
        () => {
          const el = document.querySelector('.select-item-dialog-document-version-name');
          const modal = document.querySelector('.version-or-workspace-dialog');
          return { version: el ? (el.innerText || el.textContent || '').trim() : '', modalOpen: !!modal };
        }
        """
    )
    return {"created": not version_label.get("modalOpen"), **version_label}


def timeout_dialog_state(page: Any) -> dict[str, Any]:
    """Report whether the Onshape session-timeout dialog is present."""
    return page.evaluate(
        """
        () => {
          const link = document.querySelector('.alert-link.osx-message-bubble-link');
          const dialog = document.querySelector('.osx-message');
          return {
            present: !!link,
            linkText: link ? (link.innerText || link.textContent || '').trim() : '',
            message: dialog ? (dialog.innerText || dialog.textContent || '').trim().slice(0, 200) : '',
          };
        }
        """
    )


def reconnect_if_needed(page: Any) -> dict[str, Any]:
    """Click the '重新连接' link if the Onshape timeout dialog is showing.

    Reconnecting is a session-level navigation (no cloud data is created or
    changed). Returns before/after dialog state plus the resulting URL.
    """
    before = timeout_dialog_state(page)
    if not before.get("present"):
        return {"reconnected": False, "reason": "no timeout dialog", "state": before, "pageUrl": page.url}
    try:
        page.locator(TIMEOUT_RECONNECT_LINK).first.click()
        page.wait_for_timeout(5000)
    except Exception as exc:  # noqa: BLE001 - surface as structured result
        return {
            "reconnected": False,
            "error": f"{type(exc).__name__}: {exc}",
            "state": before,
            "pageUrl": page.url,
        }
    after = timeout_dialog_state(page)
    return {
        "reconnected": not after.get("present"),
        "state": before,
        "after": after,
        "pageUrl": page.url,
    }
