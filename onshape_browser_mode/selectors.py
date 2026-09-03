"""Stable CSS selectors discovered from real Onshape UI exploration.

Kept separate from page logic so dev/button-map findings and the MCP tools
share one source of truth. Prefer these over ad-hoc strings; when a selector
changes, update it here and re-run the zero-quota probes.

Selector evidence: dev/button-map/scan-*.json. Reusable browser behavior and
maintenance guidance: onshape_docs/experience/browser-automation.md.
"""

# Shared document shell (cross-Studio)
DOC_NAME = ".navbar-document-name"
DOC_MENU = ".document-dropdown-menu"
PANEL_ROOT = ".left-content-pane-folder"
PANEL_FILTER = ".left-content-pane-folder .os-search-box-input"
PANEL_CONTENT = ".panel-content-pane"
PANEL_SPLITTERS = ".element-content-splitter-container .os-splitter"
SELECTION_PREVIEW = ".tab-preview, .selection-preview, [class*='selection'][class*='preview']"
NOTIFICATIONS_DRAWER = ".notification-dropdown, .notifications-dropdown, [class*='notification'][class*='dropdown-menu']"
SHARE_BUTTON = ".nav-share"
SHARE_DIALOG = "osx-share-dialog .share-dialog-container"
VIEW_CUBE = ".os-view-cube-bounds"

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
FS_MODULE_OUTLINE_DROPDOWN = ".top-level-symbols-dropdown"
FS_MODULE_OUTLINE_COUNT = ".top-level-symbol-count"
FS_MODULE_OUTLINE_LIST = ".top-level-symbol-list"
FS_MODULE_OUTLINE_ITEM = ".top-level-symbol-item"
FS_MODULE_OUTLINE_ICON = ".top-level-symbol-icon"
FS_MODULE_OUTLINE_NAME = ".top-level-symbol-name"
FS_WATCH_CONFIG_MENU = ".watch-part-studio-menu"
FS_WATCH_CONFIG_OPEN = ".watch-part-studio-menu .os-toolgroup-open-button"
FS_WATCH_CONFIG_CURRENT = ".watch-part-studio-menu .os-tool-command-name"
FS_WATCH_CONFIG_ITEM = ".watch-part-studio-menu .os-tool-dropdown-content .os-menu-tool"
FS_NOTICE_TOGGLE = ".notice-pane-toggle-button"
FS_NOTICE_CONTENT = ".notices-content"
FS_NOTICE_TABLE = ".feature-script-notice-table"
FS_NOTICE_MESSAGE = ".notice-location-message"
FS_NOTICE_LINE = ".notice-location-line-number"
FS_NOTICE_COLUMN = ".notice-location-column-number"

# Ace editor (FeatureScript source)
ACE_EDITOR = ".ace_editor"
ACE_TEXT_INPUT = "textarea.ace_text-input"

# FeatureScript doc popup (hover)
FS_DOC_POPUP = ".os-feature-script-doc-popup-layer"

# Session-timeout dialog
TIMEOUT_DIALOG = ".osx-message"  # "您的 Onshape 会话已超时。您的文档已保存。"
TIMEOUT_RECONNECT_LINK = ".alert-link.osx-message-bubble-link"  # "单击此处重新连接。"
TIMEOUT_CLOSE_BUTTON = ".osx-close"  # "× Close"

# Shared overlay layer used by tab and object context menus
CONTEXT_MENU_LAYER = "#context-menu-layer"

# Document tabs (hidden creation items plus rename/delete tab controls)
DOCUMENT_TABS_BUTTON = ".document-tabs-button"  # document tab tools/analysis button group; not the create-tab control
DOCUMENT_TABS_CREATE_ITEM = "a.dropdown-item"   # e.g. 创建 Feature Studio / 创建 Part Studio
TAB_BAR_TAB = ".os-tab-bar-tab"
TAB_NAME = ".os-tab-name"
TAB_RENAME_INPUT = "element-name input, input.tab-rename, .os-tab-name-input"
TAB_CONTEXT_MENU = "ul.context-menu-list.context-menu-root"
TAB_CONTEXT_MENU_ITEM = "li.context-menu-item"
TAB_CONTEXT_MENU_TEXT = {"delete": "删除", "rename": "重命名", "properties": "属性…", "export": "导出…"}

# Part Studio export dialog (live-observed 2026-08-25)
EXPORT_DIALOG = ".modal.export-dialog"
EXPORT_FILENAME = "#export-filename-input"
EXPORT_FORMAT = "#export-format-dropdown"
EXPORT_STEP_VERSION = "#step-export-version-dropdown"
EXPORT_LATEST_VERSION = "#latest-version-checkbox"
EXPORT_CUSTOM_STEP_UNITS = "#custom-step-units-checkbox"
EXPORT_STEP_UNITS = "[ng-model='options.stepExportUnit']"
EXPORT_OPTIONS = "#export-options-dropdown"
EXPORT_INDIVIDUAL_FILES = "[ng-model='download.shouldExportPartsAsIndividualFiles']"
EXPORT_HIDDEN_ENTITIES = "#export-hidden-entities-checkbox"
EXPORT_SUBMIT = ".modal.export-dialog button.btn-primary[type='submit']"
EXPORT_CANCEL = ".modal.export-dialog button.button-cancel"

# Part Studio (feature tree / toolbar)
PS_FEATURE_LIST_ITEM = ".os-list-item"
PS_USER_FEATURE = ".os-list-item.ns-user-feature"  # custom FeatureScript feature
PS_DEFAULT_FEATURE = ".os-list-item.ns-default-feature"  # Origin/Top/Front/Right
PS_FEATURES_HEADER = ".features-title"  # "特征 (5)"
PS_PART_LIST = ".part-list-container"  # "零件数 (132) base ..."
PS_PART_ROW = ".part-list-container .os-list-item"
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
DRAWING_VIEW_NODES = "[data-view-id], .drawing-view, .view-instance, [class*='DrawingView'], [class*='drawingView']"
ANALYSIS_DIALOG = ".analysis-dialog, .measure-dialog, .mass-properties-dialog, .os-dialog, .xenon-dialog"
ANALYSIS_POPUP = ".analysisControlPopup"
DRAFT_ANALYSIS_DIALOG = "#draft-analysis-view"
DRAFT_DIRECTION = "#draft-analysis-view [data-parameter-id='directionOfPull']"
DRAFT_OPPOSITE_DIRECTION = "#draft-analysis-view [data-parameter-id='oppositePullDirection']"
DRAFT_MINIMUM_ANGLE = "#draft-analysis-view [data-parameter-id='minimumDraftAngle'] input"
DRAFT_PARTS = "#draft-analysis-view [data-parameter-id='draftAnalysisParts']"
