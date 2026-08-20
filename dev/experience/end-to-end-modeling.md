# 端到端 FS 建模闭环（新文档，0 配额）实测记录

目标：在**新建文档**里完成「FS 上传+编译 → 创建版本 → Part Studio 实例化自定义特征 → 建模」，
不污染生产文档，全程 0 次 Onshape REST API。

## 1. 已实测跑通的步骤

| # | 步骤 | 工具/选择器 | 实测结果 |
|---|---|---|---|
| 1 | 创建新文档 | `browser_create_document(name)`：`#create-new-type` → `.create-new-document` → `#document-name-input` 填名 → `.new-document-dialog .btn-primary` | `fs-modeling-test`，did `4774246bad5e29f4c98bf632`，wid `721b2be4e4dceb696e8576e1` |
| 2 | 新建 Feature Studio 标签 | `.document-tabs-button` 下拉 → `a.dropdown-item`「创建 Feature Studio」（下拉项隐藏，用 JS click） | 标签 `Feature Studio 1`，eid `b08754f2be050e1c13a6bdf8` |
| 3 | 部署 FS 源码 | `browser_deploy_featurescript(script)`：写 Ace → 点「提交」 | 81→23875 字符，`deployed:true, verified:true` |
| 4 | 创建版本 | 插入对话框「当前文档」→ 提示「没有可用的特征。… 创建一个版本」→ `.select-item-prompt-save-version a` → `.version-or-workspace-dialog` → **取消勾选** `.publish-custom-features-checkbox` → 点「创建」 | 版本 `V1`，对话框显示特征可用 |
| 5 | 插入特征 | 插入对话框特征行 `.select-item-dialog-item-row.child-item-container` **双击**（`os-double-click=selectChildInsertableThenClose`） | 特征进入特征树，`feature-id` 已存在 |

## 2. 关键机制（易错点）

- **插入 = 双击，不是「插入」按钮**：对话框底部 `.standard-content-insert-button` 实际尺寸为
  `[0,0,0,0]`（不可点）。特征行有 `os-single-double-click` 指令：
  - 单击 `os-click=selectChildInsertable` → 只选中（`os-selected`）；
  - **双击** `os-double-click=selectChildInsertableThenClose` → 选中并关闭对话框 = 插入。
- **版本 ≠ 发布**：`version-or-workspace-dialog` 勾选「发布自定义特征」后按钮变为
  「创建和发布」，但发布有额外硬要求（公开文档、PDF、FeatureScript 说明、已在 Part Studio
  使用等）。仅插入本机文档只需**不勾选发布**直接「创建」。
- 工具栏「添加自定义特征」的文字标签 `.tool-label.hide-in-toolbar` 隐藏，需按
  `.toolbar-item` 的 textContent 找到后点内部 `.tool.is-button`。
- 代理网络慢：文档/标签/对话框加载都慢，每个导航后要轮询等待目标元素出现，不要固定短等待。

## 3. 关键修正：Part Studio 需要「应用」特征

之前走「添加自定义特征」对话框双击只会产生 `not-computed` 行（`零件数 (0)`）。
正确流程是**手动应用**：

1. 点工具栏按钮 **`此工作区中的自定义特征`**（`.tool[title="此工作区中的自定义特征"]`）；
2. 下拉里点特征名（`.os-tool-dropdown-content`）；
3. 弹出参数对话框（`.feature-dialog`，含 Base radius/Base height/… 全部默认值）；
4. 点勾选 `.ns-dialog-button-ok.button-ok` 接受 → 特征计算。

实测最终结果：
- 特征树 `特征 (5)`，含 `Bc Branch cable trophy display 1`（isUserFeature）
- 零件列表 `零件数 (132) base plaqueInsert_blank rootCollars_0 …`
- 即「上传+编译+版本+应用+建模」全链路 0 配额闭环成功。

## 4. 已落地工具（0 配额）

- `browser_create_document`、`browser_create_document_version`、`browser_insert_custom_feature`、
  `browser_get_page_tabs`、`browser_get_partstudio_features`、`browser_deploy_featurescript`、
  `browser_read_featurescript`、`browser_open_document`、`browser_reconnect`。
- `browser_click` 支持 `selector+text` 精确定位与 `double` 双击。
