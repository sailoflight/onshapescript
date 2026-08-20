"""Zero-quota browser actions for the FeatureScript editor.

These operate on the live Onshape page through Playwright. They never call the
Onshape REST API: reading/writing the Ace editor and clicking the Commit button
all happen in the browser UI, so deploying a FeatureScript script this way
spends 0 API calls.

All functions take a Playwright sync `page` object obtained from
``BrowserSession.start()``.
"""

from __future__ import annotations

from typing import Any

from onshape_browser_mode.selectors import ACE_EDITOR, FS_COMMIT_BUTTON

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
