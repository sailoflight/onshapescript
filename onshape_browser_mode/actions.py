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
    FS_COMMIT_BUTTON,
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
            return { name, active: cls.includes('active') };
          });
          const plusButton = document.querySelector('.document-tabs-button');
          return { tabs, hasPlusButton: !!plusButton };
        }
        """
    )


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
    """Insert a custom FeatureScript feature into a Part Studio (0 API quota).

    Opens the add-custom-feature dialog, switches to the 当前文档 tab, selects
    the feature by name, and clicks 插入. Returns the resulting feature-tree
    state when successful, or a clear blocker (e.g. the Feature Studio needs a
    version created first) when insertion is not possible.
    """
    from onshape_browser_mode.selectors import INSERT_FEATURE_DIALOG, INSERT_FEATURE_TAB

    if part_studio_tab:
        page.locator(f".os-tab-bar-tab:has-text('{part_studio_tab}')").first.click()
        page.wait_for_timeout(4000)

    opened = open_insert_custom_feature_dialog(page)
    if not opened.get("clicked"):
        return {**opened, "inserted": False}

    info = read_insert_dialog(page)
    if not info.get("present"):
        return {**opened, "inserted": False, "reason": "insert dialog did not appear"}

    # Switch to the 当前文档 tab if it is not already active.
    page.evaluate(
        """
        () => {
          const tabs = Array.from(document.querySelectorAll('.os-dialog-tab'));
          const tab = tabs.find(el => (el.textContent || '').trim() === '当前文档');
          if (tab) tab.click();
          return !!tab;
        }
        """
    )
    page.wait_for_timeout(2500)

    info = read_insert_dialog(page)
    if info.get("promptSaveVersion") or "没有可用的特征" in (info.get("warning") or ""):
        return {
            "inserted": False,
            "reason": "Feature Studio needs a version before the feature is insertable",
            "dialog": info,
        }

    # Onshape's picker inserts on DOUBLE-click of the feature row
    # (os-single-double-click directive: single click selects, double click
    # selects-and-closes = insert). The footer "插入" button is zero-sized in
    # this dialog, so double-click is the reliable path.
    try:
        row = page.locator(".select-item-dialog-item-row.child-item-container").filter(
            has_text=feature_name
        ).first
        count = row.count()
    except Exception:
        count = 0
    if count == 0:
        return {"inserted": False, "reason": f"feature {feature_name!r} not found in insert dialog", "dialog": info}

    try:
        row.dblclick()
        page.wait_for_timeout(8000)
    except Exception as exc:  # noqa: BLE001 - surface as structured result
        return {"inserted": False, "reason": f"double-click failed: {exc}", "dialog": info}

    features = read_partstudio_features(page)
    return {"inserted": True, "features": features, "pageUrl": page.url}


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
