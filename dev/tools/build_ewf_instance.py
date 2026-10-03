#!/usr/bin/env python3
"""从 onshapescript 的真实发布数据生成 EWF 项目实例（写方向，EWF 0.6.0）。

这是一个**写方向的机器执行者**：`instance.yaml` 不是手抄的，而是由三份真实数据
生成，并且在写出之前先复算一遍。

源数据（全部只读）

  S1  /home/lijq/code/onshapescript-releases/onshapescript-mcp-1.3.0-6ceacfb.zip
      以及同名 .sha256 边车，和归档内的 release-manifest.json / SHA256SUMS /
      RELEASE-NOTES.md。
  S2  dev/tools/consumer_release_spec.py 的**发布点那一版**（`git show v1.3.0:…`）；该文件是
      白名单 / 黑名单 / plan() 的唯一真相源，本实例读它被冻结的形态。
  S3  onshape_docs/verification/resident-login-survival-2026-09-26.json
      （本仓自己的发布验证记录）。

生成前的硬校验（任何一条对不上就拒绝写出）

  * 归档 sha256 == .sha256 边车 == 验证记录里记的那一个摘要；
  * 归档内 release-manifest.json 的每一条逐文件摘要，在解包树上复算一致，
    且 SHA256SUMS 行数 == manifest.fileCount；
  * annotated tag v1.3.0 指向的 commit == manifest.sourceRevision；
  * 归档全部条目的时间戳为 1980-01-01（可复现构建的可判别标记）；
  * 归档内的 RELEASE-NOTES.md 与发行目录里的副本逐字节相同。

用法

    python3 dev/tools/build_ewf_instance.py --check    # 重新渲染并与 ewf/instance.yaml 比较
    python3 dev/tools/build_ewf_instance.py --write    # 写出 ewf/instance.yaml
    python3 dev/tools/build_ewf_instance.py            # 打到 stdout

本工具只读源数据、只写 ewf/instance.yaml；不联网、不改工作树。

布局：生成器住在 dev/tools/ 而不是 ewf/，因为 ewf/ 目录按 EWF 的约定只放交付物
（instance.yaml、README.md、FEEDBACK.md），不放代码。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EWF_DIR = ROOT / "ewf"
INSTANCE_PATH = EWF_DIR / "instance.yaml"

RELEASES_DIR = Path("/home/lijq/code/onshapescript-releases")
ARCHIVE_NAME = "onshapescript-mcp-1.3.0-6ceacfb.zip"
ARCHIVE = RELEASES_DIR / ARCHIVE_NAME
SIDECAR = RELEASES_DIR / (ARCHIVE_NAME + ".sha256")
NOTES_COPY = RELEASES_DIR / "RELEASE-NOTES-v1.3.0.md"
SPEC_TOOL = ROOT / "dev/tools/consumer_release_spec.py"
RECORD = ROOT / "onshape_docs/verification/resident-login-survival-2026-09-26.json"

SPEC_VERSION = "0.6.0"
TAG = "v1.3.0"
RELEASE_URL = "https://github.com/sailoflight/onshapescript/releases/tag/v1.3.0"
ZIP_FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class Gap(Exception):
    """源数据不自洽；生成器拒绝继续。"""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise Gap(f"git {' '.join(args)} 失败：{proc.stderr.strip()}")
    return proc.stdout.strip()


def _spec_constants() -> dict:
    """用 ast 读发布工具里的常量，不 import 它（import 会往 checkout 写 .pyc）。

    读的是**发布点那一版**（`git show <TAG>:<path>`），不是工作树里的当前文件：本实例描述的
    是一个已经冻结的发布，S2 的四个常量（白名单 / 黑名单 / 待决 / server 版本）都是那次发布的
    属性。从工作树读会让后续的版本提升或白名单调整悄悄改写一份历史报告——而那个失误只有
    `--check` 会报，报出来也难看出成因。
    """
    text = _git("show", f"{TAG}:dev/tools/consumer_release_spec.py")
    tree = ast.parse(text)
    wanted = {
        "WHITELIST",
        "DENYLIST",
        "PENDING_DECISION",
        "MCP_SERVER_VERSION",
        "GOVERNANCE_RELEASE",
        "MANIFEST_NAME",
        "CHECKSUM_SIDECAR_NAME",
    }
    found: dict = {}
    for node in tree.body:
        name = None
        value = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name, value = node.targets[0].id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name, value = node.target.id, node.value
        if name in wanted and value is not None:
            found[name] = ast.literal_eval(value)
    missing = wanted - found.keys()
    if missing:
        raise Gap(f"发布工具里找不到这些常量：{sorted(missing)}")
    return found


def _notes_preserve_list(notes: str) -> list[str]:
    keep = []
    for line in notes.splitlines():
        if line.startswith("- `") and line.endswith("`"):
            keep.append(line[3:-1])
    return keep


def collect() -> dict:
    """读取并复算三份源数据，返回渲染所需的全部 token。"""
    for path in (ARCHIVE, SIDECAR, NOTES_COPY, SPEC_TOOL, RECORD):
        if not path.is_file():
            raise Gap(f"缺少发布数据：{path}")

    spec = _spec_constants()

    outer = _sha256_file(ARCHIVE)
    sidecar = SIDECAR.read_text(encoding="utf-8").split()[0]
    if sidecar != outer:
        raise Gap(f"归档摘要与边车不一致：归档 {outer}，边车 {sidecar}")

    record_text = RECORD.read_text(encoding="utf-8")
    if outer not in record_text:
        raise Gap(f"验证记录 {RECORD.name} 里没有出现归档摘要 {outer}")

    tag_type = _git("cat-file", "-t", TAG)
    if tag_type != "tag":
        raise Gap(f"{TAG} 不是 annotated tag（git cat-file -t 返回 {tag_type!r}）")
    full_revision = _git("rev-parse", f"{TAG}^{{commit}}")
    revision = full_revision[:7]
    commit_date = _git("log", "-1", "--format=%cI", full_revision)

    with zipfile.ZipFile(ARCHIVE) as archive:
        infos = archive.infolist()
        stamps = {info.date_time for info in infos}
        manifest = json.loads(archive.read(spec["MANIFEST_NAME"]))
        sums = archive.read(spec["CHECKSUM_SIDECAR_NAME"]).decode("utf-8").splitlines()
        notes = archive.read("RELEASE-NOTES.md").decode("utf-8")
        mismatches = 0
        with tempfile.TemporaryDirectory() as tmp:
            archive.extractall(tmp)
            for row in manifest["files"]:
                extracted = Path(tmp) / row["path"]
                if (
                    _sha256_file(extracted) != row["sha256"]
                    or extracted.stat().st_size != row["bytes"]
                ):
                    mismatches += 1

    if stamps != {ZIP_FIXED_TIMESTAMP}:
        raise Gap(f"归档条目的时间戳不是固定值：{sorted(stamps)}")
    if mismatches:
        raise Gap(f"归档内有 {mismatches} 个文件与清单摘要不符")
    if manifest["sourceRevision"] != revision:
        raise Gap(
            f"清单 sourceRevision={manifest['sourceRevision']!r}，"
            f"tag 指向 {revision!r}"
        )
    if manifest["artifactName"] != ARCHIVE_NAME:
        raise Gap(f"清单 artifactName={manifest['artifactName']!r}")
    if manifest["mcpServerVersion"] != spec["MCP_SERVER_VERSION"]:
        raise Gap("清单里的 server 版本与发布工具常量不一致")
    if manifest["fileCount"] != len(manifest["files"]) or len(sums) != len(manifest["files"]):
        raise Gap("清单 fileCount、files[] 与 SHA256SUMS 行数三者不一致")
    if len(infos) != manifest["fileCount"] + 3:
        raise Gap("归档条目数 != fileCount + manifest/SHA256SUMS/RELEASE-NOTES 三个文件")
    if notes != NOTES_COPY.read_text(encoding="utf-8"):
        raise Gap("归档内 RELEASE-NOTES.md 与发行目录里的副本不同")

    exclude = list(manifest["excludedPaths"])
    preserve = _notes_preserve_list(notes)
    missing = [entry for entry in exclude if entry not in preserve]

    return {
        "SPEC_VERSION": SPEC_VERSION,
        "REVISION": revision,
        "REVISION_FULL": full_revision,
        "TAG": TAG,
        "TAG_TYPE": tag_type,
        "COMMIT_DATE": commit_date,
        "ARCHIVE_NAME": ARCHIVE_NAME,
        "ARCHIVE_BYTES": str(ARCHIVE.stat().st_size),
        "ARCHIVE_SHA256": outer,
        "MANIFEST_FILE_COUNT": str(manifest["fileCount"]),
        "MANIFEST_TOTAL_BYTES": str(manifest["totalBytes"]),
        "ZIP_ENTRY_COUNT": str(len(infos)),
        "BUILD_EXTRA_ENTRIES": str(len(infos) - manifest["fileCount"]),
        "WHITELIST_COUNT": str(len(spec["WHITELIST"])),
        "DENYLIST_COUNT": str(len(spec["DENYLIST"])),
        "PENDING_COUNT": str(len(spec["PENDING_DECISION"])),
        "NOTES_PRESERVE_COUNT": str(len(preserve)),
        "NOTES_MISSING_COUNT": str(len(missing)),
        "NOTES_MISSING_LIST": "、".join(f"`{entry}`" for entry in missing),
        "RECORD_NAME": RECORD.name,
        "RECORD_PATH": f"onshape_docs/verification/{RECORD.name}",
        "RELEASE_URL": RELEASE_URL,
        "GOVERNANCE_RELEASE": spec["GOVERNANCE_RELEASE"],
        "MANIFEST_NAME": spec["MANIFEST_NAME"],
        "CHECKSUM_SIDECAR_NAME": spec["CHECKSUM_SIDECAR_NAME"],
    }


TEMPLATE = r"""kind: ewf-instance
spec_version: "@@SPEC_VERSION@@"

# ===========================================================================
# onshapescript 的 EWF 项目实例 —— 写方向（EWF @@SPEC_VERSION@@）
#
# 生成者：dev/tools/build_ewf_instance.py。本文件不是手写的：它由该脚本从三份真实发布
# 数据生成，并在写出之前先复算一遍。源数据：
#
#   S1 已发布归档 @@ARCHIVE_NAME@@
#      与同名 .sha256 边车（/home/lijq/code/onshapescript-releases/），以及归档内
#      的 @@MANIFEST_NAME@@ / @@CHECKSUM_SIDECAR_NAME@@ / RELEASE-NOTES.md
#   S2 发布工具源码 dev/tools/consumer_release_spec.py 的发布点那一版（白名单 / 黑名单 / plan()）
#   S3 发布验证记录 @@RECORD_PATH@@
#
# 生成前的硬校验（任何一条对不上即拒绝写出）：
#   * 归档 sha256 == 边车 == 验证记录里的那一个摘要；
#   * 归档内清单的 @@MANIFEST_FILE_COUNT@@ 条逐文件摘要，在解包树上全部复算一致；
#   * annotated tag v1.3.0 指向的 commit == manifest.sourceRevision == @@REVISION@@；
#   * 归档 @@ZIP_ENTRY_COUNT@@ 个条目的时间戳全为 1980-01-01。
#
# 本文件里的每一个读数都由上述数据算出，不是手抄；会随后续提交漂移的读数一律
# 不写（判据见 README「权威来源」）。三张图分开表达（EWF-GEN-005）：
# maturity[]（Lifecycle）/ workflows[]（Workflow Graph）/ execution（Execution Graph）。
# ===========================================================================

instance:
  id: onshapescript-release-1.3.0
  title:
    zh: onshapescript consumer Release 1.3.0 的构建、发布与宿主就地刷新
    en: Building, publishing and host-refreshing the onshapescript consumer Release 1.3.0
  mode: real

  boundary:
    in_scope:
      - 把产物内容契约写成可执行的不变量（白名单 / 黑名单 / plan() / validate()），并能离线产出 spec-only 清单
      - 由版本化源码构建可复现归档，并随归档写出逐文件摘要清单与 sha256sum 边车
      - 在 checkout 之外解包并启动 stdio 服务，作为集成与安装自检
      - 把归档发布到 GitHub Release v1.3.0，并以下载回流（而不是信任上传结果）复核已发布对象
      - 在既有原生 Windows 安装树上只替换版本化代码，并核对保留状态既未被写入也未被删除
    out_of_scope:
      - MCP 工具功能面的日常开发；本实例只承载 @@REVISION@@ 那一次发布与一次宿主对齐
      - Onshape 云端对象、REST 配额、凭据与浏览器 profile 的日常运维（由各自模块持有）
      - 许可与再分发授权谈判（本实例只登记边界，不做决定）
      - 治理包 @@GOVERNANCE_RELEASE@@ 的身份与版本（与被发布的产物无关）
      - 对更早或更晚的 revision 重新出包
    entry_points:
      - kind: existing-artifact
        description: >-
          既有 onshapescript git 源码树。发布点是 annotated tag v1.3.0 指向的
          @@REVISION@@（提交时间 @@COMMIT_DATE@@）；源码、提交历史与分支由 git 持有，
          本实例只在它之上做一次产物发布。
        ref: ART-OSH-SRC
        external_ref: git-onshapescript
        lifecycle_history_owned: false
      - kind: existing-artifact
        description: >-
          既有原生 Windows 消费者安装树（部署约定 C:\MCP\onshapescript）。它承载可运行的
          解包产物，并持有不属于产物的可变状态：浏览器 profile、凭据、配额账本、本地配置、
          几何后端选择。这些状态的存亡不由产物生命周期决定。
        ref: SUBJ-OSH-HOST
        external_ref: fs-windows-install
        lifecycle_history_owned: false
      - kind: event
        description: >-
          owner 决策 2026-09-26：发布渠道由「本地文件交付」改为 GitHub Release，发布成为唯一
          写外部系统的一步；同一条提交把记录中的决定与渠道一起改掉。
        ref: DEC-OSH-CHANNEL
        external_ref: git-onshapescript
        lifecycle_history_owned: false
      - kind: defect
        description: >-
          本发布链上两次真实的产物级缺陷：归档曾携带机器本地的几何后端选择文件（解包即静默
          关闭宿主已启用的后端）；修好后又发现保留清单发布的是「构建 checkout 中恰好存在」
          的子集，而不是主机无关的完整黑名单。
        ref: DEF-OSH-GEOMBACKEND
        external_ref: git-onshapescript
        lifecycle_history_owned: false
    boundary_note: >-
      本实例只覆盖 consumer Release 1.3.0（revision @@REVISION@@）的产物构建、发布与一次
      宿主就地刷新。onshapescript 在此之前的需求、架构与运行历史客观存在，但它们 MAY 不属于本
      实例：入口只声明既有对象与既有缺陷存在，MUST NOT 要求 EWF 先拥有它们过去的完整
      lifecycle（EWF-EXT-002、EWF-EXT-003）。同样，本实例 MUST NOT 复制 git、GitHub Release
      与仓库自身文档所持有的治理历史（EWF-EXT-001）。

  governance_drivers: [cost-of-failure, reversibility, rollback-need, artifact-count, evidence-need, repeated-manufacture, regulatory-formality]

  subjects:
    - id: SUBJ-OSH-SRC
      name:
        zh: onshapescript 版本化源码树
        en: onshapescript versioned source tree
      domain: software
      kind: component
      responsibility: 持有被发布的源码与提交历史；发布点是它上面一个不可变的 revision
      managed: true
      note:
        text: >-
          本实例对它的改动只有发布工具与依赖形态，不改模块划分与依赖方向。进入本实例时的
          发布点 revision 为 @@REVISION@@。
      children:
        - id: SUBJ-OSH-TOOLING
          name:
            zh: 发布规格与构建工具
            en: Release specification and build tooling
          domain: software
          kind: subsystem
          responsibility: 把产物内容契约做成可执行的不变量，并把同一条计划构造成可复现归档
          managed: true
          note:
            text: >-
              唯一真相源是 dev/tools/consumer_release_spec.py 的 WHITELIST / DENYLIST /
              plan()；docs/operations/RELEASE.md 是人可读投影。构建器自己不发明文件列表，
              规格不变量不成立时它一个字节也不写。

    - id: SUBJ-OSH-ARTIFACT
      name:
        zh: consumer Release 产物
        en: Consumer release artifact
      domain: software
      kind: component
      responsibility: 一个 extract-and-run 的版本化代码树；身份由 server 版本、来源 revision 与归档摘要共同给定
      managed: true
      note:
        text: >-
          产物身份与治理包身份被刻意分开：产物版本是 1.3.0，而 @@GOVERNANCE_RELEASE@@
          是开发面的治理依赖，产物不携带它也不引用它。

    - id: SUBJ-OSH-HOST
      name:
        zh: 原生 Windows 消费者安装树与其保留状态
        en: Native-Windows consumer install tree and its preserved state
      domain: software
      kind: infrastructure
      responsibility: 承载可运行的解包产物，并持有不属于产物的可变状态（profile、凭据、配额账本、本地配置、几何后端选择）
      managed: true
      note:
        text: >-
          把它单列为 subject 是本实例的一处判断：产物与安装树不是同一个工程对象，「只替换版本化
          代码、绝不删除状态」这条升级语义正是两者之间的关系。刷新与升级在同一棵树上都发生过。

    - id: SUBJ-OSH-UPSTREAM
      name:
        zh: 随产物再分发的上游语料与 wheel
        en: Vendored upstream corpus and wheels redistributed with the artifact
      domain: software
      kind: component
      responsibility: 由上游持有版权与许可、随产物一起被再分发的参考语料与二进制依赖
      managed: false
      external_ref: {system: git, external_id: git-onshape-std-library-mirror, external_kind: repository, ownership: external, role: source, sync_policy: reference-only, imported_history: false}
      note:
        text: >-
          它不被本实例管理，因此没有 maturity 条目。本实例只登记这条再分发边界，不做授权决定；
          许可条款的事实源在语料目录内，不在 EWF 里。

  maturity:
    - {subject: SUBJ-OSH-SRC, stage: implementation-realization, status: complete, note: {text: "发布点 @@REVISION@@ 是一个已提交、已打 annotated tag 的 revision；本实例不重建它，只在它之上出包。"}}
    - {subject: SUBJ-OSH-TOOLING, stage: requirements-definition, status: complete, evidence: [REQ-OSH-CONTENT], note: {text: "内容契约以 WHITELIST / DENYLIST / plan() 固化；已登记的白名单 @@WHITELIST_COUNT@@ 条、黑名单 @@DENYLIST_COUNT@@ 条、待决路径 @@PENDING_COUNT@@ 条。"}}
    - {subject: SUBJ-OSH-TOOLING, stage: design, status: complete, evidence: [DEC-OSH-FORMAT, DEC-OSH-SIGNING], note: {text: "格式与签名状态被显式决定并写进清单，而不是留作隐含假设。"}}
    - {subject: SUBJ-OSH-TOOLING, stage: implementation-realization, status: complete, note: {text: "build_release.py 固定条目时间戳、排序计划条目、固定压缩级别；同一个树应当给出逐字节相同的归档。"}}
    - {subject: SUBJ-OSH-TOOLING, stage: verification, status: complete, evidence: [E-OSH-INTEGRITY], note: {text: "规格自身的不变量由 validate() 守卫；构建前先 validate()，不变量不成立就拒绝构建。"}}
    - {subject: SUBJ-OSH-ARTIFACT, stage: need-problem-definition, status: complete, note: {text: "产物必须可构建、可校验、可发布，且刷新不得损失宿主状态；判据 CRIT-OSH-CONTENT / CRIT-OSH-REPRO / CRIT-OSH-SELFCHECK / CRIT-OSH-STATE。"}}
    - {subject: SUBJ-OSH-ARTIFACT, stage: requirements-definition, status: complete, evidence: [REQ-OSH-CONTENT, REQ-OSH-REPRO], note: {text: "两条要求都可判定：内容恰好等于计划集合、同一树给出逐字节相同归档。"}}
    - {subject: SUBJ-OSH-ARTIFACT, stage: design, status: complete, evidence: [DEC-OSH-FORMAT, DEC-OSH-SIGNING], note: {text: "消费者是原生 Windows、无 git / 无 APG / 无 WSL；格式与签名状态由此决定。"}}
    - {subject: SUBJ-OSH-ARTIFACT, stage: implementation-realization, status: complete, evidence: [ART-OSH-ARCHIVE, ART-OSH-MANIFEST], note: {text: "归档 @@ARCHIVE_NAME@@（@@ARCHIVE_BYTES@@ 字节，@@ZIP_ENTRY_COUNT@@ 个条目 = @@MANIFEST_FILE_COUNT@@ 个计划文件 + @@BUILD_EXTRA_ENTRIES@@ 个构建期文件）。"}}
    - {subject: SUBJ-OSH-ARTIFACT, stage: integration, status: complete, evidence: [E-OSH-SELFCHECK], note: {text: "在 checkout 之外解包并以移除 PYTHONPATH 的系统解释器启动 stdio 服务，确认各模块组合成一个可安装整体。"}}
    - {subject: SUBJ-OSH-ARTIFACT, stage: verification, status: complete, evidence: [E-OSH-INTEGRITY, E-OSH-DOWNLOADBACK], note: {text: "归档摘要、逐文件摘要 @@MANIFEST_FILE_COUNT@@ 条，以及发布后的下载回流摘要比对。"}}
    - {subject: SUBJ-OSH-ARTIFACT, stage: transition-to-use, status: complete, evidence: [RLS-OSH-1.3.0], note: {text: "GitHub Release v1.3.0 的资产恰好是归档与 .sha256 边车；这些事实可现场复核（见 README）。"}}
    - {subject: SUBJ-OSH-HOST, stage: transition-to-use, status: complete, evidence: [E-OSH-HOST], note: {text: "就地刷新只写属于产物的路径，重启后桥代次递进且客户端被保留。"}}
    - {subject: SUBJ-OSH-HOST, stage: validation, status: complete, evidence: [E-OSH-HOST], note: {text: "刷新后产物内容逐文件等值、保留状态文件的 mtime 与内容不变、运行时几何后端选择不变。"}}
    - {subject: SUBJ-OSH-HOST, stage: operation-sustainment-feedback, status: complete, evidence: [E-OSH-HOST], note: {text: "刷新没有让宿主付出第二次人工登录与配额代价；这是「状态被当成状态对待」的直接兑现。"}}

  derived:
    derived: true
    basis: ["maturity[] 中每个 subject 的最新 complete 条目"]
    per_subject: {SUBJ-OSH-SRC: implementation-realization, SUBJ-OSH-TOOLING: verification, SUBJ-OSH-ARTIFACT: transition-to-use, SUBJ-OSH-HOST: operation-sustainment-feedback}
    note: {text: "本块只是展示用的派生摘要，事实源是上面的 maturity[] 集合（EWF-LC-002）。上游语料 subject 未被管理，因此不出现在这里。"}

  tailoring:
    profile_id: TLR-OSH
    operations:
      - id: TLR-OSH-01
        op: INLINE
        target: {kind: stage, ids: [architecture-definition]}
        into: 既有模块边界与依赖方向（mcp_main / onshape_docs / onshape_rest_api_mode / onshape_browser_mode）
        rationale: >-
          这一次发布没有改模块划分与依赖方向；唯一沾到架构的是一条新的交付契约（产物 ↔ 安装树），
          它由 REL 层的 Interface 承载。把 architecture-definition 内联进既有模块文档，而不是让
          它在这份发布实例里再成熟一次。
        preserves_semantics: true
        basis: [模块边界与依赖方向由既有代码与既有文档承载, 本次只调依赖到达时机而不改依赖图]
      - id: TLR-OSH-02
        op: COLLAPSE_LEVEL
        target: {kind: workflow, ids: [WF-OSH-BUILD, WFBUILD-PLAN, WFBUILD-ZIP, WFBUILD-MANIFEST]}
        into: 一次 build_release.py 调用
        governance_value_absent: [routing, decision, gate]
        rationale: >-
          生成计划、写归档、写 manifest / SHA256SUMS / 外层摘要由同一次构建调用完成，三者之间
          没有可路由分支、没有方案取舍、没有质量门。判据是该层缺少独立治理价值，而不是子节点数量
          （EWF-TLR-002）。折叠没有取消义务：产物与清单仍在同一执行节点上被生产与引用。
        preserves_semantics: true
      - id: TLR-OSH-03
        op: REMOVE_PERSISTENCE
        target: {kind: entity, ids: [change, verification-case]}
        rationale: >-
          发布链上客观发生了变更（两次产物级缺陷各触发一次修改），也有待验证条目（内容、可复现、
          自检、状态保留）；但本实例不为它们建受管 Record。变更事实由 git 提交历史持有，待验证条目
          写在 requirement 的 criterion 上（EWF-ENT-001、EWF-ENT-002、EWF-ENT-004）。
        preserves_semantics: true
        basis: [提交历史与 GitHub Release 已承载变更事实, 返工由 reentry 边表达而不新建 Change Record]
      - id: TLR-OSH-04
        op: REMOVE_GATE
        target: {kind: gate, ids: [signing-gate, clean-windows-acceptance-gate]}
        rationale: >-
          素材把「是否对产物与清单签名」和「在干净消费者 Windows 环境上的原生验收」显式记为未决事项
          （docs/operations/RELEASE.md 的 Open decisions）；今天既不成立也不由本实例持有，因此不为
          它们建 Gate。未决不是缺陷，但把它建模成 Gate 会让读者以为它有判定标准。
        preserves_semantics: true
        basis: [RELEASE.md 明写这两项未决, 今天的产物 unsigned 且只做离线代理验收]
      - id: TLR-OSH-05
        op: REDUCE_FORMALITY
        target: {kind: formality, ids: [GATE-OSH-REFRESH]}
        from_formality: formal-approval
        to_formality: self-check
        rationale: >-
          就地刷新由「dry-run 计划集合必须恰好等于被审查过的产物条目集合，出现未列路径即中止」
          外加刷新后逐文件复核自证，由单个 Operator 执行。它不是多人正式审批，但强于隐式判断，
          因此降到 self-check 而不是移除。
        preserves_semantics: true
        basis: [刷新有可中止的 allow-list 守卫, 刷新后可逐文件复核内容等值与 mtime]
      - id: TLR-OSH-06
        op: REMOVE_TRACEABILITY
        target: {kind: traceability, ids: [release-evidence-trace-matrix]}
        traceability_scope: [产物规格变更 → 受影响离线证据子集, 产物 → 摘要 / 清单 → 回流校验证据]
        rationale: >-
          本仓库自己持有一份 change → required evidence 的追溯矩阵（docs/verification/MATRIX.md），
          并由「每次发布都记录 tests / digest / 宿主对齐」的验证记录兑现。本实例不复制第二份全局追溯
          义务（EWF-EXT-001、EWF-EXT-004）；REL 层仍保留语义链接，但不承担全局义务。
        preserves_semantics: true

  workflows:
    - id: WF-OSH-PUBLISH
      name:
        zh: consumer Release 发布工作流（含跨 Stage 回边）
        en: Consumer-release workflow with cross-stage re-entry
      scope: cross-stage
      applies_to_stages: [requirements-definition, design, implementation-realization, integration, verification, transition-to-use, validation, operation-sustainment-feedback]
      nodes:
        - {id: WFPUB-CONTRACT, work_node: plan, label: {zh: 固化产物内容契约, en: Fix the artifact content contract}, is_control_point: true, branch_role: decision}
        - {id: WFPUB-DECIDE, work_node: decide, label: {zh: 决定格式 / 渠道 / 签名, en: "Decide format, channel and signing"}}
        - {id: WFPUB-BUILD, work_node: build, label: {zh: 构建可复现归档与清单, en: Build the reproducible archive and manifest}}
        - {id: WFPUB-CHECK, work_node: inspect, label: {zh: 离线完整性与清单校验, en: Offline integrity and manifest check}, is_control_point: true, branch_role: decision}
        - {id: WFPUB-SELFCHECK, work_node: integrate, label: {zh: 解包树整体启动自检, en: Extract-and-run self-check}}
        - {id: WFPUB-PUBLISH, work_node: transition, label: {zh: 发布 GitHub Release, en: Publish the GitHub Release}}
        - {id: WFPUB-DOWNLOADBACK, work_node: inspect, label: {zh: 下载回流复核, en: Download-back re-verification}, is_control_point: true, branch_role: decision}
        - {id: WFPUB-REFRESH, work_node: transition, label: {zh: 宿主就地代码刷新, en: In-place host code refresh}, is_control_point: true, branch_role: decision}
        - {id: WFPUB-ACCEPT, work_node: observe, label: {zh: 宿主运行时验收, en: Host runtime acceptance}, is_control_point: true, branch_role: decision}
      edges:
        - {from: WFPUB-CONTRACT, to: WFPUB-DECIDE, kind: sequence, when: always}
        - {from: WFPUB-DECIDE, to: WFPUB-BUILD, kind: sequence, when: always}
        - {from: WFPUB-BUILD, to: WFPUB-CHECK, kind: sequence, when: always}
        - {from: WFPUB-CHECK, to: WFPUB-SELFCHECK, kind: sequence, when: pass}
        - {from: WFPUB-SELFCHECK, to: WFPUB-PUBLISH, kind: sequence, when: pass}
        - {from: WFPUB-PUBLISH, to: WFPUB-DOWNLOADBACK, kind: sequence, when: always}
        - {from: WFPUB-DOWNLOADBACK, to: WFPUB-REFRESH, kind: sequence, when: pass}
        - {from: WFPUB-REFRESH, to: WFPUB-ACCEPT, kind: sequence, when: always}
        - {from: WFPUB-CHECK, to: WFPUB-CONTRACT, kind: reentry, when: fail, label: {zh: 内容契约本身不成立, en: The content contract itself is wrong}}
        - {from: WFPUB-CHECK, to: WFPUB-BUILD, kind: reentry, when: fail, label: {zh: 契约成立但构建结果不合格, en: Contract holds but the build output fails}}
        - {from: WFPUB-DOWNLOADBACK, to: WFPUB-BUILD, kind: reentry, when: fail, label: {zh: 已发布对象与本地构建不一致, en: The published object differs from the local build}}
        - {from: WFPUB-ACCEPT, to: WFPUB-BUILD, kind: reentry, when: fail, label: {zh: 宿主验收失败则重新构建重发, en: Rebuild and re-release when host acceptance fails}}
      supports: {branch: false, merge: false, loop: false, parallel: false, reentry: true, cross_stage: true}
      note:
        text: >-
          回边一端在 verification（WFPUB-CHECK / WFPUB-DOWNLOADBACK）与 validation
          （WFPUB-ACCEPT），另一端在 requirements-definition（WFPUB-CONTRACT）或
          implementation-realization（WFPUB-BUILD），两端 Stage 不同，因此本 Workflow MUST 声明
          cross-stage（EWF-WF-005）。这些回边在素材里真实走过：1.3.0 之前有三次重新发布，其中两次由
          产物级缺陷触发。EWF 没有字段记录「走过几次」（见 README 的绕行条目）。
    - id: WF-OSH-BUILD
      name:
        zh: 可复现归档构建工作流（本实例被折叠）
        en: Reproducible archive build workflow (collapsed here)
      scope: stage-local
      applies_to_stages: [implementation-realization]
      nodes:
        - {id: WFBUILD-PLAN, work_node: plan, label: {zh: 生成白名单计划, en: Emit the whitelist plan}, branch_role: plain}
        - {id: WFBUILD-ZIP, work_node: build, label: {zh: 写压缩归档, en: Write the archive}, branch_role: plain}
        - {id: WFBUILD-MANIFEST, work_node: build, label: {zh: 写 manifest / SHA256SUMS / 外层摘要, en: "Write manifest, SHA256SUMS and outer digest"}, branch_role: plain}
      edges:
        - {from: WFBUILD-PLAN, to: WFBUILD-ZIP, kind: sequence, when: always}
        - {from: WFBUILD-ZIP, to: WFBUILD-MANIFEST, kind: sequence, when: always}
      supports: {branch: false, merge: false, loop: false, parallel: false, reentry: false, cross_stage: false}
      note:
        text: >-
          这条链两端同在 implementation-realization、没有跨 Stage 回边，因此 scope 是 stage-local，
          与 WF-OSH-PUBLISH 构成 EWF-WF-005 判据下的对照。它被 TLR-OSH-02 折叠成一次 build_release.py。

  method_capability_bindings:
    - {id: MCB-OSH-01, work_node: plan, method: release-content-contract, capability: release-plan-derivation, tool: consumer-release-spec, tool_kind: software, layer_collapse: true, address: {subject: SUBJ-OSH-TOOLING, stage: requirements-definition}, note: {text: "真实入口是 dev/tools/consumer_release_spec.py；plan() 是文件列表的唯一真相源，--check 写出 artifactStatus: spec-only（只描述、不构建、不压缩）。"}}
    - {id: MCB-OSH-02, work_node: decide, method: release-policy-tradeoff, capability: release-policy-judgment, layer_collapse: true, address: {subject: SUBJ-OSH-ARTIFACT, stage: design}, note: {text: "格式 / 渠道 / 签名三项取舍；method 与 capability 在本项目里本来就是同一件事的两种说法（OQ-001 未冻结），因此显式标记坍缩。"}}
    - {id: MCB-OSH-03, work_node: build, method: reproducible-archive-build, capability: deterministic-packaging, tool: build-release, address: {subject: SUBJ-OSH-ARTIFACT, stage: implementation-realization}, note: {text: "真实入口是 dev/tools/build_release.py：固定 1980 条目时间戳、排序计划条目、固定压缩级别；revision 默认取 git 短 HEAD，脏树带 -dirty 后缀。"}}
    - {id: MCB-OSH-04, work_node: inspect, method: digest-and-manifest-check, capability: content-integrity-check, tool: sha256sum, address: {subject: SUBJ-OSH-ARTIFACT, stage: verification}, note: {text: "外层摘要覆盖归档本身；内层 SHA256SUMS 覆盖恰好 @@MANIFEST_FILE_COUNT@@ 个计划文件。"}}
    - {id: MCB-OSH-05, work_node: integrate, method: extract-and-run-selfcheck, capability: package-integration-check, tool: python-stdio-smoke, address: {subject: SUBJ-OSH-ARTIFACT, stage: integration}, note: {text: "在 checkout 之外解包、移除 PYTHONPATH、用系统解释器起 stdio 服务，确认组合成一个可安装整体。"}}
    - {id: MCB-OSH-06, work_node: transition, method: release-publication, capability: artifact-distribution, tool: gh-release, address: {subject: SUBJ-OSH-ARTIFACT, stage: transition-to-use}, note: {text: "真实命令是 gh release create；资产只有归档与 .sha256 边车，Release body 取归档内 RELEASE-NOTES.md。这是唯一写外部系统的一步，需显式批准。"}}
    - {id: MCB-OSH-07, work_node: inspect, method: download-back-verification, capability: content-integrity-check, tool: gh-release, address: {subject: SUBJ-OSH-ARTIFACT, stage: verification}, note: {text: "与 MCB-OSH-04 共用同一条 capability、不同 method：用「下载回流」而不是「信任上传结果」来确认已发布对象。"}}
    - {id: MCB-OSH-08, work_node: transition, method: in-place-code-refresh, capability: deployed-code-replacement, tool: rsync, address: {subject: SUBJ-OSH-HOST, stage: transition-to-use}, note: {text: "只替换版本化代码：dry-run 的计划集合必须恰好等于被审查过的产物条目集合，带 -c 校验内容、不带 --delete。"}}
    - {id: MCB-OSH-09, work_node: observe, method: host-runtime-observation, capability: runtime-acceptance-observation, tool: onshape-mcp-tools, address: {subject: SUBJ-OSH-HOST, stage: validation}, note: {text: "刷新后由项目自己的只读工具取证：产物逐文件等值、保留状态 mtime 不变、几何后端选择不变、桥代次递进。"}}

  stage_reductions: [need-problem-definition, requirements-definition, design, implementation-realization, integration, verification, validation, transition-to-use, operation-sustainment-feedback]

  managed_entities: [need-problem, requirement, artifact, baseline, release, decision, verification-evidence, defect-issue, measurement]

  declared_ids: [CRIT-OSH-CONTENT, CRIT-OSH-REPRO, CRIT-OSH-SELFCHECK, CRIT-OSH-STATE, BAS-OSH-1.3.0-PREV]

  entities:
    - id: NEED-OSH-RELEASE
      kind: need-problem
      title:
        zh: 产物要可构建、可校验、可发布，且刷新不得损失宿主状态
        en: The artifact must be buildable, verifiable and publishable, and a refresh must not cost host state
      statement: >-
        consumer Release 产物 MUST 能从版本化源码构建、可在不信任上传方的前提下被复核、可被发布到
        一个按 revision 定位的渠道，并能在既有宿主上只替换代码而不触碰可变状态。
      existence: {engineering_object: present, record: context-only, managed: false}
      address: {subject: SUBJ-OSH-ARTIFACT, stage: need-problem-definition}
      criterion:
        statement: 一次完整发布链结束后，产物内容与 plan() 的差异 MUST 为 0；已发布归档的 sha256 MUST 与本地构建一致；宿主保留状态文件被改动的数量 MUST 为 0。
        metric: release-invariant-violation-count
        operator: eq
        value: "0"
        condition: 构建 → 非 checkout 目录解包自检 → 发布 → 下载回流 → 宿主就地刷新
        procedure: 比对 plan() 输出与实际归档条目；以 sha256sum -c 复核外层与内层摘要；比对刷新前后保留状态文件的内容与 mtime
      need_problem:
        source: owner 关于发布渠道与 resident 默认值的决定，加上发布链上暴露的两处产物级缺陷
        trigger_kind: defect
        accepted_boundary: 只做 consumer Release 1.3.0 的产物构建、发布与一次宿主对齐；不改 MCP 工具功能面，不改 Onshape 云端对象，不决定许可与再分发授权
        problem_statement: 产物一度既不是一等工程对象（无内容契约、无摘要清单），也不是可安全重复施加的对象（升级可能覆盖或删除宿主状态）；本实例把这两件事一次做实。
      note: {text: "这条 Need 既是 Lifecycle Input，也是本实例唯一的 need-problem 实体；它不形成持久记录（EWF-ENT-001、EWF-ENT-002）。"}

    - id: REQ-OSH-CONTENT
      kind: requirement
      title:
        zh: 产物内容契约
        en: Artifact content contract
      statement: >-
        归档内容 MUST 恰好等于白名单减去黑名单的计划集合；MUST NOT 携带开发面内容、机器本地状态或
        运行期可变状态；清单 MUST 逐文件给出 workspace 相对 POSIX 路径、字节数与 SHA-256。
      existence: {engineering_object: present, record: context-only, managed: false}
      address: {subject: SUBJ-OSH-ARTIFACT, stage: requirements-definition}
      criterion:
        statement: 计划外路径数量 MUST 为 0，黑名单命中数量 MUST 为 0，清单条目数 MUST 等于归档内计划文件数。
        metric: unplanned-or-denylisted-path-count
        operator: eq
        value: "0"
        condition: 在 checkout 之外构建的 1.3.0-@@REVISION@@ 归档
        procedure: 对归档全部条目做开发面 / 状态残留扫描，并用 manifest 与 SHA256SUMS 逐文件复核
      requirement: {derived_from: [NEED-OSH-RELEASE], verified_by: [E-OSH-INTEGRITY, E-OSH-DOWNLOADBACK]}
      note: {text: "机器可读载体是 dev/tools/consumer_release_spec.py 的 WHITELIST / DENYLIST 与 plan() / validate()；RELEASE.md 是可派生的人可读投影（EWF-DOC-003）。"}

    - id: REQ-OSH-REPRO
      kind: requirement
      title:
        zh: 构建必须可复现
        en: The build must be reproducible
      statement: >-
        同一个源码树 MUST 给出逐字节相同的归档；归档条目 MUST 用固定时间戳与稳定顺序，使
        「哪些文件来自产物、哪些是宿主状态」可以只靠时间戳判别。
      existence: {engineering_object: present, record: context-only, managed: false}
      address: {subject: SUBJ-OSH-ARTIFACT, stage: requirements-definition}
      criterion:
        statement: 归档内全部条目的时间戳 MUST 为固定值（1980-01-01），且计划条目 MUST 按路径排序。
        metric: non-fixed-entry-timestamp-count
        operator: eq
        value: "0"
        condition: 在 checkout 之外构建的 1.3.0-@@REVISION@@ 归档
        procedure: 读归档条目时间戳与顺序；同树重跑构建并比较归档摘要
      requirement: {derived_from: [NEED-OSH-RELEASE], verified_by: [E-OSH-INTEGRITY]}
      note: {text: "固定时间戳不只是可复现手段，它同时是刷新阶段的判别依据：产物文件带 1980 时间戳，宿主状态保留真实 mtime。", refs: [CRIT-OSH-REPRO]}

    - id: REQ-OSH-SELFCHECK
      kind: requirement
      title:
        zh: 安装自检必须零 Onshape 请求
        en: Install self-check must make zero Onshape requests
      statement: >-
        安装 / 自检 MUST NOT 联系 Onshape；启动 stdio 服务并完成一次 initialize / tools/list 交换
        即算通过，且 MUST 报出 server 身份与运行时策略 revision。
      existence: {engineering_object: present, record: context-only, managed: false}
      address: {subject: SUBJ-OSH-ARTIFACT, stage: requirements-definition}
      criterion:
        statement: 安装自检期间发往 Onshape 的请求数 MUST 为 0。
        metric: onshape-request-count-during-install-self-check
        operator: eq
        value: "0"
        condition: LIVE_API_ENABLED 未设置；无浏览器工作；系统解释器、PYTHONPATH 已移除
        procedure: 在解包目录内启动 stdio 服务，观察 initialize / tools/list 应答与退出码
      requirement: {derived_from: [NEED-OSH-RELEASE], verified_by: [E-OSH-SELFCHECK]}
      note: {text: "「自检成功」被刻意写成可判定的空集：不给外部系统发任何请求。"}

    - id: REQ-OSH-STATE
      kind: requirement
      title:
        zh: 刷新与升级不得触碰保留状态
        en: Refresh and upgrade must not touch preserved state
      statement: >-
        就地刷新 MUST NOT 写入或删除黑名单中的任何路径；刷新后每个保留状态文件的内容与 mtime
        MUST 不变（归档内文件的固定 1980 时间戳是可判别的对照）。
      existence: {engineering_object: present, record: context-only, managed: false}
      address: {subject: SUBJ-OSH-HOST, stage: requirements-definition}
      criterion:
        statement: 刷新计划中出现的保留状态路径数 MUST 为 0；刷新后被改动过的保留状态文件数 MUST 为 0。
        metric: preserved-state-files-changed
        operator: eq
        value: "0"
        condition: 在既有宿主安装树上的一次就地刷新
        procedure: 先 dry-run 出计划集合并与被审查的产物条目集合逐条比对；刷新后逐文件比对内容等值与 mtime
      requirement: {derived_from: [NEED-OSH-RELEASE], validated_by: [E-OSH-HOST]}
      note: {text: "这条要求是「记录由谁持有」的直接体现：配额账本与浏览器 profile 不属于产物，MUST NOT 由产物生命周期决定其存亡。"}

    - id: ART-OSH-SRC
      kind: artifact
      title:
        zh: 既有 onshapescript git 源码树
        en: Existing onshapescript git source tree
      statement: >-
        进入本实例时的版本化源码树；发布点是 annotated tag v1.3.0 指向的 @@REVISION@@
        （提交时间 @@COMMIT_DATE@@），源码与提交历史由 git 持有。
      existence: {engineering_object: present, record: external-reference, managed: false}
      address: {subject: SUBJ-OSH-SRC, stage: implementation-realization}
      artifact: {realization_kind: other, identity: "git:onshapescript:@@REVISION@@"}
      external_ref: {system: git, external_id: git-onshapescript, external_kind: repository, ownership: external, role: source, sync_policy: reference-only, imported_history: false}
      note: {text: "engineering_object: present 而 record: external-reference：客体存在，记录由 git 持有，本实例不导入其完整历史（EWF-EXT-001、EWF-ENT-001）。"}

    - id: ART-OSH-ARCHIVE
      kind: artifact
      title:
        zh: consumer Release 归档 1.3.0-@@REVISION@@
        en: Consumer release archive 1.3.0-@@REVISION@@
      statement: >-
        由版本化源码构建的 extract-and-run 归档；@@ZIP_ENTRY_COUNT@@ 个条目 =
        @@MANIFEST_FILE_COUNT@@ 个计划文件 + @@BUILD_EXTRA_ENTRIES@@ 个构建期文件
        （@@MANIFEST_NAME@@、@@CHECKSUM_SIDECAR_NAME@@、RELEASE-NOTES.md）；未签名。
      existence: {engineering_object: present, record: context-only, managed: false}
      address: {subject: SUBJ-OSH-ARTIFACT, stage: implementation-realization}
      artifact: {realization_kind: software-package, satisfies: [REQ-OSH-CONTENT, REQ-OSH-REPRO], identity: "sha256:@@ARCHIVE_SHA256@@"}
      provenance: {produced_by: N3, method: reproducible-archive-build, capability: deterministic-packaging, tool: build-release, environment: "构建在 checkout 之外；revision 由 git 短 HEAD 给出"}
      note: {text: "真实身份是三元组：server 版本 1.3.0 + 来源 revision @@REVISION@@ + 归档摘要 @@ARCHIVE_SHA256@@，而 artifact.identity 只有一个字符串（见 README 的绕行条目）。"}

    - id: ART-OSH-MANIFEST
      kind: artifact
      title:
        zh: 逐文件摘要清单与 sha256sum 边车
        en: Per-file digest manifest and checksum sidecar
      statement: >-
        @@MANIFEST_NAME@@ 逐文件给出路径 / 字节数 / SHA-256，并给出完整 @@DENYLIST_COUNT@@ 项
        excludedPaths、sourceRevision、signed:false；@@CHECKSUM_SIDECAR_NAME@@ 是 sha256sum -c
        的输入；归档本身另有一个外层 .sha256 边车。
      existence: {engineering_object: present, record: context-only, managed: false}
      address: {subject: SUBJ-OSH-ARTIFACT, stage: implementation-realization}
      artifact: {realization_kind: document, satisfies: [REQ-OSH-CONTENT]}
      provenance: {produced_by: N3, method: reproducible-archive-build, capability: deterministic-packaging, tool: build-release}
      note: {text: "清单里的 excludedPaths 是**主机无关的完整黑名单**：产物在一台机器上构建、在另一台机器上安装，用构建 checkout 的观测结果冒充契约会漏掉恰好在别处的状态路径。"}

    - id: ART-OSH-UPSTREAM
      kind: artifact
      title:
        zh: 随产物再分发的上游语料与 wheel
        en: Upstream corpus and wheels redistributed with the artifact
      statement: >-
        白名单里包含由上游持有版权与许可的材料：本地 FeatureScript 参考语料、Onshape 原生文档
        副本，以及内置的浏览器公共库 wheel。它们随归档一起被再分发。
      existence: {engineering_object: present, record: external-reference, managed: false}
      address: {subject: SUBJ-OSH-UPSTREAM, stage: implementation-realization}
      artifact: {realization_kind: document, identity: "vendored:fsdoc+std-library+openapi+browser-common-wheel"}
      external_ref: {system: git, external_id: git-onshape-std-library-mirror, external_kind: repository, ownership: external, role: source, sync_policy: reference-only, imported_history: false}
      note: {text: "许可与版权由上游持有，事实源在语料目录内的许可文件；本实例只登记这条边界，不复制许可治理（EWF-EXT-001）。"}

    - id: BAS-OSH-1.3.0
      kind: baseline
      title:
        zh: 1.3.0-@@REVISION@@ 的受控配置
        en: The controlled configuration of 1.3.0-@@REVISION@@
      statement: >-
        Release 1.3.0-@@REVISION@@ 的稳定引用集合：server 版本、来源 revision、归档摘要、
        逐文件摘要清单与内置 wheel 的摘要约定。
      existence: {engineering_object: present, record: context-only, managed: false}
      address: {subject: SUBJ-OSH-ARTIFACT, stage: integration}
      baseline:
        configuration:
          - {kind: software-commit, identity: "@@REVISION@@", subject: SUBJ-OSH-SRC}
          - {kind: other, identity: "@@ARCHIVE_NAME@@ (sha256 @@ARCHIVE_SHA256@@)"}
          - {kind: document-revision, identity: "@@MANIFEST_NAME@@ sourceRevision @@REVISION@@ 与 @@CHECKSUM_SIDECAR_NAME@@"}
          - {kind: other, identity: "内置浏览器公共库 wheel（按项目约定先校验摘要再安装）", subject: SUBJ-OSH-UPSTREAM}
        purpose: 让「验证的是哪个配置」可回答，并让下载回流复核有对照物
        supersedes: BAS-OSH-1.3.0-PREV
      note: {text: "本实例用上了 baseline.supersedes；对照之下 release payload 没有 supersedes 字段（见 README 的绕行条目）。前一个 baseline 只有语义 id、不携带 Record，因此只在 declared_ids 中。"}

    - id: RLS-OSH-1.3.0
      kind: release
      title:
        zh: GitHub Release v1.3.0
        en: GitHub Release v1.3.0
      statement: >-
        发布对象是打在 @@REVISION@@ 上的 annotated tag v1.3.0 及其两个资产：归档与 .sha256
        边车；Release body 取归档内 RELEASE-NOTES.md。URL 见 README 的权威来源。
      existence: {engineering_object: present, record: external-reference, managed: false}
      address: {subject: SUBJ-OSH-ARTIFACT, stage: transition-to-use}
      release: {released_baseline: BAS-OSH-1.3.0, package: [ART-OSH-ARCHIVE, ART-OSH-MANIFEST], release_gate: GATE-OSH-PUBLISH, transition_work_node: transition, target_environment: "GitHub Releases（发布渠道）与原生 Windows 消费者安装目录（投放目标）"}
      external_ref: {system: custom, system_name: github-releases, external_id: github-release-v1-3-0, external_kind: release, ownership: external, role: sink, sync_policy: manual, imported_history: false}
      note: {text: "Release != Lifecycle Stage：Release Record 面是本实体，Release Decision 由 GATE-OSH-PUBLISH 承担，publish 动作由 transition 节点承担（EWF-ENT-009）。已发布对象的最终权威在 GitHub 上，因此记录是 external-reference 级别，本实例只保留引用。"}

    - id: DEC-OSH-FORMAT
      kind: decision
      title:
        zh: 产物格式的选择
        en: Choice of the artifact format
      statement: 在 zip、wheel、zipapp / PyInstaller 之间选择 zip，且归档根即安装根。
      existence: {engineering_object: present, record: context-only, managed: false}
      address: {subject: SUBJ-OSH-ARTIFACT, stage: design}
      decision:
        alternatives:
          - wheel：需要 pip，且不会携带离线文档树
          - zipapp / PyInstaller：引入额外工具链，且会隐藏清单要公开的文件列表
          - zip：消费者是原生 Windows、无 git / 无 APG / 无 WSL，解包即可运行
        chosen: zip，无包装目录
        basis: 消费环境只有 Windows 自带能力；清单存在的意义正是公开完整文件列表，不能用一个隐藏列表的打包方式
      note: {text: "decision 是 candidate Entity（OQ-004）：本实例只把它当作普通 context-only 记录，不主张它是一等 Record。"}

    - id: DEC-OSH-CHANNEL
      kind: decision
      title:
        zh: 发布渠道的选择
        en: Choice of the publication channel
      statement: 在「只做本地文件交付」与「发布 GitHub Release」之间选择后者。
      existence: {engineering_object: present, record: context-only, managed: false}
      address: {subject: SUBJ-OSH-ARTIFACT, stage: design}
      decision:
        alternatives:
          - 只写本地文件并当场交付（原记录写的是 nothing is uploaded）
          - 发布为 GitHub Release，tag 指向构建它的 revision
        chosen: GitHub Release，且发布是唯一写外部系统的一步，需显式 owner 批准
        basis: 消费方需要一个可按 revision 定位的取得渠道；同一条提交把「记录中的决定」与「渠道」一起改变，避免文档与事实分叉
      note: {text: "这次决策同时修掉一处真实的文档漂移：RELEASE.md 之前记录的是反面，而构建器本身仍然什么都不上传。"}

    - id: DEC-OSH-SIGNING
      kind: decision
      title:
        zh: 签名状态的选择
        en: Choice of the signing state
      statement: 在「未签名 + SHA-256」与「代码签名」之间选择未签名，并在清单里显式记录 signed:false。
      existence: {engineering_object: present, record: context-only, managed: false}
      address: {subject: SUBJ-OSH-ARTIFACT, stage: design}
      decision:
        alternatives:
          - 对产物与清单做代码签名
          - 只做 SHA-256，并在 manifest 记录 signed:false
        chosen: 只做 SHA-256，并保持 signed:false 可机器读取
        basis: 代码签名需要证书，属于人或宿主层面的决定；把未签名状态写进清单，可以避免未签名产物被误当成已签名
      note: {text: "「是否签名」被留作未决，因此不为它建 Gate（TLR-OSH-04）。"}

    - id: E-OSH-INTEGRITY
      kind: verification-evidence
      title:
        zh: 产物完整性与清单校验结论
        en: Artifact integrity and manifest verification conclusion
      statement: >-
        归档摘要为 @@ARCHIVE_SHA256@@；归档内清单的 @@MANIFEST_FILE_COUNT@@ 条逐文件摘要
        与 @@CHECKSUM_SIDECAR_NAME@@ 在解包树上全部复算一致；归档 @@ZIP_ENTRY_COUNT@@ 个条目
        的时间戳全为 1980-01-01。本实例的生成器在每次生成前重做这组复算。
      existence: {engineering_object: present, record: context-only, managed: false}
      address: {subject: SUBJ-OSH-ARTIFACT, stage: verification}
      verification_evidence:
        evidence_kind: verification
        subject: SUBJ-OSH-ARTIFACT
        requirement: [REQ-OSH-CONTENT, REQ-OSH-REPRO]
        criterion_ref: CRIT-OSH-CONTENT
        verified_configuration: BAS-OSH-1.3.0
        method: digest-and-manifest-check
        capability: content-integrity-check
        run: RUN-OSH-CHECK
        result: pass
      provenance: {produced_by: N4, method: digest-and-manifest-check, capability: content-integrity-check, tool: sha256sum, run: RUN-OSH-CHECK}
      note: {text: "对照判据：计划外路径 0、黑名单命中 0。证据强度在于它是结构性空集，不是一次抽样；生成器可独立复算（见 README 的权威来源）。"}

    - id: E-OSH-SELFCHECK
      kind: verification-evidence
      title:
        zh: 解包树整体启动自检结论
        en: Extract-and-run tree self-check conclusion
      statement: >-
        在 checkout 之外的目录解包，移除 PYTHONPATH、用系统解释器启动 stdio 服务：initialize 报出
        server 身份与运行时策略 revision，tools/list 可用，进程正常退出；全程零 Onshape 请求。
        这条证据只在验证记录里，本机不可复算（宿主侧事件）。
      existence: {engineering_object: present, record: context-only, managed: false}
      address: {subject: SUBJ-OSH-ARTIFACT, stage: integration}
      verification_evidence:
        evidence_kind: verification
        subject: SUBJ-OSH-ARTIFACT
        requirement: [REQ-OSH-SELFCHECK]
        criterion_ref: CRIT-OSH-SELFCHECK
        verified_configuration: BAS-OSH-1.3.0
        method: extract-and-run-selfcheck
        capability: package-integration-check
        run: RUN-OSH-SELFCHECK
        result: pass
      provenance: {produced_by: N5, method: extract-and-run-selfcheck, capability: package-integration-check, tool: python-stdio-smoke, run: RUN-OSH-SELFCHECK}
      note: {text: "它同时回答两件事：各模块组合成一个可安装整体（Integration），以及安装自检不联系 Onshape（REQ-OSH-SELFCHECK）。"}

    - id: E-OSH-DOWNLOADBACK
      kind: verification-evidence
      title:
        zh: 已发布对象的下载回流复核结论
        en: Download-back verification of the published object
      statement: >-
        用 gh release download 把已发布资产下载到 checkout 之外，sha256sum -c 与本地构建一致，
        下载回来的归档解包后内层 @@MANIFEST_FILE_COUNT@@ 条摘要全部成功。本实例交付前的现场复核
        结果见 README 的原始输出。
      existence: {engineering_object: present, record: context-only, managed: false}
      address: {subject: SUBJ-OSH-ARTIFACT, stage: verification}
      verification_evidence:
        evidence_kind: verification
        subject: SUBJ-OSH-ARTIFACT
        requirement: [REQ-OSH-CONTENT]
        criterion_ref: CRIT-OSH-CONTENT
        verified_configuration: BAS-OSH-1.3.0
        method: download-back-verification
        capability: content-integrity-check
        run: RUN-OSH-DOWNLOADBACK
        result: pass
      provenance: {produced_by: N7, method: download-back-verification, capability: content-integrity-check, tool: gh-release, run: RUN-OSH-DOWNLOADBACK}
      note: {text: "这条证据在 Stage 上属于 verification，但时间上发生在 transition-to-use 之后：EWF 的 maturity 是语义轴而不是排程（EWF-LC-003），因此允许这种非单调顺序。"}

    - id: E-OSH-HOST
      kind: verification-evidence
      title:
        zh: 宿主就地刷新的 Validation 结论
        en: Validation conclusion of the host in-place refresh
      statement: >-
        刷新到 @@REVISION@@：dry-run 计划写入全部是产物条目、无状态路径；应用后产物内容逐文件
        等值，保留状态文件的内容与 mtime 不变，桥代次递进且客户端被保留；运行时几何后端选择
        不变。这条证据的原始记录在验证记录里，本机不可复算（Windows 宿主侧事件）。
      existence: {engineering_object: present, record: context-only, managed: false}
      address: {subject: SUBJ-OSH-HOST, stage: validation}
      verification_evidence:
        evidence_kind: validation
        subject: SUBJ-OSH-HOST
        requirement: [REQ-OSH-STATE]
        criterion_ref: CRIT-OSH-STATE
        validates_need: NEED-OSH-RELEASE
        verified_configuration: BAS-OSH-1.3.0
        method: host-runtime-observation
        capability: runtime-acceptance-observation
        run: RUN-OSH-ACCEPT
        result: pass
      provenance: {produced_by: N9, method: host-runtime-observation, capability: runtime-acceptance-observation, tool: onshape-mcp-tools, run: RUN-OSH-ACCEPT}
      note: {text: "Validation 回答「是否真的满足原始 Need」：刷新没有让宿主付出第二次登录与配额代价。它与 E-OSH-INTEGRITY 的区别正是 EWF-ENT-006 要求区分的那件事——一个对照 Requirement，一个对照原始 Need。"}

    - id: DEF-OSH-GEOMBACKEND
      kind: defect-issue
      title:
        zh: 产物携带机器本地状态导致解包即关闭几何后端
        en: The artifact carried machine-local state, so extracting it silently disabled the geometry backend
      statement: >-
        几何后端选择文件是机器本地状态（provider / executable / 参数模板 / 容差），却被作为 tracked
        文件打进产物；一次普通解包就把真实宿主上已启用的后端换成 shipped 的禁用默认。
      existence: {engineering_object: present, record: external-reference, managed: false}
      address: {subject: SUBJ-OSH-ARTIFACT, stage: implementation-realization}
      external_ref: {system: git, external_id: git-onshapescript, external_kind: repository, ownership: external, role: reference, sync_policy: reference-only, imported_history: false}
      defect_issue:
        symptom: 权威宿主实测已启用后端，而产物携带的是禁用默认
        severity: high
        root_cause: 把「机器本地状态」误分类为「版本化内容」；正确处置是移入黑名单，并让每个模式只随产物分发禁用模板
        discovered_in_stage: implementation-realization
      note: {text: "记录由仓库自身的文档与验证记录持有，因此 external_ref 指向仓库而不是缺陷库。修复后刷新用 mtime 反证状态未被触碰（产物条目固定 1980 时间戳）。"}

    - id: DEF-OSH-EXCLUDED
      kind: defect-issue
      title:
        zh: 清单发布的保留集合是「恰好存在」子集
        en: The manifest published a checkout-dependent preserve list
      statement: >-
        清单的 excludedPaths 一度发布的是黑名单里「构建 checkout 中恰好存在」的条目；产物在一台
        机器构建、在另一台机器安装，于是操作者用来决定「升级要携带什么」的字段恰好漏掉了本次停止
        分发的两个几何选择文件。修复后清单发布完整 @@DENYLIST_COUNT@@ 项黑名单。
      existence: {engineering_object: present, record: external-reference, managed: false}
      address: {subject: SUBJ-OSH-ARTIFACT, stage: verification}
      external_ref: {system: git, external_id: git-onshapescript, external_kind: repository, ownership: external, role: reference, sync_policy: reference-only, imported_history: false}
      defect_issue:
        symptom: 第一次重发后才发现同一升级路径上的第二个洞：保留清单与升级携带步骤都不含这两个文件
        severity: high
        root_cause: 用 checkout 观测结果冒充主机无关的契约；黑名单是契约，checkout 子集只是观测
        discovered_in_stage: verification
      note: {text: "修复把两个清单写出方都改为发布完整黑名单并加了字段说明。本实例的生成器每次都会复算这项：manifest.excludedPaths 的条数必须等于发布工具 DENYLIST 的条数。"}

    - id: DEF-OSH-NOTES
      kind: defect-issue
      title:
        zh: 人类可读的发行说明仍发布保留集合的子集
        en: The human-readable release notes still publish a subset of the preserve list
      statement: >-
        归档内 RELEASE-NOTES.md 的「Preserved state」小节列的是构建 checkout 中恰好存在的
        @@NOTES_PRESERVE_COUNT@@ 条，而 release-manifest.json 的 excludedPaths 是完整的
        @@DENYLIST_COUNT@@ 项；两者相差 @@NOTES_MISSING_COUNT@@ 条，恰好是构建机上不存在的状态
        路径：@@NOTES_MISSING_LIST@@。其中两项正是上一轮缺陷的主角（几何后端选择文件）。
      existence: {engineering_object: present, record: context-only, managed: false}
      address: {subject: SUBJ-OSH-ARTIFACT, stage: verification}
      external_ref: {system: git, external_id: git-onshapescript, external_kind: repository, ownership: external, role: reference, sync_policy: reference-only, imported_history: false}
      defect_issue:
        symptom: 同一份归档里，「升级必须保留什么」有两个互相不一致的人 / 机可读答案
        severity: medium
        root_cause: 清单写出方在上一轮修复里改成发布完整黑名单，而发行说明的写出方仍用「本 checkout 观测到的子集」
        discovered_in_stage: verification
      note: {text: "这是本实例的生成器在复算时发现的：它不写死数字，而是比对归档内两份文件后算出差集。因为 EWF 不是那个发行说明的写出方，这条不改 EWF，只回给项目侧。"}

    - id: MEA-OSH-ARCHIVE-BYTES
      kind: measurement
      title:
        zh: 已发布归档的字节数
        en: Byte size of the published archive
      statement: 已发布归档 @@ARCHIVE_NAME@@ 的字节数为 @@ARCHIVE_BYTES@@（sha256 @@ARCHIVE_SHA256@@）。
      existence: {engineering_object: present, record: context-only, managed: false}
      address: {subject: SUBJ-OSH-ARTIFACT, stage: verification}
      measurement:
        quantity: archive-bytes
        value: "@@ARCHIVE_BYTES@@"
        unit: byte
        method: digest-and-manifest-check
        tool: sha256sum
      note: {text: "measurement 是 candidate Entity（OQ-003 相邻问题）。把它单独记下来是因为字节数是发布复核里唯一需要与远端比对的量化读数；本机可用 stat -c %s 复算。"}

  relations:
    - id: IF-OSH-DELIVERY
      kind: interface
      name:
        zh: 产物 ↔ 消费者安装树交付接口
        en: Artifact-to-install-tree delivery interface
      endpoints:
        - {ref: ART-OSH-ARCHIVE, role: delivered-package}
        - {ref: SUBJ-OSH-HOST, role: install-root}
      contract:
        - {domain: process, statement: 解包到空目录，归档根即安装根；升级解包到新目录并携带状态，或就地把版本化代码替换掉}
        - {domain: data, statement: 产物只包含版本化代码；可变状态由宿主按黑名单在相对路径上携带前行，既不在产物内，也不被刷新写入或删除}
        - {domain: process, statement: 产物与状态可用时间戳判别：可复现归档的每个条目固定 1980 时间戳，状态文件保留真实 mtime}
      requirements: [REQ-OSH-STATE]
      persistent: false
      note: {text: "Interface 是 Engineering Relation 而不是 Artifact（EWF-REL-001）；本次没有接口契约变更传播问题（OQ-009 不触发）。"}

    - id: REL-OSH-DERIVE
      kind: derivation
      name:
        zh: 归档由源码树构建而来
        en: The archive is derived from the source tree
      endpoints:
        - {ref: ART-OSH-SRC, role: source-tree}
        - {ref: ART-OSH-ARCHIVE, role: derived-artifact}
      persistent: false
      note: {text: "发布链上出现过的更早 revision 没有本地残留产物，只有摘要记录在验证记录里；本条只声明被发布的那一次派生关系。"}

    - id: REL-OSH-VERIFY
      kind: verification-link
      name:
        zh: 产物与验证证据的语义链接
        en: Semantic links between the artifact and its verification evidence
      endpoints:
        - {ref: ART-OSH-ARCHIVE, role: verified-object}
        - {ref: E-OSH-INTEGRITY, role: evidence}
        - {ref: E-OSH-DOWNLOADBACK, role: evidence}
      persistent: false
      note: {text: "这些链接在语义上存在，但本实例用 TLR-OSH-06 解除了全局追溯义务：追溯矩阵由仓库自身持有（docs/verification/MATRIX.md），EWF 不复制第二份。"}

  gates:
    - id: GATE-OSH-PUBLISH
      name:
        zh: 发布门
        en: Publication gate
      placement: release-workflow
      applies_to: {stages: [transition-to-use], workflow: WF-OSH-PUBLISH, subjects: [SUBJ-OSH-ARTIFACT], release: RLS-OSH-1.3.0}
      criteria:
        - {id: GC-OSH-DIGEST, kind: evidence-available, description: "本地构建的归档摘要与逐文件清单已核验（对照 CRIT-OSH-CONTENT / CRIT-OSH-REPRO）", refs: [E-OSH-INTEGRITY, ART-OSH-ARCHIVE]}
        - {id: GC-OSH-CONFIG, kind: entity-condition, description: "被发布的配置已由 Baseline 标识（sourceRevision + 逐文件摘要清单）", refs: [BAS-OSH-1.3.0]}
        - {id: GC-OSH-REVISION, kind: state-condition, description: "revision 是已提交、干净的工作树（-dirty 的构建 MUST NOT 被发布）", refs: [ART-OSH-SRC]}
        - {id: GC-OSH-SIGN, kind: state-condition, description: "产物未签名且清单记录 signed:false；是否签名被显式保留为未决，而不是默认假设"}
      formality: formal-approval
      tailored: false
      note: {text: "Gate 只消费已声明的 criterion 与 evidence，自身不是 Stage、也不是执行节点（EWF-GATE-001）。发布是唯一写外部系统的一步，因此门保持最高正式度；下载回流是发布之后的独立复核节点，不是这道门的条件。"}

    - id: GATE-OSH-REFRESH
      name:
        zh: 宿主就地刷新门
        en: Host in-place refresh gate
      placement: within-stage
      applies_to: {stages: [transition-to-use], workflow: WF-OSH-PUBLISH, subjects: [SUBJ-OSH-HOST], release: RLS-OSH-1.3.0}
      criteria:
        - {id: GC-OSH-ALLOWLIST, kind: entity-condition, description: "dry-run 计划写入集合必须恰好等于被审查过的产物条目集合；出现任何未列路径即在写第一字节之前中止", refs: [ART-OSH-MANIFEST]}
        - {id: GC-OSH-STATE, kind: state-condition, description: "刷新后保留状态文件的内容与 mtime 不变", refs: [E-OSH-HOST]}
      formality: self-check
      tailored: true
      note: {text: "其正式度由 TLR-OSH-05 从 formal-approval 降到 self-check（EWF-GATE-003）。"}

  traceability:
    required: false
    scope: []
    note: {text: "TLR-OSH-06 解除了追溯义务（EWF-EXT-001）。这里有一个边界上的循环：本实例的主体之一就是那份持有记录的仓库本身，于是「外部系统」与「被管理的工程对象」指向同一处。"}

  external_refs:
    - {system: git, external_id: git-onshapescript, external_kind: repository, ownership: external, role: source, sync_policy: reference-only, imported_history: false}
    - {system: custom, system_name: github-releases, external_id: github-release-v1-3-0, external_kind: release, ownership: external, role: sink, sync_policy: manual, imported_history: false}
    - {system: custom, system_name: filesystem, external_id: fs-onshapescript-releases, external_kind: artifact-directory, ownership: external, role: reference, sync_policy: reference-only, imported_history: false}
    - {system: custom, system_name: windows-filesystem, external_id: fs-windows-install, external_kind: install-tree, ownership: external, role: sink, sync_policy: manual, imported_history: false}

  execution:
    id: EX-OSH-RELEASE
    label:
      zh: Release 1.3.0 发布与宿主对齐的执行视图
      en: Execution view of the 1.3.0 release and host alignment
    nodes:
      - id: N1
        kind: decision
        label: {zh: 固化产物内容契约, en: Fix the artifact content contract}
        address: {subject: SUBJ-OSH-TOOLING, stage: requirements-definition, work_node: plan, workflow: WF-OSH-PUBLISH}
        intent: requirements
        method: release-content-contract
        capability: release-plan-derivation
        tool: consumer-release-spec
        executor: {type: agent, role: maintainer}
        status: done
        run: {id: RUN-OSH-CONTRACT, run_kind: other, status: completed, produces: []}
        creates_task_record: false
        note:
          text: >-
            把「产物必须包含什么」写成可执行的不变量（白名单 / 黑名单 / plan() / validate()），
            使 RELEASE.md 保持为可派生投影（EWF-DOC-003）。产出是 REQ-OSH-CONTENT / REQ-OSH-REPRO /
            REQ-OSH-SELFCHECK / REQ-OSH-STATE 四条语义，它们不形成受管 Requirement Record
            （TLR-OSH-03、EWF-ENT-002）。
      - id: N2
        kind: decision
        label: {zh: 决定格式 / 渠道 / 签名, en: "Decide format, channel and signing"}
        address: {subject: SUBJ-OSH-ARTIFACT, stage: design, work_node: decide, workflow: WF-OSH-PUBLISH}
        intent: design
        method: release-policy-tradeoff
        capability: release-policy-judgment
        executor: {type: agent, role: maintainer}
        status: done
        run: {id: RUN-OSH-DECIDE, run_kind: other, status: completed, produces: []}
        creates_task_record: false
        note:
          text: >-
            三个取舍分别记录在 DEC-OSH-FORMAT / DEC-OSH-CHANNEL / DEC-OSH-SIGNING。本节点 MUST NOT
            为它们创建 Change Record（EWF-ENT-004）。
      - id: N3
        kind: run
        label: {zh: 构建可复现归档与清单, en: Build the reproducible archive and manifest}
        address: {subject: SUBJ-OSH-ARTIFACT, stage: implementation-realization, work_node: build, workflow: WF-OSH-BUILD, collapsed_from: [WF-OSH-BUILD, WFBUILD-PLAN, WFBUILD-ZIP, WFBUILD-MANIFEST]}
        intent: realization
        method: reproducible-archive-build
        capability: deterministic-packaging
        tool: build-release
        executor: {type: automation, role: build}
        status: done
        run: {id: RUN-OSH-BUILD, run_kind: build, status: completed, produces: [ART-OSH-ARCHIVE, ART-OSH-MANIFEST]}
        creates_task_record: false
        note:
          text: >-
            构建层经 COLLAPSE_LEVEL（TLR-OSH-02）折叠为一次 build_release.py。节点语义地址仍是
            (SUBJ-OSH-ARTIFACT × implementation-realization × build)，折叠没有取消可解释性
            （EWF-EXE-001、EWF-TLR-003）。同一次调用还写出外层 .sha256。
      - id: N4
        kind: run
        label: {zh: 离线完整性与清单校验, en: Offline integrity and manifest check}
        address: {subject: SUBJ-OSH-ARTIFACT, stage: verification, work_node: inspect, workflow: WF-OSH-PUBLISH}
        intent: verification
        method: digest-and-manifest-check
        capability: content-integrity-check
        tool: sha256sum
        executor: {type: automation, role: release}
        status: done
        run: {id: RUN-OSH-CHECK, run_kind: inspection, status: completed, produces: [E-OSH-INTEGRITY]}
        creates_task_record: false
        note:
          text: >-
            对照 CRIT-OSH-CONTENT / CRIT-OSH-REPRO：计划外路径 0、黑名单命中 0、逐文件摘要
            @@MANIFEST_FILE_COUNT@@ 条一致。上面两条真实的 when: fail 回边就是在这条链上或它的
            下游被触发的。
      - id: N5
        kind: run
        label: {zh: 解包树整体启动自检, en: Extract-and-run self-check}
        address: {subject: SUBJ-OSH-ARTIFACT, stage: integration, work_node: integrate, workflow: WF-OSH-PUBLISH}
        intent: integration
        method: extract-and-run-selfcheck
        capability: package-integration-check
        tool: python-stdio-smoke
        executor: {type: automation, role: release}
        status: done
        run: {id: RUN-OSH-SELFCHECK, run_kind: test, status: completed, produces: [E-OSH-SELFCHECK]}
        creates_task_record: false
        note:
          text: >-
            在 checkout 之外解包，移除 PYTHONPATH、用系统解释器起 stdio，确认模块目录组合成一个
            可安装整体，并同时满足 REQ-OSH-SELFCHECK（零 Onshape 请求）。
      - id: N6
        kind: run
        label: {zh: 发布 GitHub Release v1.3.0, en: Publish GitHub Release v1.3.0}
        address: {subject: SUBJ-OSH-ARTIFACT, stage: transition-to-use, work_node: transition, workflow: WF-OSH-PUBLISH}
        intent: transition
        method: release-publication
        capability: artifact-distribution
        tool: gh-release
        executor: {type: agent, role: operator}
        status: done
        run: {id: RUN-OSH-PUBLISH, run_kind: transition, status: completed, produces: [RLS-OSH-1.3.0]}
        creates_task_record: false
        note:
          text: >-
            annotated tag v1.3.0 → @@REVISION@@；资产恰好是归档与 .sha256 边车，Release body 取归档内
            RELEASE-NOTES.md。这是唯一写外部系统的一步，由 GATE-OSH-PUBLISH（formal-approval）把关；
            构建器本身仍然什么都不上传。
      - id: N7
        kind: run
        label: {zh: 下载回流复核, en: Download-back re-verification}
        address: {subject: SUBJ-OSH-ARTIFACT, stage: verification, work_node: inspect, workflow: WF-OSH-PUBLISH}
        intent: verification
        method: download-back-verification
        capability: content-integrity-check
        tool: gh-release
        executor: {type: automation, role: release}
        status: done
        run: {id: RUN-OSH-DOWNLOADBACK, run_kind: test, status: completed, produces: [E-OSH-DOWNLOADBACK]}
        creates_task_record: false
        note:
          text: >-
            以「下载回流」代替「信任上传结果」：下载到 checkout 之外，sha256sum -c 后与本地构建比对。
            这条节点在 Stage 上是 verification、在时间上位于 transition 之后——EWF 允许这种非单调
            顺序（EWF-LC-003），但规范没有为它提供任何排程语义。
      - id: N8
        kind: tool-invocation
        label: {zh: 宿主就地代码刷新, en: In-place host code refresh}
        address: {subject: SUBJ-OSH-HOST, stage: transition-to-use, work_node: transition, workflow: WF-OSH-PUBLISH}
        intent: transition
        method: in-place-code-refresh
        capability: deployed-code-replacement
        tool: rsync
        executor: {type: human, role: operator}
        status: done
        run: {id: RUN-OSH-REFRESH, run_kind: transition, status: completed, produces: []}
        creates_task_record: false
        note:
          text: >-
            dry-run 的计划集合必须恰好等于被审查过的产物条目集合，出现未列路径即在写第一字节之前
            中止；对照 GATE-OSH-REFRESH。恢复点是本次将被覆盖文件的 tar + 摘要。
      - id: N9
        kind: run
        label: {zh: 宿主运行时验收, en: Host runtime acceptance}
        address: {subject: SUBJ-OSH-HOST, stage: validation, work_node: observe, workflow: WF-OSH-PUBLISH}
        intent: validation
        method: host-runtime-observation
        capability: runtime-acceptance-observation
        tool: onshape-mcp-tools
        executor: {type: human, role: operator}
        status: done
        run: {id: RUN-OSH-ACCEPT, run_kind: validation, status: completed, produces: [E-OSH-HOST]}
        creates_task_record: false
        note:
          text: >-
            刷新后核对：产物逐文件等值、保留状态文件内容与 mtime 不变、桥代次递进且客户端被保留、
            几何后端 configured / ready 且选择不变。这条证据只在验证记录里，本机不可复算。
    edges:
      - {from: N1, to: N2, kind: sequence, when: always}
      - {from: N2, to: N3, kind: sequence, when: always}
      - {from: N3, to: N4, kind: sequence, when: always}
      - {from: N4, to: N5, kind: sequence, when: pass}
      - {from: N5, to: N6, kind: sequence, when: pass}
      - {from: N6, to: N7, kind: sequence, when: always}
      - {from: N7, to: N8, kind: sequence, when: pass}
      - {from: N8, to: N9, kind: sequence, when: always}
      - {from: N4, to: N1, kind: reentry, when: fail, label: {zh: 内容契约本身不成立, en: The content contract itself is wrong}}
      - {from: N4, to: N3, kind: reentry, when: fail, label: {zh: 契约成立但构建结果不合格, en: Contract holds but the build output fails}}
      - {from: N7, to: N3, kind: reentry, when: fail, label: {zh: 已发布对象与本地构建不一致, en: The published object differs from the local build}}
      - {from: N9, to: N3, kind: reentry, when: fail, label: {zh: 宿主验收失败则重新构建重发, en: Rebuild and re-release when host acceptance fails}}
    runs:
      - {id: RUN-OSH-CONTRACT, run_kind: other, status: completed, produces: []}
      - {id: RUN-OSH-DECIDE, run_kind: other, status: completed, produces: []}
      - {id: RUN-OSH-BUILD, run_kind: build, status: completed, produces: [ART-OSH-ARCHIVE, ART-OSH-MANIFEST]}
      - {id: RUN-OSH-CHECK, run_kind: inspection, status: completed, produces: [E-OSH-INTEGRITY]}
      - {id: RUN-OSH-SELFCHECK, run_kind: test, status: completed, produces: [E-OSH-SELFCHECK]}
      - {id: RUN-OSH-PUBLISH, run_kind: transition, status: completed, produces: [RLS-OSH-1.3.0]}
      - {id: RUN-OSH-DOWNLOADBACK, run_kind: test, status: completed, produces: [E-OSH-DOWNLOADBACK]}
      - {id: RUN-OSH-REFRESH, run_kind: transition, status: completed, produces: []}
      - {id: RUN-OSH-ACCEPT, run_kind: validation, status: completed, produces: [E-OSH-HOST]}
    entry_nodes: [N1]
    terminal_nodes: [N9]
    execution_view_note: >-
      本执行视图是 WF-OSH-PUBLISH 的 9 节点投影：契约 → 取舍 → 构建 → 离线校验 → 启动自检 →
      发布 → 下载回流 → 宿主刷新 → 运行时验收；FAIL 用 kind: reentry / when: fail 回到 requirements
      或 implementation-realization。三处必须点名的投影损失：(1) 排序是**语义顺序**而不是时间顺序——
      真实时间线里三次重新发布（c10a235 / 681a4cd / e667bcc / 31d2b9c 一路到 @@REVISION@@）与宿主
      工作交错发生，EWF 没有表达交错的机制。(2) 那些重新发布是「同一条回边被走过多次」，但 EWF 既
      不能记录次数，也不能给没有节点的 run 一个语义地址（见 README 的绕行条目）。(3) RUN-OSH-BUILD
      一次调用内部写出归档 / 清单 / 边车 / 发行说明，被折叠的 WF-OSH-BUILD 没有自己的执行节点。
      runs[] 与节点内联的 run 由生成器从同一份数据渲染，因此 EWF-EXE-007 / EWF-EXE-009 的一致性
      在这里是构造保证，而不是靠人核对。

  open_questions: [OQ-011, OQ-015, OQ-016, OQ-017, OQ-020, OQ-022, OQ-026]

  note:
    text: >-
      本实例由 dev/tools/build_ewf_instance.py 生成，不是手写；生成器另提供 --check（重新渲染并与本文件
      逐字节比较），使「实例与源数据脱节」可以被一条命令发现。本实例**不使用** x-* 扩展键：我们
      确实有 EWF 无处安放的机器可读事实（产物格式、签名状态、完整黑名单、逐文件摘要），但它们各自
      另有一个更合适的落点（产物自己的 manifest / baseline 的 configuration 项 / 本目录的
      FEEDBACK.md），而私有键对不共享我们约定的消费者不可读——把缺口写进 FEEDBACK 比造一个只有
      我们认识的键更有用。

      本实例有 4 条项目自有待定项。它们不给编号：OQ- 是 EWF 的全局命名空间，项目侧 MUST NOT
      自造，而项目自己的待定项今天没有机器可读位置（走 FEEDBACK 的 onshapescript-FB-02）。
      用纯序号列在这里，逐条说明与判据见 ewf/README.md 的「项目本地的待定项（无编号）」一节：
      1) 随产物再分发的上游语料与内置 wheel 的许可与再分发边界；
      2) 产物的留存、处置与可得性（验证记录点名的构建 revision 与本地保留的归档不是同一批）；
      3) 发行说明的保留集合与 release-manifest.json 的黑名单不一致（本实例记为 DEF-OSH-NOTES）；
      4) 是否跟随 spec 0.6.1（本实例在 0.6.1 的 schema 下通过校验，但仍声明 0.6.0）。

      判断过程与每一处绕行见 ewf/README.md。
"""


def render(facts: dict) -> str:
    text = TEMPLATE
    for key, value in facts.items():
        text = text.replace(f"@@{key}@@", str(value))
    if "@@" in text:
        raise Gap("模板里仍有未替换的 token：" + text[text.index("@@") : text.index("@@") + 80])
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="从真实发布数据生成 EWF 项目实例（ewf/instance.yaml）。"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="写出 ewf/instance.yaml")
    mode.add_argument("--check", action="store_true", help="重新渲染并与 ewf/instance.yaml 比较")
    mode.add_argument(
        "--facts",
        action="store_true",
        help="打印本次采集并复算出的全部事实（JSON），不写文件",
    )
    args = parser.parse_args(argv)

    try:
        facts = collect()
        rendered = render(facts)
    except Gap as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1

    if args.facts:
        print(json.dumps(facts, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    if args.write:
        INSTANCE_PATH.write_text(rendered, encoding="utf-8")
        print(
            f"wrote {INSTANCE_PATH} "
            f"({len(rendered.splitlines())} 行；源归档 {facts['ARCHIVE_NAME']} "
            f"sha256 {facts['ARCHIVE_SHA256'][:12]}…)"
        )
        return 0

    if args.check:
        if not INSTANCE_PATH.is_file():
            print(f"refused: {INSTANCE_PATH} 不存在", file=sys.stderr)
            return 1
        current = INSTANCE_PATH.read_text(encoding="utf-8")
        if current.rstrip("\n") != rendered.rstrip("\n"):
            print(
                "FAIL: ewf/instance.yaml 与生成结果不一致（重跑 --write 前先确认源数据变化）",
                file=sys.stderr,
            )
            return 1
        print("OK: ewf/instance.yaml 与生成结果一致")
        return 0

    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
