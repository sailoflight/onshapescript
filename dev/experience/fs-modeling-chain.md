# 浏览器无配额 FS 上传+编译+建模 闭环（已实现）

本文件是「完整 FeatureScript 上传 + 编译验证 + Part Studio 实例化建模」全链路的
**实测证据与操作手册**。全程 0 次 Onshape REST API 调用（`network:"browser"`）。

## 1. 闭环三步

```
browser_deploy_featurescript(script)   上传+编译：写 Ace → 点「提交」→ 读回校验 verified
        ↓
browser_get_partstudio_features()      编译+建模验证：特征树出现自定义特征 + 零件数>0
```

### 第一步：上传 + 编译（`browser_deploy_featurescript`）

- `dry_run=true`：纯本地预览，不启动浏览器（返回 sourceLength/lineCount）。
- `dry_run=false` + `confirm_mutation=true`：
  1. 打开目标文档（如不在编辑器页）；
  2. `ed.setValue(script)` 写入 Ace（Ace 变更事件让「提交」按钮 enabled）；
  3. 点「提交」= Onshape 编译并保存（按钮回到 disabled = 提交成功）；
  4. 读回编辑器，`verified:true` 仅当页面源码与提交内容完全一致。
- 实测：23907 字符部署 `deployed:true, verified:true`；恢复 23875 字符同样通过。

### 第二步：编译 + 建模验证（`browser_get_partstudio_features`）

- 读 Part Studio 特征树与零件列表（0 配额只读）。
- **编译成功**：自定义特征出现在特征树 `.os-list-item.ns-user-feature`；
- **建模成功**：`.part-list-container` 显示 `零件数 (N)` 且 N>0。
- 实测（两个 Part Studio 均通过）：
  - `Cable trophy model v1`（elementId `0c7862642d02c53c3dd7cd79`）
  - `Cable trophy model validation`（elementId `d2774ccdb49e6900b9779d74`）
  - 特征树：`特征 (5)`，含 `Bc Branch cable trophy display`（isUserFeature）
  - 零件列表：`零件数 (132) base plaqueInsert_blank rootCollars_0 …`

## 2. 关键选择器（`onshape_browser_mode/selectors.py`）

| 场景 | 选择器 |
|---|---|
| FS 编辑器 | `.ace_editor`（Ace API `ed.getValue()/ed.setValue()`） |
| FS 提交按钮 | `.tool.is-activatable.os-primary.is-button`（文案「提交」） |
| 文档标签 | `.os-tab-bar-tab`（按 `.os-tab-name` 文本精确定位） |
| Part Studio 特征树 | `.os-list-item`、`.ns-user-feature`、`.ns-default-feature`、`.features-title` |
| Part Studio 零件列表 | `.part-list-container` |
| Part Studio 工具栏 | `.toolbar-item`（文字标签隐藏，点内部 `.tool.is-button`） |
| 添加自定义特征对话框 | `.feature-studio-insert-dialog`、`.os-dialog-tab`（当前文档/其他文档） |

## 3. 已知边界

- **新插入自定义特征需要版本**：插入对话框「当前文档」若显示
  「没有可用的特征。… 创建一个版本」，说明 Feature Studio 自上一版本后有未发布
  更改，必须先创建文档版本才能让该 FS 特征进入可插入列表。当前仓库未实现
  `browser_create_document_version` / `browser_insert_custom_feature`（下一轮计划）。
- **更新已实例化特征**：对已实例化的 FS 直接 `browser_deploy_featurescript` 提交后，
  Part Studio 中的特征会自动按新代码重新生成，无需重新插入。
- 浏览器动作有 `[pacing]` 节流（默认 8 次/分钟 + 0.8–2s 随机延迟），真实动作需
  `confirm_mutation=true`。
