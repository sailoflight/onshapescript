# onshapescript 的 EWF 项目实例（写方向）

spec_version: `0.6.0` —— **本行只是投影，事实源是 `instance.yaml` 的 `spec_version`。**

这是 EWF「写方向」的第一份由**机器生成**的项目实例：`instance.yaml` 不是手抄的，而是由
[`dev/tools/build_ewf_instance.py`](../dev/tools/build_ewf_instance.py) 从真实发布数据生成，并且在写出之前先复算一遍源数据。
本文件说明素材是什么、哪些是事实、哪些地方被迫绕行、以及每条结论的可复算命令。

---

## 1. 素材与范围

`instance.yaml` 覆盖的是 **consumer Release 1.3.0** 那一条真实发布链（revision `6ceacfb`）：

```
版本化源码树（annotated tag v1.3.0 → 6ceacfb）
  → dev/tools/consumer_release_spec.py: WHITELIST / DENYLIST / plan() / validate()
  → dev/tools/build_release.py: 可复现 zip + release-manifest.json + SHA256SUMS + 外层 .sha256
  → GitHub Release v1.3.0（资产恰好是归档与 .sha256 边车）
  → 下载回流复核（下载回来再算摘要，不信任上传结果）
  → 原生 Windows 宿主就地刷新（只替换版本化代码，保留状态按黑名单让路）
```

三个源文件（生成器只读它们）：

| 源 | 路径 | 提供什么 |
|---|---|---|
| S1 | `/home/lijq/code/onshapescript-releases/onshapescript-mcp-1.3.0-6ceacfb.zip` + `.sha256` + 归档内 `release-manifest.json` / `SHA256SUMS` / `RELEASE-NOTES.md` | 产物身份、逐文件摘要、条目数、保留清单 |
| S2 | `dev/tools/consumer_release_spec.py` | 白名单 / 黑名单 / 待决路径的**唯一真相源** |
| S3 | `onshape_docs/verification/resident-login-survival-2026-09-26.json` | 本仓自己的发布验证记录（下载回流、宿主刷新、三次重发的原始记述） |

## 2. 生成器怎么用

```console
$ cd /home/lijq/code/onshapescript
$ python3 dev/tools/build_ewf_instance.py --write   # 生成 ewf/instance.yaml
$ python3 dev/tools/build_ewf_instance.py --check   # 重新渲染并与已提交的文件逐字节比较
$ python3 dev/tools/build_ewf_instance.py --facts   # 只打印本次复算出的事实（JSON）
```

`--check` 是这条链上唯一能把「实例与源数据脱节」变成一次可执行失败的东西：改坏源数据或改坏
模板，它立刻变红（退出码 1）。

生成前的硬校验（任何一条不满足就拒绝写出，退出码 1）：归档 sha256 == 边车 == 验证记录里的摘要；
清单 399 条逐文件摘要在解包树上全部复算一致；annotated tag v1.3.0 指向的 commit ==
`manifest.sourceRevision` == `6ceacfb`；归档 402 个条目时间戳全为 1980-01-01；归档内
`RELEASE-NOTES.md` 与发行目录副本逐字节相同。

## 3. 哪些是 Fact（本机可复算）

- 归档摘要、字节数、条目数、清单条数、逐文件摘要 —— 见 §9 命令 5 / 6。
- annotated tag `v1.3.0` → `6ceacfb`，提交时间 —— `git cat-file -t v1.3.0`、`git rev-list`。
- 白名单 20 条 / 黑名单 23 条 / 待决 0 条 —— 生成器用 `ast` 直接读 `consumer_release_spec.py`
  （不 import，避免写 `.pyc`），`--facts` 会打印。
- 已发布资产的名称与字节数 —— §9 命令 5（需要网络）。
- **发行说明的保留清单与清单文件的保留集合不一致** —— §9 命令 4；这是本实例的生成器复算时
  发现的真实项目缺陷，详见 §7。

## 4. 哪些是记录事实（本机不可复算，如实标注）

下面这些只在 `onshape_docs/verification/resident-login-survival-2026-09-26.json` 里，本机（WSL 侧）
无法复算：Windows 宿主在 WSL 侧不可达（同仓的 `onshape_docs/verification/pending-live-verification-2026-10-01.json`
记的就是宿主不可达）。它们在 `instance.yaml` 里作为 `E-OSH-SELFCHECK` / `E-OSH-HOST` 的证据出现，
读者**不应**把它们当成刚被本机验证过：

- 解包树 stdio 自检（server 身份、`tools/list`、registryCount）与「零 Onshape 请求」。
- 宿主就地刷新的 dry-run 计划集合、产物逐文件等值、保留状态 mtime、桥代次递进、几何后端选择不变。
- 三次重新发布（`c10a235` / `681a4cd` / `e667bcc` / `31d2b9c` 一路到 `6ceacfb`）的经过。

## 5. `instance.yaml` 的几条设计决定

- **三张图分开**（`EWF-GEN-005`）：`maturity[]` / `workflows[]` / `execution`。
- **发布门只管发布前**：`GATE-OSH-PUBLISH` 的四条判据都在 publish 之前可满足（本地摘要、
  配置标识、干净 revision、未签名状态）；下载回流是发布**之后**的独立复核节点，不是这道门的
  条件。这是刻意的修正，不是照抄。
- **回边由真实事件支撑**：`WF-OSH-PUBLISH` 的 4 条 `reentry / when: fail` 对应两次产物级缺陷与
  宿主验收失败；本实例不新建 Change Record（`TLR-OSH-03`，`EWF-ENT-004`）。
- **`runs[]` 与节点内联的 `run` 由生成器从同一份事实渲染**，因此 `EWF-EXE-007` / `EWF-EXE-009`
  的一致性在这里是构造保证，而不是靠人核对。
- `open_questions` 只列已登记的全局 OQ，且与 README / FEEDBACK 里点名的 OQ 集合一致
  （`OQ-011` / `OQ-015` / `OQ-016` / `OQ-017` / `OQ-020` / `OQ-022` / `OQ-026`）。

## 6. 被迫绕行的地方（一条一句）

1. **产物身份被压成一个字符串**：真实身份是三元组（server 版本 1.3.0 + revision `6ceacfb` +
   归档 sha256），还可能带逐文件摘要清单，而 `artifact.identity` 只有一个 `string`。
2. **取代关系不对称**：`baseline` 有 `supersedes`，`release` 没有；「新版取代旧版」在两个 Entity
   上可表达性不一致，只能借 baseline 说。
3. **返工次数写不出来**：1.3.0 之前真实发生过三次重新发布，EWF 只有 `when: fail` 的条件边，
   既不能记「这条边走过几次」，也不能给没有节点的 run 一个语义地址。
4. **发布渠道只能写 `custom`**：`external_ref.system` 的枚举里没有发布 / 分发渠道，
   GitHub Release 只能 `custom` + `system_name: github-releases`，而 `system_name` 不是必填。
5. **许可与再分发无处安放**：产物再分发上游语料与内置 wheel，但 `artifact` payload 只有
   `realization_kind` / `satisfies` / `identity`，许可义务只能写进散文。
6. **产物留存政策无处安放**（「可得性」本身不是缺口，见回灌队列 `onshapescript-FB-06` 的处置）：验证记录里点名 6 个构建 revision，本地只有 2 个 zip；
   「哪个版本还留着、留多久、谁能删」在 EWF 里既不是 Release 字段、也不是 Entity。
7. **工具标识与真实命令对不上**：真实命令是 `gh release create` / `sha256sum -c`，而 `id` 的
   字符集不允许空格，只能改写成 `gh-release` / `sha256sum`；机器可读侧没有地方放真实命令。
8. **写方向的机器执行者只能住在 `dev/tools/`**：`docs/project-onboarding.md` §1 约定
   `<project>/ewf/` 只放 `instance.yaml` + `README.md`（+ `FEEDBACK.md`），不放代码；邀请又要求
   「写个小脚本生成它」。落点是项目自己的工具目录 `dev/tools/build_ewf_instance.py`，
   本目录保持三份交付物。这条不是缺口（§1 已经说了），只是位置需要自己判断，
   `FEEDBACK.md` 的 `onshapescript-FB-01` 记为 `非缺口`。
9. **生成物没有任何来源记录**：`instance` 层没有 provenance / source 字段（只有 Entity 有），
   于是「这份实例由哪些源数据、什么摘要生成、是否过期」无法机器可读。
10. **项目自有未决项只能落 `note.text`**：`instance.open_questions` 只收 `OQ-\d{3}`，
    项目自己的待定项没有机器可读位置。
11. **治理驱动的「为什么」无处写**：`governance_drivers` 只有枚举值，没有地方说明「为什么这个
    驱动对本实例成立」。
12. **`--path` 必然失败**：项目实例目录天生叫 `ewf`，`--path` 强制「目录名 == `instance.id`」，
    所以验收必须用 `--project`（`OQ-015`，已登记，此处只是复现）。

**看起来像缺口、其实不是（如实记一条）**：`consumer_release_spec.py --check` 写出的清单是
`artifactStatus: spec-only` / `artifactFormat: null`——产物还没被构建。它看着像「无法表达未构建的
产物」，其实 `existence.engineering_object: absent` + 「计划用的摘要清单」可以是两个不同的
Artifact / Record。现有条款足够，不构成缺口，因此只写进 README，不进回灌队列。

## 7. 本实例发现的真实项目缺陷（不属于 EWF，回给项目侧）

归档内 `RELEASE-NOTES.md` 的「Preserved state」小节列了 **18** 条，而同一归档内
`release-manifest.json` 的 `excludedPaths` 是完整 **23** 项；差的 5 条恰好是构建机上不存在的
状态路径：

```
onshape_browser_mode/config/browser.local.toml
onshape_browser_mode/config/geometry-backend.json
onshape_rest_api_mode/config/geometry-backend.json
onshape_browser_mode/outputs/
mcp_main/win/mcp/config/tool_views.local.toml
```

其中 `geometry-backend.json` 两项正是上一轮产物缺陷的主角。也就是说：上一轮修复把**清单**改成
发布完整黑名单，却把**发行说明**留在「构建 checkout 观测到的子集」。同一份归档里，「升级必须
保留什么」有两个互相不一致的人读 / 机读答案。发现方式见 §9 命令 4；`instance.yaml` 里记为
`DEF-OSH-NOTES`。

## 8. `x-*` 扩展键：**不需要**（以及为什么）

本实例**没有使用任何 `x-*` 键**。我们确实有 EWF 无处安放的机器可读事实（产物格式、签名状态、
完整黑名单、逐文件摘要），但：

- 其中大部分另有一个更合适的落点：格式与签名状态在产物自己的 `release-manifest.json` 里
  （`artifactFormat` / `signed`），完整黑名单与逐文件摘要在同一份清单里，revision 在
  `baseline.configuration` 的 `software-commit` 项里。
- 私有键对**不共享我们约定**的消费者不可读；造一个只有我们认识的键，只会让实例看起来更完整，
  而不会让缺口被发现。把缺口写进 [`FEEDBACK.md`](FEEDBACK.md) 更有用。

这是本清单要的一个结论，不是省事：**`EWF-SCH-004` 的逃逸口在这条发布链上没有被需要**。

## 9. 权威来源（命令与原始输出）

下面每一段都是现场跑出来的原始输出（§4 标注的「记录事实」除外）。

### 命令 1 —— 两条验收命令（均要求 PASS、退出码 0）

```console
$ cd /home/lijq/code/ewf && ./.venv/bin/python tests/validate_examples.py --project /home/lijq/code/onshapescript/ewf
EWF Core V0 example validation —— spec_version 0.6.0
schema: 8 个文件, /home/lijq/code/ewf/schema

  OK  [project] ewf                   nodes=9   entities=22  tailoring=6   （不做断言校验）

说明（不影响判定）：
  - ewf：目录名与 instance.id = 'onshapescript-release-1.3.0' 不同——作为项目实例目录时，目录名不是实例身份，不算失败（OQ-015）

PASS —— 1 个 project 通过 schema + 引用完整性校验
exit=0

$ cd /home/lijq/code/ewf-tools && ./.venv/bin/python -m ewf_tools.check --project /home/lijq/code/onshapescript/ewf
EWF read-only check —— spec_version 0.6.0
repo: /home/lijq/code/ewf；schema: 8 个文件

  OK  [project] ewf                            nodes=9   entities=22  tailoring=6  （项目实例没有 benchmark.yaml，不做断言校验）

说明（不影响判定）：
  - ewf：目录名与 instance.id='onshapescript-release-1.3.0' 不同——作为项目实例目录时，目录名不是实例身份，不算失败

断言：**未校验**（1 个目标没有 benchmark case）：must_present / must_absent 整层未求值 —— 「PASS」只覆盖 schema + 引用完整性，不等于「断言通过」
      未求值：ewf

PASS —— 1 个 project 通过 schema + 引用完整性
exit=0
```

> **时点说明（2026-10-02）**：上面两段是本次交付时的输出，两条命令**都** PASS、退出码都是 0。
> 同日晚些时候 EWF 仓进入 `0.6.0` → `0.6.1` 的**未提交升级窗口**（`schema/*.json` 里 4 个文件已是
> `0.6.1`、4 个仍是 `0.6.0`），那一窗口里：官方校验器照跑并报 `spec_version 0.6.1`、本项目实例仍
> PASS；`ewf_tools check` 则 `RuntimeError: 无法从 EWF schema 读出唯一 spec_version` 拒绝运行。
> 这是 EWF 仓的过程态，不是本项目实例的问题，已按原始输出记进 `FEEDBACK.md` 的
> `onshapescript-FB-13`。**该窗口随后关闭**：8 个 schema 文件全部为 `0.6.1`，两条命令重新都位于
> PASS、退出码 0（本项目实例在同一份 `0.6.1` schema 下仍然通过）。关闭后消费者工具多出一条说明：
> `ewf：instance 的 spec_version=0.6.0，本工具与规范已到 0.6.1——这是版本漂移，只记录、不影响本次判定`。
> 本实例保留 `0.6.0`，理由见第 10 节待定项第 4 条。

### 命令 2 —— 反向对照：改坏一处（删掉必需的 `maturity`），两个探针都必须报 FAIL、退出码 1

```console
$ cp -r /home/lijq/code/onshapescript/ewf /tmp/osh-ewf-negative   # 然后删掉必需的 instance.maturity 键

$ cd /home/lijq/code/ewf && ./.venv/bin/python tests/validate_examples.py --project /tmp/osh-ewf-negative
EWF Core V0 example validation —— spec_version 0.6.0
schema: 8 个文件, /home/lijq/code/ewf/schema

FAIL —— 2 条问题：
  - osh-ewf-negative [schema] instance.yaml 未通过 schema 校验（1 条）
  - osh-ewf-negative [schema] 明细：
  - instance: 'maturity' is a required property
exit=1

$ cd /home/lijq/code/ewf-tools && ./.venv/bin/python -m ewf_tools.check --project /tmp/osh-ewf-negative
EWF read-only check —— spec_version 0.6.0
repo: /home/lijq/code/ewf；schema: 8 个文件

断言：**未校验**（1 个目标没有 benchmark case）：must_present / must_absent 整层未求值 —— 「PASS」只覆盖 schema + 引用完整性，不等于「断言通过」
      未求值：osh-ewf-negative

FAIL —— 2 条问题：
  - osh-ewf-negative [schema] instance.yaml 未通过 schema 校验（1 条）
  - osh-ewf-negative [schema] 明细：
  - instance: 'maturity' is a required property
exit=1
```

### 命令 3 —— 第二处反向对照：只改一个引用（schema 完全合法），`refs` 层必须报出

```console
$ # 复制实例后把 provenance.produced_by: N3 改成 N3-GHOST
$ cd /home/lijq/code/ewf-tools && ./.venv/bin/python -m ewf_tools.check --project /tmp/osh-ewf-negative-refs
EWF read-only check —— spec_version 0.6.0
repo: /home/lijq/code/ewf；schema: 8 个文件

说明（不影响判定）：
  - osh-ewf-negative-refs：目录名与 instance.id='onshapescript-release-1.3.0' 不同——作为项目实例目录时，目录名不是实例身份，不算失败

断言：**未校验**（1 个目标没有 benchmark case）：must_present / must_absent 整层未求值 —— 「PASS」只覆盖 schema + 引用完整性，不等于「断言通过」
      未求值：osh-ewf-negative-refs

FAIL —— 2 条问题：
  - osh-ewf-negative-refs [refs] instance/entities/6/provenance/produced_by -> 未声明的引用 `N3-GHOST`
  - osh-ewf-negative-refs [refs] instance/entities/7/provenance/produced_by -> 未声明的引用 `N3-GHOST`
exit=1
```

### 命令 4 —— 生成、新鲜度自检与保留集合比对

```console
$ cd /home/lijq/code/onshapescript && python3 dev/tools/build_ewf_instance.py --write
wrote /home/lijq/code/onshapescript/ewf/instance.yaml (1021 行；源归档 onshapescript-mcp-1.3.0-6ceacfb.zip sha256 d112de9c63dd…)
# 行数会随后续提交变化：以这一行的当次输出为准，不要把它当读数引用
exit=0

$ python3 dev/tools/build_ewf_instance.py --check
OK: ewf/instance.yaml 与生成结果一致
exit=0

$ python3 dev/tools/build_ewf_instance.py --facts
（JSON；关键项：REVISION=6ceacfb、ARCHIVE_SHA256=d112de9c63dd…、MANIFEST_FILE_COUNT=399、
 ZIP_ENTRY_COUNT=402、WHITELIST_COUNT=20、DENYLIST_COUNT=23、NOTES_PRESERVE_COUNT=18、
 NOTES_MISSING_COUNT=5）
exit=0
```

### 命令 5 —— 已发布对象的现场复核（下载回流；需要网络）

```console
$ cd /home/lijq/code/onshapescript && gh release view v1.3.0 --repo sailoflight/onshapescript \
    --json tagName,isDraft,isPrerelease,publishedAt,url,assets
{
  "tagName": "v1.3.0",
  "isDraft": false,
  "isPrerelease": false,
  "publishedAt": "2026-09-25T16:51:37Z",
  "url": "https://github.com/sailoflight/onshapescript/releases/tag/v1.3.0",
  "assets": [
    {
      "name": "onshapescript-mcp-1.3.0-6ceacfb.zip",
      "size": 2790631,
      "state": "uploaded"
    },
    {
      "name": "onshapescript-mcp-1.3.0-6ceacfb.zip.sha256",
      "size": 102,
      "state": "uploaded"
    }
  ]
}
exit=0

$ rm -rf /tmp/ghdl && mkdir /tmp/ghdl && gh release download v1.3.0 --repo sailoflight/onshapescript -D /tmp/ghdl \
    && (cd /tmp/ghdl && sha256sum -c onshapescript-mcp-1.3.0-6ceacfb.zip.sha256)
download exit=0
onshapescript-mcp-1.3.0-6ceacfb.zip: 成功
verify exit=0

$ sha256sum /home/lijq/code/onshapescript-releases/onshapescript-mcp-1.3.0-6ceacfb.zip /tmp/ghdl/onshapescript-mcp-1.3.0-6ceacfb.zip
d112de9c63ddd5c6332476e52746541b36607ee667133aaeef5320351178ab4b  /home/lijq/code/onshapescript-releases/onshapescript-mcp-1.3.0-6ceacfb.zip
d112de9c63ddd5c6332476e52746541b36607ee667133aaeef5320351178ab4b  /tmp/ghdl/onshapescript-mcp-1.3.0-6ceacfb.zip
```

### 命令 6 —— 归档内层摘要（399/399）

```console
$ rm -rf /tmp/oshzip && mkdir /tmp/oshzip && cd /tmp/oshzip \
    && unzip -q /home/lijq/code/onshapescript-releases/onshapescript-mcp-1.3.0-6ceacfb.zip \
    && sha256sum -c SHA256SUMS | tail -2
onshape_rest_api_mode/operations.py: 成功
onshape_rest_api_mode/step_export.py: 成功
exit=0

$ sha256sum -c SHA256SUMS | grep -c ": 成功"
399
```

### 命令 7 —— 写路径证据：在副本上跑 `--write`（2026-10-03）

`--check` 只证明"生成器与已提交产物一致"，不证明"生成器能写出产物"。下面这次在
**独立 worktree 副本**上真跑 `--write`（主检出未被写、`git status` 事后仍为空）：

```console
$ cd /home/lijq/code/onshapescript && git worktree add --detach /tmp/ewf-write-<ts> HEAD
$ cd /tmp/ewf-write-<ts> && python3 dev/tools/build_ewf_instance.py --write
wrote /tmp/ewf-write-<ts>/ewf/instance.yaml (1021 行；源归档 onshapescript-mcp-1.3.0-6ceacfb.zip sha256 d112de9c63dd…)
exit=0
$ git diff --stat
（空，0 行）
$ git status --short
（空，0 行）
$ sha256sum /tmp/ewf-write-<ts>/ewf/instance.yaml /home/lijq/code/onshapescript/ewf/instance.yaml
f5148a5da253c9f5c5cfc0b130e7db3159520e88a5528535ad7e41a92a7e67e6  /tmp/ewf-write-<ts>/ewf/instance.yaml
f5148a5da253c9f5c5cfc0b130e7db3159520e88a5528535ad7e41a92a7e67e6  /home/lijq/code/onshapescript/ewf/instance.yaml
```

即：**退出码 0、diff 为空、产物与提交版本逐字节相同**（副本 HEAD `11c36c2` 与主检出同期同提交）。
副本里两条验收命令同样 PASS、退出码 0（官方不提漂移，消费者打印那条漂移说明）。

## 10. 项目本地的待定项（无编号）

这些是**本项目自己的决定**，不是规范缺口，因此不给 `OQ-` 编号（`OQ-` 是 EWF 的全局命名空间，
项目侧 MUST NOT 自造；项目自有待定项目前也没有机器可读位置，见回灌队列的 `onshapescript-FB-02`）。
同一份清单用纯序号写在 `instance.yaml` 的 `instance.note.text` 里。

1. **上游语料与内置 wheel 的许可与再分发边界**。产物按白名单携带本地 FeatureScript 语料
   （`onshape_docs/reference/raw/` 等）、Onshape 原生文档副本与内置 wheel。授权决定不在本实例里
   （本实例只登记这条再分发边界，见 `SUBJ-OSH-UPSTREAM`），但"要不要随包发、随包发时要不要带
   notice"仍是一个没落纸的决定。
2. **产物的留存、处置与可得性**。验证记录点名的构建 revision 与本地保留的归档不是同一批：
   `onshape_docs/verification/resident-login-survival-2026-09-26.json` 给出 6 个 revision，
   而 `ls /home/lijq/code/onshapescript-releases/*.zip` 当前是 2 个（其中 `1f9f7c2` 又不在记录里）。
   "哪个版本还留着、留多久、谁能删"未决。
3. **发行说明的保留集合与清单黑名单不一致**。归档内 `RELEASE-NOTES.md` 的"Preserved state"小节
   与同一归档内 `release-manifest.json` 的 `excludedPaths` 不是同一集合（差集非空，差的恰是
   构建机上不存在的状态路径）。修法是让发行说明从清单派生，还是两边各自维护，未决。
   本实例把它记为缺陷 `DEF-OSH-NOTES`。
4. **是否跟随 spec `0.6.1`**。本实例在 `0.6.1` 的 schema 下通过校验，但它的每条读数与每个建模
   决定都是在 `0.6.0` 上做的；`0.6.1` 的条款变化没有被本项目逐条核对过。声明
   `spec_version: 0.6.1` 等于声称核对过，所以在核对之前保留 `0.6.0`——消费者工具把它记成
   "版本漂移"，只记录、不影响判定。**2026-10-03 起本条提升为正式决策记录，含重新考虑条件，见第 14 节。**

## 11. 回灌清单（叙述版）

下面每条的完整证据与建议去向见 [`FEEDBACK.md`](FEEDBACK.md)（**id 集合与队列表逐条一致**，
由 `dev/tests/test_ewf_instance.py` 逐字比对）：

- `onshapescript-FB-01` —— 两处文档都没说清写方向生成器住在哪，落在 `dev/tools/`（文档）。
- `onshapescript-FB-02` —— 项目自有未决项没有机器可读位置（`open_questions` 只收 `OQ-\d{3}`）。
- `onshapescript-FB-03` —— 生成出来的实例无法记录「由哪些源数据、什么摘要生成、是否过期」。
- `onshapescript-FB-04` —— `artifact.identity` 单字符串装不下真实的三元组身份。
- `onshapescript-FB-05` —— `release` payload 没有 `supersedes`，而 `baseline` 有。
- `onshapescript-FB-06` —— 没有产物留存**政策**的表达位置（「可得性那半」被 EWF 侧复现推翻）。
- `onshapescript-FB-07` —— `external_ref.system` 枚举没有发布 / 分发渠道。
- `onshapescript-FB-08` —— 没有许可 / 第三方再分发的表达位置。
- `onshapescript-FB-09` —— 官方校验器不认 `--help`，退出码 1。
- `onshapescript-FB-10` —— `spec-only` 清单看着像缺口，现有条款能解释（非缺口）。
- `onshapescript-FB-11` —— `id` 字符集不允许空格，真实命令改写后落在 `note.text`（非缺口）。
- `onshapescript-FB-12` —— `governance_drivers` 只有枚举值，没有写「为什么」的位置。
- `onshapescript-FB-13` —— schema 目录里同时存在两个 spec 版本时，官方校验器照跑、消费者工具拒绝运行。
- `onshapescript-FB-14` —— `[files]` 层失败会短路 schema 层，schema 错误一条都不打印。
- `onshapescript-FB-15` —— 实体通用字段与 kind 子对象写错层时，报错指向「字段名不合法」。

## 12. 守卫测试

`dev/tests/test_ewf_instance.py` 在离线状态下检查（对应 `docs/project-onboarding.md` §6 的五条自查）：

- `dev/tools/build_ewf_instance.py --check` 通过，即实例与生成结果逐字节一致；
- 本文第 3 行的 spec 版本与 `instance.yaml` 的 `spec_version` 一致（§6-5）；
- 本文出现的每个 `OQ-\d{3}` 都在 `instance.open_questions` 里（§6-1）；
- 本文第 11 节的 `onshapescript-FB-NN` 集合与 `FEEDBACK.md` 队列表的 id 集合相同（§6-4）；
- `execution_view_note` 里写的节点数与 `execution.nodes` 实际条数相同（§6-2 的机器自查）。

需要外部 EWF 仓的校验器**不在**这套测试的必过项里：它们不在时就跳过并打印原因，
不假装通过。

## 13. 相关材料

- EWF 规范与项目接入协议：`/home/lijq/code/ewf/SPEC.md`、`/home/lijq/code/ewf/docs/project-onboarding.md`。
- EWF 侧用同一批发布数据做过的试验（**不是规范**，与本实例相互独立）：
  `/home/lijq/code/ewf/trials/onshape-release-ingress/`。
- 本仓发布规格：`docs/operations/RELEASE.md`；发布工具：`dev/tools/consumer_release_spec.py`、
  `dev/tools/build_release.py`。

## 14. 决策记录：`spec_version` 不跟随 schema（含重新考虑的条件）

**决策：不跟随。** 生成器第 62 行的常量是版本住的唯一位置
（`SPEC_VERSION = "0.6.0"`）；全仓**没有**任何代码读 schema 的 `x-ewf-spec-version`。要前进必须
有人改常量、重跑 `--write`，并在**同一次提交**里跑完两条验收命令。

> **更正（2026-10-03）**：当天答复 EWF 侧提问时说过"没有为它记过任何策略"——**这句不准确**。
> 理由其实早已记过（第 10 节待定项第 4 条 + 第 9 节的时点说明）；当时真正缺的是**决策记录与
> 重新考虑条件**，也就是本节补上的东西。原话与更正都留在 `FEEDBACK.md` 的交换记录里。

**为什么不跟随（可复算的事实，不是偏好）**

1. 这个字段是**声明**，不是镜像：它说的是"本实例的每条读数与每个建模决定是照哪一版规范做的"，
   而不是"EWF 现在发到哪一版"。自动写成 schema 的当前值，等于**在没核对的情况下声称核对过**。
2. 今天**没有唯一且稳定的机器可读版本源**：2026-10-02 实测到混合版本窗口（8 个 schema 文件里
   4 个 `0.6.1` / 4 个 `0.6.0`），窗口内消费者工具直接以
   `RuntimeError: 无法从 EWF schema 读出唯一 spec_version` 拒绝运行（证据见第 9 节时点说明与
   `FEEDBACK.md` 的 `onshapescript-FB-13`）。把产物接到一个在某段时间里有**两个答案**的源上，
   会把"不唯一"引进本实例。
3. 版本前进的**真实动作是内容再核对**（两条验收命令 + 逐条处置新条款），不是改一个字符串；
   `--write` 只会重渲染同样的读数。
4. 漂移**可见且有界**：官方校验器完全沉默；消费者工具 PASS 并打印"版本漂移，只记录、不影响
   本次判定"。两个实现都不把它当失败——EWF 侧 2026-10-03 也按"**口径是选择、不是缺陷**"记。
5. `--check` 只是**自洽**检查（生成器 ↔ 已提交产物），它**不会**发现与 schema 的漂移。写在这里
   免得以后被当成 bug（EWF 侧 2026-10-03 专门问过这一点）。

**什么时候重新考虑**（满足任一条 → 先再核对，再在同一次提交里 bump 常量）

1. EWF 把"实例 `spec_version` 必须等于 schema 族的 `x-ewf-spec-version`"写成 MUST；
2. 任一实现开始因漂移判**失败**，而不是只记一条说明；
3. 本项目主动做一轮"对着新版规范再核对"（两条验收命令 + 逐条处置新条款发现）；
4. 出现"漂移导致消费者误处理"的实际案例，而不只是记一条说明；
5. schema 侧给出**唯一且稳定**的版本查询入口（单文件真源或显式打印命令），使现读不再有第 2 条
   那种双答案窗口——那之后可以考虑改成现读（仍要有人确认"读数未变"才 bump）。

**今天的状态**：schema 8 个文件全 `0.6.1`、本实例声明 `0.6.0`，两条验收命令 PASS、退出码 0；
本决策**不改变任何产物内容**（写路径证据见第 9 节命令 7）。
