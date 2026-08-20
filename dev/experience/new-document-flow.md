# 创建新文档流程（浏览器无配额，已实测）

目标：在新文档里跑「FS 上传+编译+建模」闭环，不污染生产文档。

## 1. 创建文档（已实现并实测）

工具：`browser_create_document(name)`（0 配额，需 `confirm_mutation=true`）。

实测流程与选择器：
1. 导航到 documents 页；
2. 点 `#create-new-type`（「创建」按钮）→ 弹出 `.os-create-menu.create-new-type-menu`；
3. 点 `button.create-new-document`（「文档…」）→ 弹出 `.new-document-dialog`；
4. 名称输入 `#document-name-input`（默认「无标题文档」），Playwright `locator.fill()` 即可触发 Angular 绑定；
5. 点 `.new-document-dialog .btn-primary`（「创建」，id `model-name-dialog-ok`）。

实测结果：
- 新文档名 `fs-modeling-test`
- URL `https://cad.onshape.com/documents/4774246bad5e29f4c98bf632/w/721b2be4e4dceb696e8576e1`
- documentId `4774246bad5e29f4c98bf632`，workspaceId `721b2be4e4dceb696e8576e1`
- 新文档默认标签：`Part Studio 1` + `Assembly 1`，另有 `+` 按钮（`.document-tabs-button`）。

## 2. 新文档里的后续步骤（待登录后继续）

- `+` 按钮（`.document-tabs-button`）下拉含「创建 Feature Studio」等项，用于新建 FS 标签；
- 把 FS 源码 deploy 进新建的 Feature Studio；
- 在 FS 页创建版本（插入对话框提示「没有可用的特征。… 创建一个版本」，说明未发布版本前自定义特征不可插入）；
- 切回 `Part Studio 1`，点工具栏「添加自定义特征」（`.toolbar-item` 内 `.tool.is-button`，
  文本标签隐藏），对话框 `.feature-studio-insert-dialog` 里「当前文档」标签选特征后点「插入」；
- 用 `browser_get_partstudio_features` 验证特征树出现自定义特征且零件数>0。

## 3. 当前状态

- `browser_create_document` 已落地并有单元测试（77 测试通过）。
- 端到端余下步骤依赖浏览器登录态；会话过期后需人工在 Windows 的 Edge 窗口完成登录。
