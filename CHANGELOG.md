# 变更记录

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## v0.1.0 — 首个可用版本

### 新增

* **解压引擎接入**：使用 erofs-utils 1.8.10 的 Cygwin x86_64 构建（`fsck.erofs.exe`），
  Windows 原生运行，**不依赖 WSL / 虚拟机 / 管理员权限 / 任何安装**。
* **图形界面**（`imgtool/gui.py`）：tkinter 界面，支持一次拖入多个文件或整个文件夹，
  默认"拖进来自动解压"；后台线程解压、可取消；进度按 inode 数估算；带日志面板与任务表。
* **原生拖放**（`imgtool/dnd.py`）：纯 ctypes 实现 `WM_DROPFILES` + 子类化窗口过程，
  零第三方依赖；附带 `post_drop()` 用于自动化测试拖放链路。
* **核心解压流程**（`imgtool/core.py`）：
  * 格式识别：EROFS / Android sparse / ext4 / f2fs / squashfs / cramfs / Android boot /
    gzip / xz / zip / bzip2 / super.img
  * 自动扫描 EROFS 超级块偏移（前 64 MB，512 对齐校验），支持非 0 偏移镜像
  * 输出目录策略：`auto`（自动加序号）/ `overwrite`（删除后重建）
  * 进度轮询、取消、日志实时回传
  * 失败信息映射为中文提示
* **Android sparse 支持**（`imgtool/sparse.py`）：识别 `0xED26FF3A`，流式展开
  raw / fill / don't care / crc32 四种 chunk，展开后自动清理临时文件；含反向打包（测试用）。
* **符号链接还原**：三级降级 —— 真 Windows 符号链接 → 目录联接（`mklink /J`，免权限）→
  保留 `!<symlink>` 目标文件并写出 `_imgtool_symlinks.txt` 清单。
  关键前提是给引擎设置 `CYGWIN=winsymlinks:sys`，避免 Cygwin 默认写出
  Windows 读不了的 WSL `LX_SYMLINK` 重解析点。
* **硬链接还原**：镜像里的硬链接在 NTFS 上还原为真硬链接（共享 inode）。
* **安全删除**：`safe_rmtree()` 识别重解析点，绝不跟进目录联接删别人的数据。
* **命令行**（`imgtool/cli.py`）：`--info / -o / --policy / --symlinks / --offset /
  --keep-temp / --version`。
* **启动器**：`1-启动解压工具.bat`（自动定位 pythonw）、`2-拖放解压.cmd`（拖到图标即解压）、
  `3-制作测试镜像.bat`。全部纯 ASCII + CRLF 行尾。
* **测试镜像生成**（`tests/make_fixtures.py`）：用 `tarfile` 构造含中文名、空格名、符号链接
  （相对/绝对/悬空/指向目录）、硬链接、只读/私有权限、空目录、设备节点的 tar，
  再经 `mkfs.erofs --tar` 压成 11 种布局的 EROFS 镜像。
* **端到端测试**（`tests/e2e_test.py`）：45 项断言，覆盖压缩算法矩阵、默认输出目录、
  冲突策略、符号链接三种模式、sparse、偏移、中文路径、错误处理、取消、设备节点。
* **GUI 与启动器测试**（`tests/gui_test.py`、`tests/launcher_test.ps1`）。
* **演示镜像生成**（`tests/make_demo_img.py`）：产出 `示例镜像\` 下 3 个可直接拖拽的镜像
  与人工验收清单。
* **文档**：README（含"从零复现本工程"完整指南与 11 条踩坑记录）、LICENSE（0BSD）、
  THIRD_PARTY_NOTICES、CHANGELOG、.gitignore、.gitattributes，
  以及文档自检脚本 `tools/check_docs.py`（校验锚点、相对链接与提到的文件是否存在）。
* **许可证合规**：
  * `LICENSE` 按组件区分写清楚 —— 本项目代码 `0BSD`；
    `engine/` 二进制分别为 `GPL-2.0-or-later` 和 `LGPL-3.0-or-later`（含 Cygwin 链接例外）；
    并说明为何 0BSD 能与 GPL 二进制聚合分发、分发者需要履行哪些义务；
  * 新增 `LICENSES/` 目录，随附 GPL-2.0 / GPL-3.0 / LGPL-3.0 许可证全文
    （`tools/fetch_licenses.py` 可重新获取）；
  * `THIRD_PARTY_NOTICES.md` 补全到 tag/commit 级的源码获取点与"发布前逐项检查"清单；
  * `engine/README.md` 补全这套 exe 的完整构建链路：上游 erofs-utils 源码 →
    第三方构建工程（CMake 目标定义、静态链接库清单、Cygwin 兼容补丁）→
    `build_cygwin.sh`（`x86_64-pc-cygwin-clang`）→ GitHub Actions 上的交叉编译 →
    Release 资产 → 本项目的取用方式；并修正了原先"fragments / 元数据压缩已实测"
    的不实陈述（这两类本机造不出样本，属未实测）。
  * 新增 **`docs/ENGINE_PROVENANCE.md`**：把"这些 exe 是怎么来的"写成九个环节的详解
    （上游源码 / 构建工程与 11 个依赖的锁定提交 / CMake 目标原文 / 4 个 Cygwin 补丁内容 /
    构建脚本逐行解释 / CI 步骤 / 发布资产 / 本项目取用 / 运行期调用参数），
    外加版本校验值、三层自查方法、**从源码自己重编的三种方式**、8 条常见疑问与术语表。
  * README 与 `engine/README.md` 里那句概括改为**明确区分三方**：
    ① 官方上游 erofs-utils（kernel.org 主开发树 / GitHub 官方镜像）、
    ② 第三方构建工程 sekaiacg/erofs-tools（只打包、不写文件系统代码）、
    ③ 本项目 imgtool（只管下载与调用），并配"四步构建过程"说明。
    `engine/README.md` 相应收敛为摘要 + 指向详解文档，避免两份内容各自漂移。
  * `tools/check_docs.py` 升级：从只查 README 扩展为查全部 6 份文档
    （README / CHANGELOG / THIRD_PARTY_NOTICES / LICENSE / engine/README / docs/*.md），
    校验锚点、相对链接与正文提到的文件路径是否都存在。

### 已知限制

* 仅支持 EROFS（含 Android sparse 包装）；ext4/f2fs/squashfs 等只识别不解压。
* Cygwin 版 `mkfs.erofs` 无法生成 fragments / 元数据压缩 / chunk 化布局的镜像，
  因此这几类布局**没有实测**（解压端由上游 fsck.erofs 负责）。
* 设备节点 / FIFO 在 NTFS 上只能写成 `.lnk` 占位文件。
* 不支持选择性解压、不支持回打包（路线见 README 第 11 节）。
* 32 位 Python 未测试。

### 实测环境

Windows 11 (build 26100) · Python 3.8.3 (64-bit, Anaconda) · erofs-utils 1.8.10-gee46dd74
