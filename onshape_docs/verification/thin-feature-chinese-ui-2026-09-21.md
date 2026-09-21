# 薄特征链的「中文 UI」版重建与 B-rep 验收（2026-09-21）

## 1. 目标与判定标准

用户的原话是「**我其实就是 UI 上显示中文就行**」，所以判定标准有两条，缺一不可：

1. **界面可见**：Part Studio 标签名、23 行特征树的行名（特征表里读到的 `name`）必须是中文；
   只在夹具注释、参数说明或文档里出现中文不算。
2. **几何不变**：重建出来的实体必须与已验证的英文链（`GF Thin Plate`）以及域基线
   **逐族一致**，否则「中文」只是一个长得像的板子。

## 2. 目标身份（活证据）

| 项 | 值 |
|---|---|
| documentId | `1ef2be8f3d45e6f996af24ab` |
| workspaceId | `bac7c0bf31912a956c44d15a` |
| elementId（新 Part Studio） | `72023dd3363ff9b18c8c73bc` |
| 标签名 | `网格底板 2×2` |
| Feature Studio（活定义） | `Thin Native Features` / `e8291d6887c1ffb321f4f868` |
| 用户特征行数 | 23（表头 `特征 (27)` = 23 用户 + 4 基准面） |
| 实体 | `零件数 (1)` `Part 1`，无任何 `hasError` 行 |
| Onshape REST 配额 | **0**（全程浏览器腿） |

树序（reload 后的稳定读，逐行核对过参数）：

```text
TV #gf_pitch = 42 mm 格距：相邻格子中心距
TV #gf_plate_size = 84 mm 2×2 底板外形尺寸
TV #gf_plate_corner = 4 mm 外角圆角半径
TV #gf_socket = 36.3 mm 插槽间隙方孔边长
TV #gf_socket_r = 1.15 mm 插槽圆角半径
TV #gf_lock = 37.7 mm 锁定面方孔边长
TV #gf_lock_r = 1.85 mm 锁定面圆角半径
TV #gf_magnet_d = 6.5 mm 磁铁孔直径
TV #gf_magnet_side = 8 mm 磁铁中心到格子边的距离
TS Thin Sketch Rectangle 1        板体草图（84×84 r4）
TE Thin Extrude 1                 +10 mm 板体
TS Thin Sketch Rectangle 3        插槽间隙草图 z=5    36.3 r1.15
TE Thin Extrude 2                 -0.35 mm 间隙
TS Thin Sketch Rectangle 4        斜坡草图 z=5.35
TE Thin Extrude 3                 -0.7 mm 45°
TS Thin Sketch Rectangle 5        锁定面草图 z=6.05  37.7 r1.85
TE Thin Extrude 4                 -1.8 mm 锁定面
TS Thin Sketch Rectangle 2        喇叭口草图 z=7.85
TE Thin Extrude 5                 -2.15 mm 45° 喇叭口
TS Thin Sketch Circle 1           磁铁孔草图 z=2.6    ⌀6.5 距边 8
TE Thin Extrude 6                 -1.6 mm 孔柱段
TS Thin Sketch Circle 2           磁铁倒角草图 z=4.2
TE Thin Extrude 7                 -0.8 mm 45° 倒角
```

`TS/TE` 的行名模板仍是 ASCII 的（`annotation` 只允许可打印 ASCII），中文在**变量行的
值/说明**上——这正是用户要的「UI 上显示中文」，规则与实测见
`onshape_docs/experience/browser-modeling.md` 第 23 节。

## 3. 为什么必须重建，而不是改注释

`Feature Name Template` 是在特征**被创建**时算进行名的：改 FS 源码不会给已插入的行改名。
本次先按错误假设（「已插入的行会随源码重算」）改过模板，实测证伪——22 行老行名原封不动，
只有新插入的行带上中文说明。于是：

- `dev/fixtures-capture/thin-native-features.fs` 里那条错误注释已改正，写明「模板在创建时
  生效，旧行保持出生时的名字，中文必须重新插入」。
- 中文界面只能靠**重新插一遍**得到，这就是本页记录的重建。

FS 的云端源码与本地文件目前只差这条注释（注释不参与编译，编译结果 0 notice），
因此没有为此再花一次部署。

## 4. 落地方式（两次夹具 + 短路径逐行）

1. 新建 `网格底板 2×2` 标签，手插 `00-var-pitch`、`01-var-plate-size`（`#gf_pitch * 2`
   实测解析为 `84 mm`）。
2. 用轻量夹具 `dev/fixtures-capture/gridfinity-thin-plate-cn-light.json`（`steps[2:16]`，
   14 步）把 02…15 走完，runner 报 14/14，每步 `零件数` 都是 1。
3. 16…22 这 7 步改用**逐行直接调用**的短路径（`verify_commit=false`）：一次调用一个特征，
   接受后立刻返回，随后由本代理读特征表确认行数与行名。原因是重算等待的自适应预算随
   自定义特征数增长（23 行时 `regenerationMs` 已达 64–74 s、`commitSurvivalMs` 166–206 s），
   已经超过单次调用的传输预算，而 runner 的判据要求 `inserted` 为真（短路径下是 `null`），
   所以 runner 无法走这条路。

### 4.1 一个丢失判决的重复行

14 步跑完后表头比预期多 1：期望 17 行，实际 18 行，且行名计数器跳号
（`TSR1, TE1, TSR2, TSR3, TE2, …`）。逐行读参数确认 `TSR2` 与 `TSR3` 参数完全相同
（z=5 / 2×2 / 36.3 / r1.15），即**同一个「插槽间隙草图」步骤插了两次**：第一次的判决在
relay 超时里丢了（行已落地、checkpoint 未记），resume 又插了第二次。
`browser_delete_feature` 删掉这行孤儿草图（命中数唯一，无需 `occurrence`），
删后 17 行、`零件数 (1)`。删除是安全的：它被下一张草图覆盖，没有被任何拉伸消费——
这一条由最终 B-rep 逐族相同反证。

## 5. B-rep 验收：与域基线逐族一致

```text
STEP: onshape_browser_mode/outputs/step_exports/cn-gridfinity-2x2-thin-native/model.step
sha256: 926463e7f88b45f4068ac9917a21a82d819ae0cdd1a329cd788709c2baa96d10   (AP242, mm)
```

| 族 | 面数 | 面积 mm² | 备注 |
|---|---|---|---|
| plane | 94 | 18458.3352 | 水平面 z = 0 / 2.6 / 5.0 / 10.0 |
| cone 45° | 16 | 37.3200 | 插槽斜坡 z 5.35→6.05，ref r1.15 |
| cone 45° | 16 | 223.5216 | 喇叭口 z 7.85→10.0，ref r1.85 |
| cone 45° | 16 | 415.1424 | 磁铁倒角 z 4.2→5.0，ref r3.25 |
| cylinder | 16 | 10.1152 | r1.15 |
| cylinder | 16 | 83.6928 | r1.85 |
| cylinder | 16 | 522.7616 | r3.25（磁铁孔） |
| cylinder | 4 | 251.3276 | r4.00（板体外角） |

- 体积 `39547.5903` mm³、面积 `20002.2154` mm²、面数 `194`，与
  `onshape_docs/verification/thin-feature-rebuild-brep-2026-09-21.md` 记录的英文链
  （STEP sha `6378ff1b609fef98f0f4187dd3a96c582d26942cac275c638f3a643003028239`）
  **完全相同**。
- 因此「中文界面」与「几何正确」两条判定标准同时成立：行名/标签名是中文，B-rep 与基线
  逐族一致。这条链对**顺序**敏感（薄拉伸消费它前面最近一个薄草图发布的区域），逐族相等
  也就证明了 23 行的树序是语义正确的。

复现：

```bash
/home/lijq/code/CadQ/.venv/bin/python onshape_docs/scripts/verify_step_brep.py \
  /mnt/c/MCP/onshapescript/onshape_browser_mode/outputs/step_exports/cn-gridfinity-2x2-thin-native/model.step
```

## 6. 本次一并修掉的代码缺陷（离线 849 测试，0 次真实调用）

| 缺陷 | 修法 | 覆盖 |
|---|---|---|
| 判决丢失后 resume 会插出重复行，而按**名字集合**做差集判定时，重复行让该步骤**每次都判失败** | `created_user_feature_rows` 改成**多重集**差值（`Counter` 带计数） | `test_a_created_row_is_the_excess_over_a_baseline_multiset` |
| 两个同名行无法只删一个 | `browser_delete_feature` 增加 `occurrence`，判据改为计数下降 | `test_an_occurrence_selects_one_of_two_identical_rows` 等 |
| 重算等待预算超过单次调用传输预算，重步骤在 runner 里永远跑不完 | `verify_commit=false` 短路径**跳过**重算等待并如实上报 `skipped` | `test_the_commit_reload_can_be_skipped_without_claiming_success` |
| 标签按**子串** + `.first` 选目标，撞名时点到别的标签，检查 `count() != 1` 永远发现不了 | `actions.resolve_exact_tab` 全名精确匹配 + 按命中 `data-id` 点击；`rename_tab`、`export_browser_step` 都改用它 | 4 条新用例（撞前缀、精确重名、只匹配子串、命中无 id） |

`step_export.py` 的这条修法同时消掉了「导出报错信息指向后续步骤」的问题：之前撞名会点到
`GF Thin Plate (old, 14 rows)`，然后以
`RuntimeError: active Part Studio URL does not match requested document/workspace/element IDs`
失败，把根因藏了起来。

## 7. 边界（本页不声明的东西）

- 本页只验收**这一个**元素与**这一份** STEP；不声明任意夹具、任意顺序都能得到同样 B-rep。
- 云端 `Thin Native Features` 的源码与仓库里 `thin-native-features.fs` **只差一条注释**，
  没有为这条注释重新部署；若将来要按源码 sha 做字节级比对，需重新部署一次。
- 逐行插入期间出现过中间态读数（`零件数 (5)` / `(17)`，`Part 2…17` 带 `edited` 类名），
  这是重算中间态而非真实几何：第二次读与 reload 后都回到 `零件数 (1)`，最终 STEP 亦为单实体。
- 没有对其它并发会话使用的共享桥做任何代码修改；本次未 push。
