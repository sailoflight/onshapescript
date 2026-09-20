# 薄特征链重建 Gridfinity 底板：与域基线逐位一致的 B-rep 验收（2026-09-21）

本文记录一次**用薄特征（thin custom feature）把建模步骤搬进特征树**的验收证据：14 行
`sketch`/`extrude` 自定义特征搭出的 2x2 底板，与三行域特征基线导出的是**同一个实体**。

- 目标文档：document `1ef2be8f3d45e6f996af24ab` / workspace `bac7c0bf31912a956c44d15a`
- 薄特征件：Part Studio `GF Thin Plate`（`960a50add3bfef717721ca9b`），
  Feature Studio `Thin Native Features`（`e8291d6887c1ffb321f4f868`）
- 域基线件：Part Studio 1（`f0360bb015d7612284423f55`），
  `GB GF Base Plate Body 1` / `GS GF Socket Pockets 1` / `GM GF Magnet Holes 1`
- 全程 0 次 Onshape REST 额度（浏览器路径导出 STEP + 本地 B-rep 量测）

## 1. 为什么要 B-rep，而不是网格

同一个错误模型（板体四角是尖角、型腔侧壁没有 45° 拔模）在网格层面**完全正常**：
几何包报 `watertight: true`、`dimensionsMm [84, 84, 10]`、体积也落在合理区间。
网格是三角面，尖角和 R4 圆角都能各向同性三角化，所以"水密 + 尺寸对"不构成几何正确性证据。

B-rep 面清单一句话就能判定：R4 圆角会以 `cylinder r=4.0` 出现，45° 拔模会以
`cone semi-angle=45.0` 出现，缺一即错。本次验收因此直接读 STEP 的曲面拓扑。

校验器是仓库脚本 `onshape_docs/scripts/verify_step_brep.py`（需要一个 OpenCascade
Python 绑定；本仓库不安装依赖，只检测相邻的 CadQuery/OCP 环境，见
`docs/roadmap/BROWSER_MODELING_GAPS.md` §2）：

```bash
/home/lijq/code/CadQ/.venv/bin/python onshape_docs/scripts/verify_step_brep.py <model.step>
```

它用 CadQuery 2.8.0 自带的 OpenCascade：`BRepGProp` 量体积/面积，`BRepAdaptor_Surface`
逐面分类 `plane / cylinder / cone / torus`，再按 (类型, 半径或半角) 归并计数与面积，
并报告每类面自己的 z 区间。输出 JSON：本次两份原始报告是运行产物（写在 gitignore 的
`temp/browser-model-verify/reports/`），可提交的汇总证据是
`onshape_docs/verification/thin-feature-rebuild-brep-2026-09-21.json`。

## 2. 两条独立路径的指纹完全一致

| 指标 | 薄特征件 (GF Thin Plate) | 域基线 (Part Studio 1) | 差 |
|---|---|---|---|
| 体积 | **39547.5903 mm³** | **39547.5903 mm³** | 0.000000 |
| 表面积 | **20002.2154 mm²** | **20002.2154 mm²** | 0.000000 |
| 面数 | **194** | **194** | 0 |
| 包围盒 | 84 x 84 x 10（-42..42, -42..42, 0..10） | 同左 | 同左 |
| 水平面 z | 0 / 2.6 / 5.0 / 10.0 | 同左 | 同左 |
| STEP sha256 | `45aa111f997c6400c4fdf4feaf39bf73193541a0e1940b301b7318cb3745b98c` | `ed2363f9e73847ad1d3475871ecf328344fae99e6f9d55d2a1061b5f501591b7` | 文件不同，实体相同 |

两份面清单逐项对应（同一类型、同一数量、同一面积、同一 z 区间）：

| 曲面 | 数量 | 实测面积 (mm²) | z 区间 | 含义 |
|---|---|---|---|---|
| plane | 94 | 18458.3352 | 0..10 | 底/型腔底/磁铁孔底/顶面与各直墙 |
| cylinder r=4.00 | 4 | 251.3276 | 0..10 | 板体四角 R4 圆角 |
| cylinder r=1.85 | 16 | 83.6928 | 6.05..7.85 | 型腔 37.7 锁定段角柱 |
| cylinder r=1.15 | 16 | 10.1152 | 5.00..5.35 | 型腔 36.3 让位段角柱 |
| cylinder r=3.25 | 16 | 522.7616 | 2.60..4.20 | 磁铁孔直段 |
| cone 45° | 16 | 37.3200 | 5.35..6.05 | 角部 45° 张角锥 |
| cone 45° | 16 | 223.5216 | 7.85..10.00 | 角部 45° 外张锥 |
| cone 45° | 16 | 415.1424 | 4.20..5.00 | 磁铁孔口 45° 倒角锥 |

唯一差异是 OpenCascade 报出的锥面 `RefRadius` 参考端不同（域件报远端、薄件报近端），
同一张面、同一面积、同一 z 区间；这是构造顺序差异，不是几何差异。

## 3. 解析面积交叉验算

每条面族都能由公开规格（pitch 42、外圆角 R4、让位 36.3@0.35、张角到 37.7@6.05、
锁定到 7.85、外张到 42@10、磁铁 ⌀6.5 深 2.4 距边 8 带 0.8 倒角）独立算出来，公差 0.001 mm²：

| 面族 | 解析式 | 解析 | 实测 | 差 |
|---|---|---|---|---|
| 板体 R4 角柱 x4 | `4 · (π/2 · 4) · 10` | 251.3274 | 251.3276 | +0.0002 |
| 型腔 36.3 角柱 x16 | `16 · (π/2 · 1.15) · 0.35` | 10.1159 | 10.1152 | -0.0007 |
| 型腔 37.7 角柱 x16 | `16 · (π/2 · 1.85) · 1.80` | 83.6920 | 83.6928 | +0.0008 |
| 磁铁孔直段 x16 | `16 · (2π · 3.25) · 1.60` | 522.7610 | 522.7616 | +0.0006 |
| 角部 45° 张角锥 x16 | `16 · π(1.85+1.15)·(0.7√2)/4` | 37.3202 | 37.3200 | -0.0002 |
| 角部 45° 外张锥 x16 | `16 · π(4.0+1.85)·(2.15√2)/4` | 223.5214 | 223.5216 | +0.0002 |
| 磁铁孔口 45° 倒角锥 x16 | `16 · π(4.05+3.25)·(0.8√2)` | 415.1430 | 415.1424 | -0.0006 |

两个细节值得记下，它们都是"柱面只有四分之一圆弧"造成的：

- 角柱是圆角矩形的 **90° 弧段**，故 `π/2 · R`；磁铁孔是整圆，故 `2π · r`；
- 锥面同理，角部锥只有四分之一扇区，磁铁孔口锥是整锥。

体积同样与解析模型吻合：`70422.655（圆角矩形 x10） - 29487.699（四个型腔） - 1387.2（16 个磁铁孔含倒角）= 39547.76`，
与 B-rep 的 `39547.5903` 差 0.17 mm³（约 4 ppm，来自解析积分的梯形近似）。

## 4. 这次验收否掉了什么

- 早期一次"全绿但错误"的构建：STL 里底面面积恰好 7056.0000（= 84²，**尖角**），
  竖直面只有 (0,10)/(2.6,5.0)/(5.0,6.05)/(6.05,10.0) 四组且无任何锥面；z=6.05 还冒出
  `414.399 = 4·(37.7² - 36.3²)` 的环形平台——那是"拔模没生效"留下的台阶。
  本次面清单里 z=6.05 不再是水平面，而是 45° 锥与直墙的交线，说明拔模确实进模型了。
- 根因是对话框**最后一个被填写的字段不会提交**（详见
  `onshape_docs/experience/featurescript.md` 的 change 事件/blur 条目），
  修复后重建，`browser_run_project` 每一步都报 `committed` 且 `uncommitted: []`。

## 5. 复现命令

```bash
# 1) 部署薄特征源到 Feature Studio（浏览器路径，0 REST 额度）
#    dev/fixtures-capture/thin-native-features.fs -> Thin Native Features
# 2) 跑 14 步项目（超过约 60 s 中继上限，中断后用 resume 续跑）
#    browser_run_project(project="gridfinity-thin-plate", confirm_mutation=true)
#    browser_run_project(project="gridfinity-thin-plate", resume=true)
# 3) 导出两份 STEP（UI 对话，apiRequests: 0）
#    browser_export_step(export_id="gridfinity-thin-plate-v2-20260921", source_tab="GF Thin Plate", ...)
#    browser_export_step(export_id="gridfinity-domain-baseline-20260921", source_tab="Part Studio 1", ...)
# 4) B-rep 量测（0 网络）
/home/lijq/code/CadQ/.venv/bin/python onshape_docs/scripts/verify_step_brep.py \
  /mnt/c/MCP/onshapescript/onshape_browser_mode/outputs/step_exports/gridfinity-thin-plate-v2-20260921/model.step
# 5) 夹具算式的离线守卫（0 网络）
PYTHONPATH=temp/browser-common-site python3 -m unittest dev.tests.test_thin_plate_fixture
```

验收产物：

```
onshape_docs/verification/thin-feature-rebuild-brep-2026-09-21.json   # 两份指纹 + 面清单 + 解析式交叉验算
dev/tests/test_thin_plate_fixture.py                                  # 上述算式的离线守卫（12 项）
temp/browser-model-verify/reports/*.json                              # 运行产物，gitignore，可由脚本重生成
```
