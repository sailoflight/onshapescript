"""Stable CSS selectors discovered from real Onshape UI exploration.

Kept separate from page logic so dev/button-map findings and the MCP tools
share one source of truth. Prefer these over ad-hoc strings; when a selector
changes, update it here and re-run the zero-quota probes.

Source of truth: dev/button-map/scan-*.json and
dev/experience/browser-usage-notes.md.
"""

# Documents list page
DOCUMENTS_SEARCH_BOX = "#search-box"
DOCUMENTS_NOTIFICATION = "#user-notification-status"
DOCUMENTS_CREATE_BUTTON = "#create-new-type"
DOCUMENTS_SCROLL_VIEWPORT = ".ag-body-viewport"  # AG Grid body is the real scroll container
DOCUMENT_LINK = (
    ".document-list-item-name, .document-display-link, .os-document-display-name"
)

# FeatureStudio / FeatureScript page
FS_TAB = "tab-list-item.os-tab-bar-tab"
FS_TAB_NAME = ".os-tab-name"
FS_TOOLBAR = ".os-feature-studio-main-menu-bar"
FS_TOOL_BUTTON = ".tool.is-activatable.is-button"
FS_COMMIT_BUTTON = ".tool.is-activatable.os-primary.is-button"  # text: 提交
FS_COMMIT_TEXT = "提交"
FS_MODULE_OUTLINE = ".top-level-symbols-button"
FS_MODULE_OUTLINE_LABEL = ".top-level-symbols-label"
FS_WATCH_CONFIG_MENU = ".os-menu-tool"  # e.g. 监控/配置文件 <tab name>

# Ace editor (FeatureScript source)
ACE_EDITOR = ".ace_editor"
ACE_TEXT_INPUT = "textarea.ace_text-input"

# FeatureScript doc popup (hover)
FS_DOC_POPUP = ".os-feature-script-doc-popup-layer"

# Session-timeout dialog
TIMEOUT_DIALOG = ".osx-message"  # "您的 Onshape 会话已超时。您的文档已保存。"
TIMEOUT_RECONNECT_LINK = ".alert-link.osx-message-bubble-link"  # "单击此处重新连接。"
TIMEOUT_CLOSE_BUTTON = ".osx-close"  # "× Close"
