# Gridfinity 底板：板体圆角矩形与 45° 型腔侧壁修正（2026-09-20）

本文记录一次**特征树全绿但模型仍然是错的**的修正与验收证据。两处缺陷都不报错、
`watertight: true`、尺寸 `[84, 84, 10]` 正好，只能从导出几何里量出来。

- 目标文档：document `1ef2be8f3d45e6f996af24ab` / workspace `bac7c0bf31912a956c44d15a`
- Part Studio `f0360bb015d7612284423f55`，Feature Studio `c57b7cc5f7291694afffd17b`
- 特征树（未变，仍 3 行自定义特征）：`GB GF Base Plate Body 1`、`GS GF Socket Pockets 1`、
  `GM GF Magnet Holes 1`，全部 `hasError: false`，`零件数 (1) Gridfinity baseplate 2x2`
- 源文件：`dev/fixtures-capture/gridfinity-baseplate.fs`
- 全程 0 次 Onshape REST 额度（浏览器路径 + 离线几何包）

## 1. 缺陷一：板体不是圆角矩形

`gfBasePlate` 旧写法用一个 `fCuboid`（半宽 = 板半宽 - 外圆角）加四个角圆柱，得到的不是
84 x 84 圆角矩形，而是 **76 x 76 方块 + 四个 r=4 圆耳**：只有靠近四角处材料才到 ±42。

- 底面面积实测 **5926.749 mm²**（几何包 `bedContactAreaMm2`）；
- 84 x 84 圆角矩形（R4）解析面积 = 7056 - (4 - pi) * 16 = **7042.27 mm²**；
- 差值 1115.5 mm² ≈ 四条边条 4 x (76 x 4) = 1216 mm² 减去圆角重叠，方向与量级都对得上。

屏幕上因此能看到"四角探出的凸台"，用户截图（`屏幕截图 2026-09-20 185046.png`）里
表现为角上鼓出的蘑菇状台阶。

修正：两条十字交叉 `fCuboid`（全长 x 芯宽 + 芯长 x 全长）加四个角圆柱。修正后底面面积
**7042.2495 mm²**，与解析值差 0.02 mm²（网格化量级）。

## 2. 缺陷二：型腔 45° 只在角上，平边是直墙

参考实现（`kennetek/gridfinity-rebuilt-openscad`）把平移后的 profile 沿**直角 34 x 34
方框**扫掠，z 处截面是方框按偏移 o(z) 的膨胀：半宽 `17 + o(z)`、圆角半径 `o(z)`。
旧写法只有角柱在长（半径还多算了 1.15），平边在全 z 上都是 34 mm 间距。

导出 STL 的切片证据（`gridfinity-2x2-final-3`，第一次修正尝试、拔模方向反了）：

| z | 平边半宽 实测 | 规格 | 角半径 实测 | 规格 |
|---|---|---|---|---|
| 5.70 | 17.80 | 18.50 | 1.50 | 1.50 |
| 8.50 | 18.20 | 19.50 | 2.50 | 2.50 |
| 9.95 | 17.00 | 20.95 | 3.95 | 3.95 |

角半径精确、平边少 0.35 / 1.30 / 3.95 mm——正好等于"面向内倒"的位移，说明
`opDraft` 的面法线朝 **pull 向量**旋转；要随 z 张开必须 `pullVec = vector(0, 0, -1)`
（中性面取该段底面）。角锥是独立 body，所以切刀整体 `evBox3d` 依旧"正确"，
自检必须逐条对斜条断言。

## 3. 最终验收（`gridfinity-2x2-final-4`）

- 源文件 sha256 `8203a0e03f0042e143bc06d30d6d14db6c32b1bde38ea7696e2fb228cfcd886a`，
  与云端提交回报的 `sourceSha256` 一致（`browser_run_project(gridfinity-refresh-fs)`，
  `apply: false`，不新建文档、不新增特征行）；
- `browser_get_fs_compile_status`：`compiled: true`、`documentClean: true`、
  `elementErrorCount: 0`、`staleErrorCount: 0`；Part Studio 容器
  `Result: Regeneration complete`；
- STEP 导出（浏览器路径，`apiRequests: 0`）sha256
  `ff540a9e696d45292581cc8820b7e58a686f75ce674ce06e56b3b0ff1badc7b4`；
- 几何包：`watertight: true`、`dimensionsMm [84, 84, 10]`、
  `bedContactAreaMm2 7042.249535894`、`volumeMm3 39548.42967909`、
  `triangleCount 29300`、`centerOfMassMm [-1e-09, 0.0, 3.09647225]`、
  `overhangAreaMm2 7042.249535894`。

切片探针（`temp/gridfinity_slice_check.py`，0 网络）全部命中，公差 0.02 mm：

```
 z      o(z)  E=17+o   side_x   dev     r=o   corner_x  dev
 5.20   1.15    18.15    18.15  +0.00   1.15     1.15  -0.00
 5.70   1.50    18.50    18.50  -0.00   1.50     1.50  -0.00
 6.50   1.85    18.85    18.85  -0.00   1.85     1.85  -0.00
 7.50   1.85    18.85    18.85  -0.00   1.85     1.85  -0.00
 8.50   2.50    19.50    19.50  -0.00   2.50     2.50  -0.00
 9.50   3.50    20.50    20.50  -0.00   3.50     3.50  -0.00
 9.95   3.95    20.95    20.95  -0.00   3.95     3.95  -0.00

result: ALL CHECKS PASS  (29300 triangles)
```

磁铁孔（每格 4 个，格心 ± (pitch/2 - 8) = ±13，从 z=5 向下挖 2.4，顶部倒角 0.8）：

| z | 孔心射线最近交点 | 判读 | 期望 |
|---|---|---|---|
| 4.90 | +3.95 mm | 孔内（倒角段 3.25 + 0.8 * 0.7） | 孔 |
| 3.00 | +3.25 mm | 孔内（半径 6.5/2） | 孔 |
| 2.55 | +8.00 mm（到板外缘） | 实心（孔底 2.6 以下） | 实心 |
| 1.00 | +8.00 mm | 实心（基座块） | 实心 |

体积演变可作旁证：磁铁孔摆错修正后 36628.55 → 36011.47 mm³；本次平边张开后
41933.31 → 39548.43 mm³（拔模方向反时平边收窄、少挖了料，所以中间那次体积偏大）。

## 4. 复现命令

```bash
python3 onshape_docs/scripts/fs_local_check.py dev/fixtures-capture/gridfinity-baseplate.fs
python3 temp/deploy_refresh/deploy.py apply --deployment-id "$(date -u +%Y%m%dT%H%M%SZ)-slug"
# 清除 onshape_browser_mode/user_data/project-runs/gridfinity-refresh-fs.checkpoint.json 后：
#   browser_run_project(project="gridfinity-refresh-fs", confirm_mutation=true)
#   browser_export_step(export_id="gridfinity-2x2-final-4", ...) -> browser_build_geometry_package
python3 temp/gridfinity_slice_check.py <geometry_packages>/<id>/model.stl
python3 temp/stl_render.py <geometry_packages>/<id>/model.stl out.png 900 -42 34 1.0
```

渲染出图（本地软件光栅器，0 依赖、0 额度）示例：
`temp/screenshots/{before-iso,after-iso,after-top,after-corner}.png`。
