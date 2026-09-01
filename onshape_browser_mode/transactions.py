"""Browser L2 transactions for Feature Studio and the shared document shell."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from onshape_browser_mode import actions, selectors


DOC_NAME = selectors.DOC_NAME
DOC_MENU = selectors.DOC_MENU
PANEL_ROOT = selectors.PANEL_ROOT
PANEL_FILTER = selectors.PANEL_FILTER
PANEL_CONTENT = selectors.PANEL_CONTENT
PANEL_SPLITTERS = selectors.PANEL_SPLITTERS
SELECTION_PREVIEW = selectors.SELECTION_PREVIEW
NOTIFICATIONS = selectors.DOCUMENTS_NOTIFICATION
NOTIFICATIONS_DRAWER = selectors.NOTIFICATIONS_DRAWER
SHARE_BUTTON = selectors.SHARE_BUTTON
SHARE_DIALOG = selectors.SHARE_DIALOG
VIEW_CUBE = selectors.VIEW_CUBE


def _visible_count(locator: Any) -> int:
    return sum(1 for index in range(locator.count()) if locator.nth(index).is_visible())


def _exact_text(locator: Any, expected: str) -> Any | None:
    normalized = expected.strip()
    matches = []
    for index in range(locator.count()):
        candidate = locator.nth(index)
        if candidate.is_visible() and candidate.inner_text().strip() == normalized:
            matches.append(candidate)
    return matches[0] if len(matches) == 1 else None


def _ace_cursor(page: Any) -> dict[str, Any]:
    result = page.evaluate(
        """
        () => {
          const el = document.querySelector('.ace_editor');
          const ed = el && ((el.env && el.env.editor) || (window.ace && window.ace.edit(el)));
          if (!ed) return {found: false};
          const cursor = ed.getCursorPosition();
          const lineText = ed.session.getLine(cursor.row) || '';
          return {found: true, row: cursor.row, column: cursor.column, lineText};
        }
        """
    )
    return result if isinstance(result, dict) else {"found": False}


def fs_goto_definition(page: Any, symbol: str) -> dict[str, Any]:
    """Navigate to a top-level definition through Module outline."""
    inventory = actions.read_featurescript_symbols(page)
    available = [item.get("name") for item in inventory.get("symbols", [])]
    if symbol not in available:
        return {
            "definitionFound": False,
            "symbol": symbol,
            "availableSymbols": available,
            "reason": f"symbol {symbol!r} is not present in Module outline",
        }
    before = _ace_cursor(page)
    item = _exact_text(page.locator(selectors.FS_MODULE_OUTLINE_NAME), symbol)
    if item is None:
        return {"definitionFound": False, "symbol": symbol, "reason": "exact outline symbol row not found"}
    item.click()
    page.wait_for_timeout(250)
    after = _ace_cursor(page)
    line_tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", str(after.get("lineText", "")))
    target_verified = bool(after.get("found")) and symbol in line_tokens
    cursor_changed = (before.get("row"), before.get("column")) != (after.get("row"), after.get("column"))
    return {
        "definitionFound": target_verified,
        "symbol": symbol,
        "beforeCursor": before,
        "cursor": after,
        "cursorChanged": cursor_changed,
        "alreadyAtDefinition": target_verified and not cursor_changed,
        "navigation": "module-outline",
    }


def _insert_source_text(
    page: Any,
    snippet: str,
    *,
    row: int | None = None,
    column: int | None = None,
) -> dict[str, Any]:
    """Insert caller-provided FeatureScript text through the Ace API."""
    before_commit = actions.commit_button_state(page)
    result = page.evaluate(
        """
        (args) => {
          const el = document.querySelector('.ace_editor');
          const ed = el && ((el.env && el.env.editor) || (window.ace && window.ace.edit(el)));
          if (!ed) return {snippetInserted: false, reason: 'FeatureScript editor not found'};
          const before = ed.getValue();
          const cursor = ed.getCursorPosition();
          const row = Number.isInteger(args.row) ? args.row : cursor.row;
          const column = Number.isInteger(args.column) ? args.column : cursor.column;
          ed.session.insert({row, column}, args.snippet);
          const after = ed.getValue();
          return {
            snippetInserted: after.length === before.length + args.snippet.length,
            row,
            column,
            beforeLength: before.length,
            afterLength: after.length,
            insertedLength: args.snippet.length,
            sourceChanged: before !== after,
          };
        }
        """,
        {"snippet": snippet, "row": row, "column": column},
    )
    if not isinstance(result, dict):
        return {"snippetInserted": False, "reason": "Ace insertion returned no state"}
    after_commit = actions.commit_button_state(page)
    dirty = after_commit.get("found") and after_commit.get("disabled") is False
    result.update({
        "snippetInserted": bool(result.get("snippetInserted")) and dirty,
        "commitDirty": dirty,
        "commitBefore": before_commit,
        "commitAfter": after_commit,
    })
    return result


def fs_insert_snippet(
    page: Any,
    *,
    row: int | None = None,
    column: int | None = None,
) -> dict[str, Any]:
    """Invoke the verified Ace 插入代码段 command and verify its exact delta."""
    before = actions.read_featurescript_editor(page)
    if before is None:
        return {"snippetInserted": False, "reason": "FeatureScript editor not found"}
    before_commit = actions.commit_button_state(page)
    point = page.evaluate(
        """
        (args) => {
          const el = document.querySelector('.ace_editor');
          const ed = el && ((el.env && el.env.editor) || (window.ace && window.ace.edit(el)));
          if (!ed) return null;
          const cursor = ed.getCursorPosition();
          const row = Number.isInteger(args.row) ? args.row : cursor.row;
          const column = Number.isInteger(args.column) ? args.column : cursor.column;
          ed.moveCursorTo(row, column);
          ed.clearSelection();
          ed.renderer.scrollCursorIntoView();
          const screen = ed.renderer.textToScreenCoordinates(row, column);
          return {row, column, x: screen.pageX, y: screen.pageY};
        }
        """,
        {"row": row, "column": column},
    )
    if not isinstance(point, dict):
        return {"snippetInserted": False, "reason": "Ace cursor coordinates unavailable"}
    page.mouse.click(point["x"], point["y"], button="right")
    command = _exact_text(page.locator(selectors.TAB_CONTEXT_MENU_ITEM), "插入代码段")
    if command is None:
        return {"snippetInserted": False, "reason": "exact 插入代码段 command not found", "cursor": point}
    command.click()
    page.wait_for_timeout(250)
    after = actions.read_featurescript_editor(page)
    after_commit = actions.commit_button_state(page)
    if not isinstance(after, str):
        return {"snippetInserted": False, "reason": "FeatureScript source unreadable after command"}
    prefix = 0
    while prefix < min(len(before), len(after)) and before[prefix] == after[prefix]:
        prefix += 1
    suffix = 0
    while suffix < min(len(before) - prefix, len(after) - prefix) and before[-1 - suffix] == after[-1 - suffix]:
        suffix += 1
    inserted = after[prefix:len(after) - suffix if suffix else len(after)]
    dirty = after_commit.get("found") and after_commit.get("disabled") is False
    return {
        "snippetInserted": bool(inserted) and len(after) > len(before) and dirty,
        "cursor": {"row": point["row"], "column": point["column"]},
        "beforeLength": len(before),
        "afterLength": len(after),
        "insertedLength": len(inserted),
        "insertedPreview": inserted[:500],
        "commitDirty": dirty,
        "commitBefore": before_commit,
        "commitAfter": after_commit,
        "command": "插入代码段",
    }


def fs_insert_parameter(
    page: Any,
    *,
    parameter_source: str = "",
    row: int | None = None,
    column: int | None = None,
) -> dict[str, Any]:
    """Insert a Length parameter template or explicit parameter source."""
    if parameter_source:
        before_commit = actions.commit_button_state(page)
        result = _insert_source_text(page, parameter_source, row=row, column=column)
        after_commit = actions.commit_button_state(page)
        dirty = after_commit.get("found") and after_commit.get("disabled") is False
        return {
            "parameterInserted": bool(result.get("snippetInserted")) and dirty,
            "mode": "source",
            "commitDirty": dirty,
            "commitBefore": before_commit,
            "commitAfter": after_commit,
            **result,
        }
    before = actions.read_featurescript_editor(page)
    if before is None:
        return {"parameterInserted": False, "reason": "FeatureScript editor not found"}
    button = page.locator(selectors.FS_TOOLBAR).locator(selectors.FS_TOOL_BUTTON).filter(has_text="Length parameter")
    if button.count() == 0:
        return {"parameterInserted": False, "reason": "Length parameter toolbar button not found"}
    if row is not None or column is not None:
        page.evaluate(
            """
            (args) => {
              const el = document.querySelector('.ace_editor');
              const ed = el && ((el.env && el.env.editor) || (window.ace && window.ace.edit(el)));
              if (!ed) return false;
              const cursor = ed.getCursorPosition();
              ed.moveCursorTo(Number.isInteger(args.row) ? args.row : cursor.row,
                              Number.isInteger(args.column) ? args.column : cursor.column);
              ed.clearSelection();
              ed.focus();
              return true;
            }
            """,
            {"row": row, "column": column},
        )
    before_commit = actions.commit_button_state(page)
    button.first.click()
    page.wait_for_timeout(300)
    after = actions.read_featurescript_editor(page)
    after_commit = actions.commit_button_state(page)
    dirty = after_commit.get("found") and after_commit.get("disabled") is False
    return {
        "parameterInserted": isinstance(after, str) and after != before and dirty,
        "mode": "toolbar",
        "beforeLength": len(before),
        "afterLength": len(after) if isinstance(after, str) else None,
        "sourceChanged": isinstance(after, str) and after != before,
        "commitDirty": dirty,
        "commitBefore": before_commit,
        "commitAfter": after_commit,
    }


def fs_toggle_fold(page: Any, *, row: int | None = None, action: str = "toggle") -> dict[str, Any]:
    """Fold, unfold, or toggle the fold at an Ace row and return all folds."""
    result = page.evaluate(
        """
        (args) => {
          const el = document.querySelector('.ace_editor');
          const ed = el && ((el.env && el.env.editor) || (window.ace && window.ace.edit(el)));
          if (!ed) return {foldChanged: false, reason: 'FeatureScript editor not found'};
          const targetRow = Number.isInteger(args.row) ? args.row : ed.getCursorPosition().row;
          const serialize = () => (ed.session.getAllFolds ? ed.session.getAllFolds() : []).map(fold => ({
            startRow: fold.start.row,
            startColumn: fold.start.column,
            endRow: fold.end.row,
            endColumn: fold.end.column,
            placeholder: String(fold.placeholder || ''),
          }));
          const before = serialize();
          ed.moveCursorTo(targetRow, 0);
          const command = args.action === 'fold' ? 'fold' : (args.action === 'unfold' ? 'unfold' : 'toggleFoldWidget');
          ed.execCommand(command);
          const after = serialize();
          const changed = JSON.stringify(before) !== JSON.stringify(after);
          const targetFolded = after.some(fold => fold.startRow <= targetRow && fold.endRow >= targetRow);
          return {
            foldChanged: changed,
            foldStateApplied: args.action === 'toggle' ? changed : (args.action === 'fold' ? targetFolded : !targetFolded),
            targetFolded,
            alreadyInState: !changed && ((args.action === 'fold' && targetFolded) || (args.action === 'unfold' && !targetFolded)),
            action: args.action,
            row: targetRow,
            beforeFolds: before,
            foldedRanges: after,
            foldCount: after.length,
          };
        }
        """,
        {"row": row, "action": action},
    )
    return result if isinstance(result, dict) else {"foldChanged": False, "reason": "Ace fold command returned no state"}


def _dialog_values(page: Any) -> dict[str, str]:
    result = page.evaluate(
        """
        () => {
          const dialog = document.querySelector('.feature-dialog');
          if (!dialog) return {};
          const result = {};
          for (const input of dialog.querySelectorAll('input, textarea, select')) {
            const owner = input.closest('[data-parameter-id], [parameter-id]');
            const key = input.getAttribute('name') || input.id ||
              owner?.getAttribute('data-parameter-id') || owner?.getAttribute('parameter-id') ||
              input.getAttribute('aria-label') || '';
            if (key) result[key] = input.type === 'checkbox' ? String(input.checked) : String(input.value || '');
          }
          return result;
        }
        """
    )
    return result if isinstance(result, dict) else {}


def edit_feature_parameters(
    page: Any,
    feature_name: str,
    parameters: dict[str, Any],
    *,
    accept: bool = True,
) -> dict[str, Any]:
    """Open a custom feature dialog, update named fields, and optionally accept."""
    row = page.locator(selectors.PS_USER_FEATURE).filter(has_text=feature_name)
    if row.count() != 1:
        return {"parametersApplied": False, "reason": f"feature {feature_name!r} must match exactly one row"}
    row.first.dblclick()
    dialog = page.locator(selectors.PS_FEATURE_DIALOG).first
    try:
        dialog.wait_for(state="visible", timeout=10_000)
    except Exception as exc:  # noqa: BLE001
        return {"parametersApplied": False, "reason": f"feature dialog did not open: {exc}"}
    before = _dialog_values(page)
    missing = []
    updated = []
    for key, value in parameters.items():
        locator = dialog.locator(
            f'[data-parameter-id="{key}"] input, [parameter-id="{key}"] input, '
            f'input[name="{key}"], textarea[name="{key}"], select[name="{key}"], #{key}'
        )
        if locator.count() == 0:
            container = dialog.locator(".parameter-item, .feature-parameter").filter(has_text=str(key))
            locator = container.locator("input, textarea, select") if container.count() else locator
        if locator.count() == 0:
            missing.append(str(key))
            continue
        target = locator.first
        if isinstance(value, bool):
            checked = target.is_checked()
            if checked != value:
                target.click()
        else:
            target.fill(str(value))
        updated.append(str(key))
    after = _dialog_values(page)
    desired = {key: str(value).lower() if isinstance(value, bool) else str(value) for key, value in parameters.items()}
    readback_ok = all(str(after.get(key, "")).lower() == value.lower() for key, value in desired.items())
    accepted = False
    if accept and not missing and readback_ok:
        button = dialog.locator(selectors.PS_FEATURE_DIALOG_ACCEPT)
        if button.count() == 0:
            button = page.locator(selectors.PS_FEATURE_DIALOG_ACCEPT)
        if button.count() > 0:
            button.first.click()
            page.wait_for_timeout(500)
            accepted = page.locator(selectors.PS_FEATURE_DIALOG).count() == 0
    feature_state = actions.read_partstudio_features(page) if accepted else {"features": []}
    matching_features = [
        item for item in feature_state.get("features", [])
        if feature_name.lower() in str(item.get("name", "")).lower()
    ]
    regeneration_ok = len(matching_features) == 1 and not matching_features[0].get("hasError")
    persisted = {}
    persistence_ok = False
    if accepted and regeneration_ok:
        row.first.dblclick()
        reopened = page.locator(selectors.PS_FEATURE_DIALOG).first
        try:
            reopened.wait_for(state="visible", timeout=5_000)
            persisted = _dialog_values(page)
            persistence_ok = all(str(persisted.get(key, "")).lower() == value.lower() for key, value in desired.items())
        except Exception:
            persistence_ok = False
        finally:
            page.keyboard.press("Escape")
    return {
        "parametersApplied": not missing and len(updated) == len(parameters) and readback_ok and accepted and regeneration_ok and persistence_ok,
        "featureName": feature_name,
        "updated": updated,
        "missing": missing,
        "before": before,
        "after": after,
        "readbackOk": readback_ok,
        "accepted": accepted,
        "regenerationOk": regeneration_ok,
        "persisted": persisted,
        "persistenceOk": persistence_ok,
        "featureState": matching_features,
    }


def fs_watch_part_studio(
    page: Any,
    part_studio: str,
    *,
    mode: str = "watch",
) -> dict[str, Any]:
    """Select one exact watch/configure target and verify toolbar readback."""
    prefix = "监控" if mode == "watch" else "配置文件"
    desired = f"{prefix} {part_studio}"
    root = page.locator(selectors.FS_WATCH_CONFIG_MENU)
    current = page.locator(selectors.FS_WATCH_CONFIG_CURRENT)
    if root.count() != 1 or current.count() != 1:
        return {"watchConfigured": False, "reason": "watch/configure toolbar control not found uniquely"}
    before = current.first.inner_text().strip()
    if before == desired:
        return {
            "watchConfigured": True,
            "mode": mode,
            "partStudio": part_studio,
            "before": before,
            "after": before,
            "changed": False,
            "alreadyConfigured": True,
            "compileStatus": actions.read_featurescript_compile_status(page),
        }
    opener = page.locator(selectors.FS_WATCH_CONFIG_OPEN)
    if opener.count() != 1:
        return {"watchConfigured": False, "reason": "watch/configure dropdown opener not found uniquely"}
    opener.first.click()
    items = page.locator(selectors.FS_WATCH_CONFIG_ITEM)
    try:
        items.first.wait_for(state="visible", timeout=5_000)
    except Exception as exc:  # noqa: BLE001
        return {"watchConfigured": False, "reason": f"watch/configure dropdown did not open: {exc}"}
    labels = [
        items.nth(index).inner_text().strip()
        for index in range(items.count())
        if items.nth(index).is_visible() and items.nth(index).inner_text().strip()
    ]
    target = _exact_text(items, desired)
    if target is None:
        return {"watchConfigured": False, "desired": desired, "menuItems": labels, "reason": "exact watch/configure target not found"}
    target.click()
    try:
        page.wait_for_function(
            "(args) => { const el = document.querySelector(args.selector); return !!el && (el.innerText || el.textContent || '').trim() === args.desired; }",
            {"selector": selectors.FS_WATCH_CONFIG_CURRENT, "desired": desired},
            timeout=10_000,
        )
    except Exception:
        pass
    after = current.first.inner_text().strip()
    return {
        "watchConfigured": after == desired,
        "mode": mode,
        "partStudio": part_studio,
        "before": before,
        "after": after,
        "changed": before != after,
        "alreadyConfigured": False,
        "menuItems": labels,
        "compileStatus": actions.read_featurescript_compile_status(page),
    }


def open_doc_menu(page: Any, command: str = "") -> dict[str, Any]:
    """Open the document-name menu and optionally trigger one exact command."""
    button = page.locator(DOC_NAME)
    if button.count() == 0:
        return {"menuOpened": False, "reason": "document name control not found"}
    button.first.click()
    menu = page.locator(DOC_MENU).first
    try:
        menu.wait_for(state="visible", timeout=5_000)
    except Exception as exc:  # noqa: BLE001
        return {"menuOpened": False, "reason": f"document menu did not open: {exc}"}
    rows = menu.locator("a, button, li")
    items = [rows.nth(index).inner_text().strip() for index in range(rows.count()) if rows.nth(index).inner_text().strip()]
    triggered = False
    if command:
        target = _exact_text(rows, command)
        if target is not None:
            target.click()
            triggered = True
    return {
        "menuOpened": not command or triggered,
        "menuVisible": True,
        "items": items,
        "command": command,
        "commandTriggered": triggered,
    }


def set_panel_filter(page: Any, query: str) -> dict[str, Any]:
    """Set the left-panel filter and verify the visible tree narrows."""
    root = page.locator(PANEL_ROOT).first
    field = page.locator(PANEL_FILTER).first
    if root.count() == 0 or field.count() == 0:
        return {"filterApplied": False, "reason": "left-panel filter not found"}
    rows = root.locator(selectors.PS_FEATURE_LIST_ITEM)
    before = _visible_count(rows)
    field.fill(query)
    page.wait_for_timeout(250)
    after = _visible_count(rows)
    value = field.input_value()
    return {
        "filterApplied": value == query and after <= before,
        "query": query,
        "inputValue": value,
        "beforeCount": before,
        "afterCount": after,
        "treeNarrowed": after < before,
    }


def _panel_state(page: Any, panel_selector: str = PANEL_CONTENT) -> dict[str, Any]:
    result = page.evaluate(
        """
        (selector) => {
          const panel = document.querySelector(selector);
          if (!panel) return {present: false, visible: false, x: 0, width: 0};
          const rect = panel.getBoundingClientRect();
          return {present: true, visible: !!panel.offsetParent && rect.width > 20, x: rect.x, width: rect.width, height: rect.height};
        }
        """,
        panel_selector,
    )
    return result if isinstance(result, dict) else {"present": False, "visible": False, "width": 0}


def toggle_left_panel(
    page: Any,
    *,
    target: str = "toggle",
    panel_selector: str = PANEL_CONTENT,
    splitter_selector: str = PANEL_SPLITTERS,
    expanded_width: int = 200,
) -> dict[str, Any]:
    """Collapse or expand the left panel by dragging its vertical splitter."""
    before = _panel_state(page, panel_selector)
    desired = not before.get("visible") if target == "toggle" else target == "show"
    if bool(before.get("visible")) == desired:
        return {"panelToggled": True, "target": target, "before": before, "after": before, "changed": False}
    splitter = page.evaluate(
        """
        (args) => {
          const candidates = Array.from(document.querySelectorAll(args.selector))
            .map(el => ({el, rect: el.getBoundingClientRect()}))
            .filter(item => item.rect.height > 100 && item.rect.width <= 8);
          if (!candidates.length) return null;
          candidates.sort((a, b) => Math.abs(a.rect.x - args.targetX) - Math.abs(b.rect.x - args.targetX));
          const r = candidates[0].rect;
          return {x: r.x + r.width / 2, y: r.y + r.height / 2};
        }
        """,
        {"selector": splitter_selector, "targetX": before.get("x", 0) + before.get("width", 0)},
    )
    if not isinstance(splitter, dict):
        return {"panelToggled": False, "target": target, "before": before, "reason": "vertical panel splitter not found"}
    page.mouse.move(splitter["x"], splitter["y"])
    page.mouse.down()
    target_x = before.get("x", 0) + (expanded_width if desired else 8)
    page.mouse.move(target_x, splitter["y"], steps=5)
    page.mouse.up()
    page.wait_for_timeout(250)
    after = _panel_state(page, panel_selector)
    return {
        "panelToggled": bool(after.get("visible")) == desired,
        "target": target,
        "before": before,
        "after": after,
        "changed": bool(before.get("visible")) != bool(after.get("visible")),
    }


def read_selection_preview(page: Any, selector: str = SELECTION_PREVIEW) -> dict[str, Any]:
    """Read a visible selection/tab-preview card without changing selection."""
    result = page.evaluate(
        """
        (selector) => {
          const candidate = Array.from(document.querySelectorAll(selector)).find(el => el.offsetParent);
          if (!candidate) return {previewFound: false, text: '', fields: []};
          const fields = Array.from(candidate.querySelectorAll('[aria-label], [title], dt, dd')).map(el => ({
            label: el.getAttribute('aria-label') || el.getAttribute('title') || (el.tagName === 'DT' ? (el.textContent || '').trim() : ''),
            value: (el.innerText || el.textContent || '').trim(),
          })).filter(item => item.label || item.value);
          return {previewFound: true, text: (candidate.innerText || candidate.textContent || '').trim(), fields};
        }
        """,
        selector,
    )
    return result if isinstance(result, dict) else {"previewFound": False, "text": "", "fields": []}


def _tab_locator(page: Any, *, element_id: str = "", element_name: str = "") -> Any:
    locator = page.locator(
        f'{selectors.TAB_BAR_TAB}[data-id="{element_id}"]' if element_id else selectors.TAB_BAR_TAB
    )
    return locator if element_id else locator.filter(has_text=element_name)


def element_context_menu(page: Any, *, element_id: str = "", element_name: str = "") -> dict[str, Any]:
    """Open a document-element tab context menu and return its visible items."""
    tab = _tab_locator(page, element_id=element_id, element_name=element_name)
    if tab.count() == 0:
        return {"contextMenuOpened": False, "reason": "document element tab not found"}
    actions.dismiss_stale_context_menu(page)
    tab.first.click(button="right")
    menu = page.locator(selectors.TAB_CONTEXT_MENU).first
    try:
        menu.wait_for(state="visible", timeout=5_000)
    except Exception as exc:  # noqa: BLE001
        return {"contextMenuOpened": False, "reason": f"context menu did not open: {exc}"}
    rows = page.locator(selectors.TAB_CONTEXT_MENU_ITEM)
    items = [
        rows.nth(index).inner_text().strip()
        for index in range(rows.count())
        if rows.nth(index).is_visible() and rows.nth(index).inner_text().strip()
    ]
    return {
        "contextMenuOpened": bool(items),
        "elementId": element_id,
        "elementName": element_name,
        "items": items,
    }


def duplicate_element(
    page: Any,
    *,
    element_id: str = "",
    element_name: str = "",
    new_name: str = "",
) -> dict[str, Any]:
    """Copy one visible document element and verify a new tab appears."""
    before = actions.list_document_tabs(page).get("tabs", [])
    opened = element_context_menu(page, element_id=element_id, element_name=element_name)
    if not opened.get("contextMenuOpened"):
        return {"duplicated": False, **opened}
    item = _exact_text(page.locator(selectors.TAB_CONTEXT_MENU_ITEM), "复制")
    if item is None:
        return {"duplicated": False, **opened, "reason": "exact 复制 menu item not found"}
    item.click()
    dialog = page.locator(".copy-element-dialog, [class*='copy'][class*='dialog']")
    if dialog.count() > 0:
        if new_name:
            field = dialog.first.locator("input")
            if field.count() > 0:
                field.first.fill(new_name)
        accept = dialog.first.locator(selectors.DIALOG_ACCEPT)
        if accept.count() > 0:
            accept.first.click()
    before_ids = {item.get("id") for item in before if item.get("id")}
    try:
        page.wait_for_function(
            """
            (ids) => Array.from(document.querySelectorAll('.os-tab-bar-tab'))
              .map(el => el.getAttribute('data-id')).filter(Boolean)
              .filter(id => !ids.includes(id)).length === 1
            """,
            list(before_ids),
            timeout=10_000,
        )
    except Exception:
        pass
    after = actions.list_document_tabs(page).get("tabs", [])
    created = [item for item in after if item.get("id") and item.get("id") not in before_ids]
    source_still_present = any(
        item.get("id") == element_id for item in after
    ) if element_id else any(item.get("name") == element_name for item in after)
    return {
        "duplicated": len(created) == 1 and len(after) == len(before) + 1 and source_still_present,
        "sourceElementId": element_id,
        "sourceElementName": element_name,
        "newTabs": created,
        "sourceStillPresent": source_still_present,
        "beforeCount": len(before),
        "afterCount": len(after),
    }


def notifications_status(page: Any, *, open_drawer: bool = False) -> dict[str, Any]:
    """Read the unread notification count and optionally the visible drawer."""
    root = page.locator(NOTIFICATIONS)
    if root.count() == 0:
        return {"notificationsRead": False, "reason": "notification control not found"}
    text = root.first.inner_text().strip()
    match = re.search(r"\d+", text)
    if open_drawer:
        root.first.click()
        page.wait_for_timeout(200)
    drawer = page.locator(NOTIFICATIONS_DRAWER)
    drawer_text = drawer.first.inner_text().strip() if drawer.count() else ""
    return {
        "notificationsRead": True,
        "unreadCount": int(match.group(0)) if match else 0,
        "drawerOpened": bool(open_drawer and drawer.count()),
        "drawerText": drawer_text,
    }


def share_document(page: Any) -> dict[str, Any]:
    """Open the document share dialog without changing permissions."""
    button = page.locator(SHARE_BUTTON).filter(has_text="共享")
    if button.count() == 0:
        return {"shareOpened": False, "reason": "share button not found"}
    button.first.click()
    dialog = page.locator(SHARE_DIALOG)
    try:
        dialog.first.wait_for(state="visible", timeout=5_000)
    except Exception as exc:  # noqa: BLE001
        return {"shareOpened": False, "reason": f"share dialog did not open: {exc}"}
    text = dialog.first.inner_text().strip()
    return {"shareOpened": True, "dialogText": text[:1000]}


def view_orientation(
    page: Any,
    *,
    orientation: str = "",
    point: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Read the view-cube state or click a requested orientation point."""
    cube = page.locator(VIEW_CUBE)
    if cube.count() == 0:
        return {"orientationRead": False, "orientationSet": False, "reason": "view cube not found"}
    box = cube.first.bounding_box()
    if not box:
        return {"orientationRead": False, "orientationSet": False, "reason": "view cube is not visible"}
    before = cube.first.screenshot()
    before_sha = hashlib.sha256(before).hexdigest()
    if not orientation and point is None:
        return {
            "orientationRead": True,
            "orientationSet": False,
            "orientation": "visual-state",
            "viewCubeSha256": before_sha,
            "bounds": box,
        }
    normalized = {
        "front": (0.50, 0.62),
        "back": (0.50, 0.42),
        "top": (0.50, 0.22),
        "bottom": (0.50, 0.82),
        "left": (0.26, 0.58),
        "right": (0.74, 0.58),
        "iso": (0.70, 0.28),
    }
    if point is not None:
        x = box["x"] + float(point["x"])
        y = box["y"] + float(point["y"])
    elif orientation in normalized:
        px, py = normalized[orientation]
        x = box["x"] + box["width"] * px
        y = box["y"] + box["height"] * py
    else:
        return {"orientationRead": True, "orientationSet": False, "reason": f"unsupported orientation {orientation!r}"}
    page.mouse.click(x, y)
    page.wait_for_timeout(500)
    after = cube.first.screenshot()
    after_sha = hashlib.sha256(after).hexdigest()
    return {
        "orientationRead": True,
        "orientationSet": before_sha != after_sha,
        "orientation": orientation or "custom",
        "beforeSha256": before_sha,
        "afterSha256": after_sha,
        "clickPoint": {"x": x, "y": y},
    }
