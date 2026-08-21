"""Stable CSS selectors discovered from real Onshape UI exploration.

Kept separate from page logic so dev/button-map findings and the MCP tools
share one source of truth. Prefer these over ad-hoc strings; when a selector
changes, update it here and re-run the zero-quota probes.

Selector evidence: dev/button-map/scan-*.json. Reusable browser behavior and
maintenance guidance: onshape_docs/experience/browser-automation.md.
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

# Document tabs (hidden creation items plus rename/delete tab controls)
DOCUMENT_TABS_BUTTON = ".document-tabs-button"  # document tab tools/analysis button group; not the create-tab control
DOCUMENT_TABS_CREATE_ITEM = "a.dropdown-item"   # e.g. 创建 Feature Studio / 创建 Part Studio
TAB_BAR_TAB = ".os-tab-bar-tab"
TAB_NAME = ".os-tab-name"
TAB_RENAME_INPUT = "element-name input, input.tab-rename, .os-tab-name-input"
TAB_CONTEXT_MENU = "ul.context-menu-list.context-menu-root"
TAB_CONTEXT_MENU_ITEM = "li.context-menu-item"
TAB_CONTEXT_MENU_TEXT = {"delete": "删除", "rename": "重命名", "properties": "属性…"}

# Part Studio (feature tree / toolbar)
PS_FEATURE_LIST_ITEM = ".os-list-item"
PS_USER_FEATURE = ".os-list-item.ns-user-feature"  # custom FeatureScript feature
PS_DEFAULT_FEATURE = ".os-list-item.ns-default-feature"  # Origin/Top/Front/Right
PS_FEATURES_HEADER = ".features-title"  # "特征 (5)"
PS_PART_LIST = ".part-list-container"  # "零件数 (132) base ..."
PS_TOOLBAR_ITEM = ".toolbar-item"
PS_TOOL_BUTTON = ".tool.is-activatable.is-button"

# Add-custom-feature dialog
INSERT_FEATURE_DIALOG = ".feature-studio-insert-dialog"
INSERT_FEATURE_TAB = ".os-dialog-tab"  # 当前文档 / 其他文档
INSERT_FEATURE_DOC_NAME = ".select-item-dialog-document-name"

# Apply custom feature in this workspace (the REAL apply path)
PS_WORKSPACE_CUSTOM_FEATURE_BTN = '.tool[title="此工作区中的自定义特征"], .tool[data-bs-original-title="此工作区中的自定义特征"]'
PS_WORKSPACE_CUSTOM_FEATURE_ITEM = ".os-tool-dropdown-content"
PS_FEATURE_DIALOG = ".feature-dialog"
PS_FEATURE_DIALOG_ACCEPT = ".ns-dialog-button-ok.button-ok"  # checkmark

# Assembly insert workflow
ASM_INSERT_BUTTON = '.tool[title^="插入零件和装配体"], .tool[data-bs-original-title^="插入零件和装配体"]'
ASM_INSTANCE_ROW = ".ns-tree-root .ns-assembly-instance-row.is-instance"
ASM_INSERT_DIALOG = ".assembly-insert-dialog-wrapper"
ASM_INSERT_ROW = ".select-item-dialog-item.parent-item.os-selectable-item"
DIALOG_ACCEPT = ".ns-dialog-button-ok.button-ok"
ASM_INSERT_ACCEPT = DIALOG_ACCEPT

# Cross-origin Drawing editor
DRAWING_FRAME_URL_PREFIX = "production-drawing-"
DRAWING_IFRAME = 'iframe[src*="production-drawing-"]'
DRAWING_CREATE_DIALOG = ".drawing-create-dialog, .new-drawing-dialog, [class*=\"drawing\"][class*=\"dialog\"]"
