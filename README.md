# imgtool · Windows 原生 EROFS/IMG 解压工具

**把 `.img` 拖进窗口，松手就解压到同目录下的同名文件夹。**

[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078d4.svg)](#21-运行要求)
[![Python](https://img.shields.io/badge/python-3.7%2B-3776ab.svg)](#21-运行要求)
[![Dependencies](https://img.shields.io/badge/dependencies-stdlib%20only-brightgreen.svg)](#5-目录结构)
[![Engine](https://img.shields.io/badge/engine-erofs--utils%201.8.10-orange.svg)](#43-为什么用-cygwin-版-fsckerofs)
[![License](https://img.shields.io/badge/license-0BSD%20%2B%20GPL--2.0--or--later%20engine-blue.svg)](#12-许可证与第三方组件)

> **English abstract** — `imgtool` is a Windows-native extractor for EROFS images (Android
> `system.img` / `vendor.img` / `product.img`, ChromeOS partitions, …). It drives the **official
> `fsck.erofs`** from [erofs-utils](https://github.com/erofs/erofs-utils), cross-built for
> Windows/Cygwin, so it needs **no WSL, no VM, no admin rights and no installation** — just a
> `fsck.erofs.exe` plus `cygwin1.dll`. A tkinter GUI accepts real Explorer drag-and-drop
> (implemented with `WM_DROPFILES` through ctypes, zero third-party packages) and extracts every
> dropped image into a folder named after the image. It also normalises Android sparse images,
> auto-detects non-zero EROFS offsets, and restores symlinks / hardlinks on NTFS as faithfully as
> Windows allows. Verified by a 45-assertion end-to-end suite against self-built EROFS images.

---

## 目录

- [1 这是什么](#1-这是什么)
- [2 快速开始](#2-快速开始)
  - [2.1 运行要求](#21-运行要求)
  - [2.2 三种用法](#22-三种用法)
  - [2.3 界面说明](#23-界面说明)
- [3 支持矩阵](#3-支持矩阵)
- [4 工作原理](#4-工作原理)
  - [4.1 架构](#41-架构)
  - [4.2 解压流程](#42-解压流程)
  - [4.3 为什么用 Cygwin 版 fsck.erofs](#43-为什么用-cygwin-版-fsckerofs)
- [5 目录结构](#5-目录结构)
- [6 从零复现本工程](#6-从零复现本工程)
  - [6.1 准备引擎](#61-准备引擎)
  - [6.2 编写 sparse 模块](#62-编写-sparse-模块)
  - [6.3 编写 core 模块](#63-编写-core-模块)
  - [6.4 编写 dnd 模块](#64-编写-dnd-模块)
  - [6.5 编写 GUI 和 CLI](#65-编写-gui-和-cli)
  - [6.6 编写启动器](#66-编写启动器)
  - [6.7 构造测试镜像](#67-构造测试镜像)
  - [6.8 测试与验收](#68-测试与验收)
  - [6.9 复现自检清单](#69-复现自检清单)
- [7 踩坑记录](#7-踩坑记录)
- [8 测试](#8-测试)
  - [8.1 测试镜像里有什么](#81-测试镜像里有什么)
  - [8.2 怎么跑](#82-怎么跑)
  - [8.3 实测结果](#83-实测结果)
- [9 常见问题](#9-常见问题)
- [10 已知限制](#10-已知限制)
- [11 扩展路线](#11-扩展路线)
- [12 许可证与第三方组件](#12-许可证与第三方组件)
- [13 变更记录与致谢](#13-变更记录与致谢)

---

## 1 这是什么

一个给 Windows 用的 EROFS 镜像解压工具。核心诉求只有一句话：

> **把任意 `.img` 拖进来，就解压到该 IMG 同目录下的同名文件夹。**

`D:\rom\system.img` → `D:\rom\system\`

它**不是**重新实现的 EROFS 解析器，而是驱动 Linux 下那套官方 `fsck.erofs`
（[erofs-utils](https://github.com/erofs/erofs-utils) v1.8.10）的 Windows/Cygwin 构建。

### 特性一览

| 特性 | 说明 |
| --- | --- |
| 真·fsck.erofs | 解压引擎是上游 erofs-utils 原版代码编译出的 Windows 可执行文件 |
| 零安装 | 一个 `fsck.erofs.exe` + `cygwin1.dll` 就能跑，**不需要 WSL / 虚拟机 / 管理员权限** |
| 零 Python 依赖 | 只用标准库（`tkinter` / `ctypes` / `subprocess` / `struct` / `tarfile`） |
| 真·拖放 | `WM_DROPFILES` + 子类化窗口过程（纯 ctypes），不用 `tkinterdnd2` 之类第三方包 |
| 拖进即解压 | 默认勾选「拖进来就自动开始解压」，松手即开工 |
| 批量 | 一次拖多个镜像，后台线程排队解压，可随时取消 |
| Android sparse | 自动识别 `0xED26FF3A` 外壳并展开成 raw 再解压，用完清理临时文件 |
| 非 0 偏移 | 自动扫描 EROFS 超级块位置（例如被包在别的容器头之后） |
| 格式识别 | 认出 ext4 / f2fs / squashfs / cramfs / Android boot / super.img / zip / gzip / xz 并给人话提示 |
| 符号链接 | 三级降级：真链接 → 目录联接（免权限）→ 保留目标文件 + 清单 |
| 硬链接 | 还原成真正的 NTFS 硬链接（共享 inode） |
| 中文路径 | 镜像路径、输出路径、镜像内文件名都支持中文/空格 |
| 可验证 | 自造的 11 种布局测试镜像 + 45 项断言端到端测试，全部通过 |

---

## 2 快速开始

### 2.1 运行要求

| 项目 | 要求 | 说明 |
| --- | --- | --- |
| 操作系统 | Windows 10 / 11（实测 Windows 11 build 26100，64 位） | 需要 `cmd.exe`、`shell32.dll`、`user32.dll`，都是系统自带 |
| Python | 3.7 及以上（实测 3.8.3，64 位） | 需要 `tkinter`（Windows 官方安装包默认自带）；Anaconda 亦可 |
| 磁盘 | 解压镜像的 1~2 倍空间 | sparse 镜像需要同盘临时空间存放展开后的 raw |
| 权限 | **普通用户即可** | 想要"真符号链接"才需要开发者模式或管理员 |

引擎不依赖任何运行库安装——`cygwin1.dll` 就在 `engine\` 里，和 exe 放在一起。

### 2.2 三种用法

#### 用法一 图形界面（推荐）

双击 **`1-启动解压工具.bat`** → 把 `.img` 拖进窗口 → **松手就解压**。

* 输出：`示例镜像\system_demo.img` → `示例镜像\system_demo\`
* 也支持拖**文件夹**进来（自动找出里面所有 `.img`）
* 一次拖多个文件会排队处理；完成后自动打开输出目录（可关）

#### 用法二 拖到脚本上

把 `.img` 拖到 **`2-拖放解压.cmd`** 的图标上，弹出控制台边跑边打日志，结果同上。

#### 用法三 命令行

```bat
python imgtool_cli.py D:\rom\system.img                 :: 解压到 D:\rom\system\
python imgtool_cli.py -o D:\out\sys system.img          :: 指定输出目录
python imgtool_cli.py --info system.img                 :: 只看镜像信息，不解压
python imgtool_cli.py --policy overwrite *.img          :: 目录已存在就删掉重建
python imgtool_cli.py --symlinks copy system.img        :: 符号链接还原不了就复制目标内容
python imgtool_cli.py --symlinks keep system.img        :: 符号链接原样保留
python imgtool_cli.py --offset 4096 blob.bin            :: 手动指定超级块偏移
python imgtool_cli.py --keep-temp sparse.img            :: 保留 sparse 展开的临时 raw
python imgtool_cli.py --version                         :: 打印引擎版本与路径
```

`python imgtool_cli.py --help` 有完整参数表。

### 2.3 界面说明

```
┌──────────────────────────────────────────────────────────────────────┐
│ IMG 解压工具 · EROFS                       引擎：fsck.erofs 1.8.10…  │
├──────────────────────────────────────────────────────────────────────┤
│   ╭──────────────────────────────────────────────────────────────╮   │
│   │               把 IMG 文件拖到这里                             │   │
│   │  支持 .img / .bin / .erofs，Android sparse 镜像也行；         │   │
│   │  也可以拖一个文件夹进来          （点这里选文件）              │   │
│   ╰──────────────────────────────────────────────────────────────╯   │
│ 输出位置：(•) 镜像同目录·同名文件夹  ( ) 自定义目录 [______] [浏览]  │
│ 目录已存在：[自动改名（加序号）▾]        [x] 完成后打开输出目录      │
│ 符号链接：  [尽量还原成 Windows 链接 ▾]  [ ] 解压后同时列出符号链接清单│
│                                          [x] 拖进来就自动开始解压     │
├──────────────────────────────────────────────────────────────────────┤
│ 镜像文件          状态       输出目录                                │
│ system_demo.img   完成       D:\…\示例镜像\system_demo               │
├──────────────────────────────────────────────────────────────────────┤
│ [██████████████████░░░░] 就绪                                        │
│ 就绪：把 IMG 拖进来…                    [开始解压] [取消] [清空列表] │
├──────────────────────────────────────────────────────────────────────┤
│ 日志                                                                 │
│ [00:30:15] [加入] D:\…\system_demo.img（8.3 MB）                     │
│ [00:30:16]     类型：EROFS 镜像（块大小 4096，…）                     │
└──────────────────────────────────────────────────────────────────────┘
```

* 双击任务行 = 打开该镜像的输出目录
* 回车 = 开始解压
* 进度按「已解压条目数 / 镜像 inode 总数」估算（inode 数来自 `dump.erofs -s`）
* 输出目录已存在时，默认**自动加序号**（`system` → `system (2)`），不会覆盖任何东西

---

## 3 支持矩阵

### 输入

| 输入 | 结果 |
| --- | --- |
| 裸 EROFS `.img` | ✅ 解压（不压缩 / lz4 / lz4hc / lzma / deflate / zstd 均已实测） |
| Android sparse 包装的 EROFS | ✅ 自动展开成 raw 再解压，临时文件用后即删 |
| EROFS 位于非 0 偏移 | ✅ 前 64 MB 内扫描超级块（要求 512 对齐），命中后自动加 `--offset` |
| 镜像里的符号链接 | ✅ 三级降级还原（见 [4.2](#42-解压流程)） |
| 镜像里的硬链接 | ✅ NTFS 硬链接，共享 inode |
| 镜像里的设备节点 / FIFO | ⚠️ Windows 建不了字符设备，Cygwin 写成 `null.lnk` 占位文件，**解压不中断** |
| `ext4` / `f2fs` / `squashfs` / `cramfs` | ❌ 识别出来并提示"不是 EROFS" |
| `super.img` 动态分区（LP metadata） | ❌ 提示内含多个子分区，请先拆出单个分区 |
| zip / gzip / xz / bzip2 / Android boot | ❌ 识别出格式并提示 |

### 属性保真度（NTFS 的物理限制）

| 属性 | 保真度 |
| --- | --- |
| 文件内容 | **逐字节一致**（测试里逐文件比 SHA256） |
| 目录结构 / 空目录 / 空文件 | 完全一致 |
| 符号链接目标字符串 | 完全一致（相对、绝对、悬空都对） |
| 硬链接 | 完全一致（真硬链接） |
| 只读位（0444 等） | 映射成 NTFS 只读属性，近似一致 |
| 可执行位 | Cygwin 用自己的 ACL 方案模拟，Explorer 看不出来 |
| uid / gid / SELinux 标签 / capabilities | **丢失**（NTFS 没有 POSIX 属主） |
| mtime | 近似（Cygwin 写入） |

> 做 ROM 修改时，权限请以镜像里的 `fs_config` / `file_contexts` 为准，
> 需要这两个文件可以用 `engine\extract.erofs.exe`（本工具的接口里预留了，见 [11](#11-扩展路线)）。

---

## 4 工作原理

### 4.1 架构

```
                    ┌───────────────────────────────┐
   拖放 / 命令行 ──▶ │  1-启动解压工具.bat           │
                    │  2-拖放解压.cmd / imgtool_cli │
                    └───────────────┬───────────────┘
                                    ▼
                    ┌───────────────────────────────┐
                    │ imgtool\gui.py   （tkinter）   │
                    │ imgtool\cli.py   （argparse）  │
                    └───────────────┬───────────────┘
                                    ▼
      ┌──────────────────────────────────────────────────────────┐
      │ imgtool\core.py                                          │
      │   sniff()            识别格式 / 找 EROFS 偏移             │
      │   extract_image()    sparse 展开 → 调引擎 → 链接后处理     │
      │   fix_symlinks()     三级降级还原符号链接                  │
      │   safe_rmtree()      不跟进重解析点的安全删除              │
      └───────────┬──────────────────────────┬───────────────────┘
                  ▼                          ▼
      ┌──────────────────────┐   ┌──────────────────────────────┐
      │ imgtool\sparse.py    │   │ engine\fsck.erofs.exe        │
      │ Android sparse 读写  │   │ （erofs-utils 1.8.10 Cygwin）│
      └──────────────────────┘   │ engine\dump.erofs.exe        │
                                 │ engine\mkfs.erofs.exe        │
                                 │ engine\cygwin1.dll           │
                                 └──────────────────────────────┘
```

**关键约定：不重复造轮子。** EROFS 的解析、解压、校验全部交给上游 `fsck.erofs`；
本项目只负责"让它在 Windows 上跑得舒服"：识别镜像、准备输入、传对参数、处理
Windows 特有的符号链接/删除/路径问题、做界面和进度。

### 4.2 解压流程

```
extract_image(image, dest=None, policy="auto", symlinks="native")
  │
  ├─ 1. sniff(image)                      读文件头，判断类型
  │     ├ android-sparse → 记录展开后大小
  │     ├ erofs          → 记录超级块偏移 offset
  │     └ 其它           → 抛 ExtractError（带人话提示）
  │
  ├─ 2. resolve_dest()                    算输出目录
  │     auto      → 已存在则 "name (2)"、"name (3)" …
  │     overwrite → 用原目录，但先 safe_rmtree 删掉重建
  │
  ├─ 3. sparse → raw（仅当是 sparse）
  │     写到镜像同目录的临时文件 *.rawtmp，边写边报进度，可取消
  │
  ├─ 4. 调引擎（子进程，实时回传日志）
  │     fsck.erofs --extract=<输出目录> [--offset=N] -d2 <镜像>
  │     环境：CYGWIN=winsymlinks:sys  LC_ALL=C.UTF-8  PATH 前置 engine\
  │     进度：每 50 ms 统计一次输出目录（文件数 / 字节数）
  │     取消：轮询 cancel()，命中就 kill 进程
  │
  ├─ 5. fix_symlinks()                    符号链接后处理（见下）
  │
  └─ 6. 清理临时 raw（keep_temp=True 时保留），返回 ExtractResult
```

**符号链接三级降级**（`fix_symlinks`）：

| 顺序 | 手段 | 条件 | 结果 |
| --- | --- | --- | --- |
| 1 | `os.symlink()` | 开发者模式 / 管理员 | 真正的 Windows 符号链接 |
| 2 | `cmd /c mklink /J` | 目标存在且是目录，且同盘 | **目录联接（junction）**，普通用户可建 |
| 3 | 保留 Cygwin 链接文件 | 以上都不行 | 内容为 `!<symlink>目标`的小文件，文本编辑器可读；**并在输出根目录写 `_imgtool_symlinks.txt` 清单** |

第 3 步的关键前提是让 Cygwin **别**用默认的 WSL 重解析点方案（见 [7 踩坑记录](#7-踩坑记录) T1）：

```
环境变量 CYGWIN=winsymlinks:sys
  └─ 符号链接落盘为普通文件： "!<symlink>" + FF FE + 目标(UTF-16LE) + 00 00
```

### 4.3 为什么用 Cygwin 版 fsck.erofs

| 方案 | 结论 |
| --- | --- |
| WSL + 原生 erofs-utils | 要装 WSL（几百 MB + 重启），本项目明确不依赖 |
| MSVC / MinGW 源码移植 erofs-utils | 上游大量使用 Linux 专有头文件与接口，不是改几行能过的 |
| 自己实现 EROFS 解析器 | 要覆盖 lz4/lzma/deflate/zstd + 各种布局，正确性风险高，且背离"用 fsck.erofs" |
| 第三方 Windows 解包器 | 来历不明、不可控 |
| **Cygwin 构建（本方案）** | 上游原版代码，一个 exe + 一个 DLL，绿色免安装，行为与 Linux 版一致 |

Cygwin 是 Windows 上的 POSIX 兼容层（用户态 DLL），erofs-utils 在它上面编译几乎不用改代码。
代价是引擎退出码、路径、符号链接行为都带 Cygwin 特色，这些"特色"正是本项目要抹平的部分。

---

## 5 目录结构

```
img_tool\
├─ 1-启动解压工具.bat          图形界面启动器（纯 ASCII，CRLF）
├─ 2-拖放解压.cmd              把 IMG 拖到它上面即解压（纯 ASCII，CRLF）
├─ 3-制作测试镜像.bat          用 mkfs.erofs 自己压测试镜像
├─ imgtool_gui.pyw             GUI 入口（用 pythonw 跑，无黑框）
├─ imgtool_cli.py              命令行入口
├─ README.md                   本文档
├─ LICENSE                     本项目代码的许可证（0BSD）
├─ THIRD_PARTY_NOTICES.md      引擎二进制（erofs-utils / Cygwin）的许可证、源码与分发义务
├─ LICENSES\                   第三方许可证全文（GPL-2.0 / GPL-3.0 / LGPL-3.0）
├─ docs\
│   └─ ENGINE_PROVENANCE.md    引擎来历详解：这 4 个 exe 是谁、怎么编出来的、怎么核对、怎么自己重编
├─ CHANGELOG.md                变更记录
├─ .gitignore / .gitattributes 忽略规则与行尾规则
│
├─ imgtool\                    Python 包（全部只用标准库）
│   ├─ __init__.py             版本号
│   ├─ core.py                 镜像识别 · 引擎调用 · 进度/取消 · 符号链接 · 安全删除
│   ├─ sparse.py               Android sparse 识别 / 展开 / 打包（打包用于测试）
│   ├─ dnd.py                  Windows 原生拖放（ctypes 子类化窗口过程）
│   ├─ gui.py                  tkinter 界面（拖放区 / 任务表 / 进度 / 日志）
│   └─ cli.py                  argparse 命令行
│
├─ engine\                     解压引擎（第三方二进制，GPL-2.0 / LGPL-3.0）
│   ├─ fsck.erofs.exe          ★ 解压主力：--extract=<目录>
│   ├─ dump.erofs.exe          打印超级块/目录/inode（识别信息与进度估算用）
│   ├─ mkfs.erofs.exe          造镜像（生成测试镜像用）
│   ├─ extract.erofs.exe       第三方增强解包器（可导出 fs_config，本工具暂未使用）
│   ├─ cygwin1.dll             Cygwin 运行库，必须与 exe 同目录
│   ├─ README.md               引擎说明：用途、版本校验值、许可证（构建链路详解见 docs\）
│   └─ erofs-utils-…-Cygwin_x86_64.zip   原始发行包（可删，仅作留档）
│
├─ 示例镜像\                   给手动测试用的演示镜像（由 tests\make_demo_img.py 生成）
│   ├─ system_demo.img         EROFS + lz4
│   ├─ system_demo_lzma.img    EROFS + lzma
│   ├─ system_demo_sparse.img  Android sparse 外壳
│   └─ 期望结果.txt            逐项验收清单 + SHA256
│
├─ tests\                      测试
│   ├─ __init__.py
│   ├─ run_all.ps1             一键跑完下面全部验收（含文档自检）
│   ├─ make_fixtures.py        构造 tar → mkfs.erofs 压出 11 种布局的测试镜像
│   ├─ e2e_test.py             端到端：解压 + 逐文件 SHA256 / 链接 / 边界校验（45 项断言）
│   ├─ gui_test.py             开真窗口 + 投递真 WM_DROPFILES 消息的 GUI 自测
│   ├─ launcher_test.ps1       验证两个启动器真能起来
│   └─ make_demo_img.py        生成"示例镜像\"里给人手动测的镜像
│
├─ tools\                      开发/调查用脚本（不影响运行）
│   ├─ fetch_engine.py         下载并解包最新 Cygwin 版 erofs-utils
│   ├─ fetch_licenses.py       下载第三方许可证全文到 LICENSES\
│   ├─ verify_engine_provenance.py  审计引擎来历：本地 SHA256 + 上游 tag/脚本/补丁/CI/许可证
│   ├─ check_docs.py           文档自检：README 锚点/相对链接/提到的文件是否存在
│   ├─ add_spdx.py             给源码文件补 SPDX 许可证标识（幂等）
│   ├─ probe_engine.py         探测引擎能力（帮助文本、各压缩算法、异常输入）
│   ├─ probe_symlink.py        对比 CYGWIN=winsymlinks:* 下符号链接的落盘形态
│   ├─ probe_dnd.py            拖放回调"碰 Tk" vs "只入队"的最小复现
│   ├─ cleanup_and_device_probe.py  清理残留 + 观察设备节点表现
│   └─ smoke_engine.ps1        最小闭环：mkfs → fsck → 比 SHA256
│
└─ test\                       测试产物（可整目录删除，随时可重新生成）
    ├─ e2e\                     e2e 解压结果与 fixtures\
    ├─ gui\                     gui_test 的解压结果
    └─ launcher\                launcher_test 的解压结果
```

---

## 6 从零复现本工程

> 本节面向"拿到这份 README、要从空目录重建整个工程"的开发者或 AI Agent。
> 每一步都给了可验证的中间产物；按顺序做完，第 6.8 节的测试应当全绿。

### 6.1 准备引擎

**目标**：`engine\` 下得到 `fsck.erofs.exe`、`dump.erofs.exe`、`mkfs.erofs.exe`、`cygwin1.dll`。

**来源**：上游 [erofs/erofs-utils](https://github.com/erofs/erofs-utils) 的第三方预编译发布版
[sekaiacg/erofs-tools](https://github.com/sekaiacg/erofs-tools)（社区维护，持续跟进上游，提供
Android / Linux / Darwin / **Cygwin** 多平台构建）。

```powershell
# 已随仓库提供 tools\fetch_engine.py，它会自动挑最新的 Cygwin_x86_64 资产
python tools\fetch_engine.py
```

等价的纯手工步骤（便于校验）：

1. 取最新的 release（本文档基于 `v1.8.10-251217`，对应上游 erofs-utils `1.8.10-gee46dd74`）
2. 下载资产 `erofs-utils-v1.8.10-gee46dd74-251217-Cygwin_x86_64.zip`
3. 解包到 `engine\`

**校验值**（本文档对应的版本）：

| 文件 | 字节 | SHA256 |
| --- | --- | --- |
| `erofs-utils-v1.8.10-gee46dd74-251217-Cygwin_x86_64.zip` | 5 146 583 | `b6a24de0cfe49a95283cf306db1d158bdb63850e0687c8a8b0f4c4a540ba35ba` |
| `fsck.erofs.exe` | 1 965 568 | `81890a95aa6e9dd710119b22c674d089a311cd48474d270923873fbc37c05afa` |
| `mkfs.erofs.exe` | 2 073 600 | `e2bd628cefd10cc3abca747a65f344b21fc6ce2ae0ec36e5cfb9bc64d521202c` |
| `dump.erofs.exe` | 1 964 544 | `85456613664605b40e752fc22eb2a6a24e2966a5c4029af442a52adf7b4286cb` |
| `extract.erofs.exe` | 3 077 632 | `d7378ddb500c4338c4ef02f0da7601693a16807faafa453c1dc5750baf3b0dca` |
| `cygwin1.dll` | 3 012 149 | `ab77212a71c2e2e8b870452d2c32bc72a6708d6e963dd3ebe2ac1a946cffc242` |

**验收**：

```powershell
cd engine
.\fsck.erofs.exe --help     # 应当打印用法，并列出 lz4/lz4hc/lzma/deflate/zstd
.\mkfs.erofs.exe --version  # mkfs.erofs 1.8.10-gee46dd74
```

> ⚠️ **沙箱/杀软注意**：Cygwin 程序启动时必须创建一个内部命名管道
> （`\\.\pipe\cygwin-…`）。如果宿主环境禁止创建命名管道，会立刻失败并打印
> `fatal error - couldn't create signal pipe, Win32 error 5`。
> 这不是引擎坏了，放宽沙箱 / 加白名单即可（详见 [7](#7-踩坑记录) T5）。

### 6.2 编写 sparse 模块

**文件**：`imgtool/sparse.py`（参考实现，约 190 行）

**Android sparse image 格式**（全部小端，magic `0xED26FF3A`）：

```
header（28 字节）
  u32 magic = 0xED26FF3A
  u16 major_version = 1
  u16 minor_version = 0
  u16 file_hdr_sz  = 28
  u16 chunk_hdr_sz = 12
  u32 blk_sz              每个 block 的字节数（通常 4096）
  u32 total_blks          展开后的总块数
  u32 total_chunks        块组个数
  u32 image_checksum      （常为 0）

chunk header（12 字节）+ 数据
  u16 chunk_type   0xCAC1 raw        → 后面跟 chunk_sz 个 block 的原始数据
                   0xCAC2 fill       → 后面跟 4 字节填充值，铺满 chunk_sz 个 block
                   0xCAC3 don't care → 没有数据，展开成全 0
                   0xCAC4 crc32      → 后面跟 4 字节校验，跳过即可
  u16 reserved
  u32 chunk_sz     占多少个 block
  u32 total_sz     本 chunk 的总字节数（含 12 字节头）
```

**必须实现的函数**：

| 函数 | 作用 |
| --- | --- |
| `is_sparse(path)` | 只读 4 字节判断 magic |
| `read_header(path)` | 返回 `(blk_sz, total_blks, total_chunks, raw_size)`，`raw_size = blk_sz * total_blks` |
| `to_raw(path, out, on_progress, cancel)` | 流式展开，四种 chunk 都要处理；每 256 个块回调一次进度；`cancel()` 命中抛 `InterruptedError` |
| `raw_to_sparse(src, dst, blk_sz=4096)` | 反向打包（仅测试用）：连续全零块 → don't care，连续同值块 → fill，其余 → raw |
| `crc32_of_raw(path)` | 辅助校验 |

**易错点**：

* `fill` chunk 只带 4 字节数据，要按 `blk_sz // 4` 复制成整块再铺 `chunk_sz` 次
* `total_sz` 含 12 字节 chunk 头，算数据长度时要减掉
* 展开后大小必须正好等于 `blk_sz * total_blks`，可用它做断言

### 6.3 编写 core 模块

**文件**：`imgtool/core.py`（参考实现，约 700 行）。下面按子问题列出规范。

#### 6.3.1 定位引擎

* `engine_dir()`：优先环境变量 `IMGTOOL_ENGINE`，否则找「包目录的上一级」或「包目录内」的 `engine\`
* `tool_path(name)`：返回 `<engine>\<name>.exe`，不存在就报错
* `engine_version()`：跑 `fsck.erofs -V`，从 **stdout + stderr 合并文本**里正则抓版本号
  （Cygwin 程序可能写到 stderr，两边都要看）

#### 6.3.2 识别 EROFS 与超级块偏移

EROFS 超级块固定位于**文件偏移 1024** 处，结构体开头 16 字节：

```c
struct erofs_super_block {
    __le32 magic;           // 0xE0F5E1E2
    __le32 checksum;        // crc32c
    __le32 feature_compat;
    __u8   blkszbits;       // 块大小 = 1 << blkszbits
    __u8   sb_extslots;     // 超级块大小 = 128 + sb_extslots*16
    __le16 root_nid;        // 根目录 nid
    /* 后面还有 inos / build_time / blocks / uuid / volume_name … */
};
```

对应 Python：`struct.unpack("<IIIBBH", head[:16])`
**别写成 `<IIBBHI`**——那会把 `feature_compat` 当成单字节，`blkszbits` 取错位置，校验永远失败。

扫描算法（支持非 0 偏移）：

```
needle = struct.pack("<I", 0xE0F5E1E2)
在前 min(文件大小, 64MB) 里按 4MB 分块 find(needle)
候选超级块偏移 candidate = 命中位置 - 1024
  ├ 要求 candidate >= 0 且 candidate % 512 == 0
  └ 校验：1024 <= (1 << blkszbits) <= 1MB 且 0 < root_nid < 2^24
第一个通过校验的候选就是答案；没有通过的则退回"第一个候选"（交给 fsck.erofs 判定）
```

#### 6.3.3 其它格式识别表

按顺序检查即可（偏移从 0 算）：

| 特征 | 偏移 | 结论 |
| --- | --- | --- |
| `0xED26FF3A` | 0 | android-sparse |
| EROFS magic | 见上 | erofs |
| `53 EF` | 0x438 | ext2/3/4 |
| `10 20 F5 F2` | 0x400 | f2fs |
| `hsqs` | 0 | squashfs |
| `45 3D CD 28` | 0 | cramfs |
| `ANDROID!` | 0 | Android boot/recovery |
| `1F 8B` | 0 | gzip |
| `FD 37 7A 58 5A` | 0 | xz |
| `50 4B 03 04` | 0 | zip |
| `42 5A 68` | 0 | bzip2 |
| `30 50 4C 41` / `LP_METADATA` | 0 | Android super.img（动态分区） |

`sniff()` 返回带 `kind / offset / label / raw_size / extra / inode_count` 的 `ImageInfo`；
`label` 是给用户看的一句话，`extra` 来自 `dump.erofs -s` 的键值输出（把
`Filesystem inode count: N` 解析成 `filesystem_inode_count`，用于进度估算）。

#### 6.3.4 调用引擎（最关键的一节）

```python
argv = [tool_path("fsck.erofs"),
        "--extract=" + dest_dir.replace("\\", "/"),   # Cygwin 友好：正斜杠
        "--offset=%d" % offset,                        # 仅当 offset > 0
        "-d2",                                         # 日志级别
        image.replace("\\", "/")]

env = os.environ.copy()
env["PATH"]      = engine_dir() + os.pathsep + env["PATH"]
env["LC_ALL"]    = "C.UTF-8"           # 中文文件名按 UTF-8 走
env["LANG"]      = "C.UTF-8"
env["CYGWIN"]    = "winsymlinks:sys"   # ★ 不加这个符号链接会变成 Windows 读不了的重解析点
subprocess.Popen(argv, stdout=PIPE, stderr=STDOUT, cwd=engine_dir(), env=env,
                 creationflags=CREATE_NO_WINDOW)
```

* **正斜杠路径**：Cygwin 认得 `D:/a/b`，且不会把反斜杠当转义符
* **`cwd=engine_dir()`**：保证 `cygwin1.dll` 与临时文件都在引擎目录下解析
* **`CREATE_NO_WINDOW`**：GUI 用 `pythonw` 启动时不会闪黑框
* **退出码 0 = 成功**；非 0 时把输出映射成人话（见下表）
* 输出流用独立线程逐行读走，避免管道写满死锁

失败信息映射：

| 引擎输出含 | 给用户的提示 |
| --- | --- |
| `magic` / `not an erofs` / `failed to read superblock` | 不是有效的 EROFS 镜像 |
| `No space left` | 磁盘空间不足 |
| `Permission denied` | 没有权限写入目标目录 |
| `(File exists)` | 目标目录里已有同名文件（`--overwrite` 不处理硬链接） |
| 其它 | 原样带出引擎输出，附带退出码 |

#### 6.3.5 进度与取消

* 引擎本身**不打印进度**，所以进度靠**轮询输出目录**：
  每 50 ms `os.walk` 一次目标目录，统计「文件数 + 字节数 + 已用时间」回调给界面；
  有 `inode_count` 时据此算百分比（`min(99, 已解压条目 / inode 总数 * 100)`）。
* `os.walk` 必须**跳过重解析点**，否则会钻进 junction 重复计数。
* 取消：主循环每 50 ms 调一次 `cancel()`，命中就 `proc.kill()`，抛
  `ExtractError("已取消（已解压的内容保留在 …）")`。

#### 6.3.6 符号链接后处理

```python
CYGWIN_SYMLINK_MAGIC = b"!<symlink>"

def read_cygwin_symlink(path):
    # 文件 > 8KB 直接排除；读前几字节
    # 命中 magic 后：若紧跟 FF FE 则是 UTF-16LE（BOM 后解码），否则按 UTF-8
    # 解码结果按 "\0" 截断即目标路径
```

`fix_symlinks(root, mode, write_manifest)`：

1. 遍历输出目录（跳过清单文件本身），识别所有 Cygwin 链接文件
2. 每条按 [4.2](#42-解压流程) 的三级降级处理；**失败时必须把原始字节原样写回**，不能丢信息
3. `mode="copy"` 时第 3 级改为「复制目标内容」（仅当目标是文件）
4. 未还原的（或 `write_manifest=True` 时全部）写入 `<输出目录>\_imgtool_symlinks.txt`，
   格式 `相对路径 -> 目标    [处理方式]`
5. 返回统计 `{total, symlink, junction, copy, kept}`，写进日志和结果摘要

#### 6.3.7 安全删除目录

```python
FILE_ATTRIBUTE_REPARSE_POINT = 0x400

def is_reparse_point(path):      # Windows 上 os.path.islink 认不出 junction
    return bool(os.lstat(path).st_file_attributes & 0x400)
```

`safe_rmtree(path)` 必须**自己递归**，不能用 `shutil.rmtree`：

* Python 3.8 的 `shutil.rmtree` 会把 junction 当成普通目录**钻进去**，
  删掉链接目标里的文件（如果链接指向别处，就是删别人的数据）
* 正确做法：`os.scandir` 逐项判断，`entry.is_dir(follow_symlinks=False) and not is_reparse_point(p)`
  才递归；重解析点一律「只删链接本身」（先 `os.remove`，失败再 `os.rmdir`）
* 删除失败时清一次只读属性再试

### 6.4 编写 dnd 模块

**文件**：`imgtool/dnd.py`（参考实现，约 160 行）。**不引入任何第三方包**。

```
user32: SetWindowLongPtrW / GetWindowLongPtrW（32 位系统退化为 SetWindowLongW/GetWindowLongW）
        GetAncestor(hwnd, GA_ROOT=2)  →  拿到真正的顶层窗口句柄
        CallWindowProcW                →  其它消息转给原窗口过程
        ChangeWindowMessageFilterEx(hwnd, msg, MSGFLT_ALLOW=1, NULL)
shell32: DragAcceptFiles / DragQueryFileW / DragFinish
常量:   WM_DROPFILES = 0x0233
        WM_COPYGLOBALDATA = 0x0049（管理员权限运行时需要额外放行）
        GWLP_WNDPROC = -4
```

步骤：

1. `widget.update_idletasks()` 后取 `winfo_id()`，用 `GetAncestor(..., GA_ROOT)` 换成顶层句柄
2. 放行 `WM_DROPFILES` / `WM_COPYGLOBALDATA`（防 UIPI 拦截）
3. `DragAcceptFiles(hwnd, True)`
4. 用 `ctypes.WINFUNCTYPE(LRESULT, HWND, UINT, WPARAM, LPARAM)` 定义窗口过程，
   `SetWindowLongPtrW(hwnd, GWLP_WNDPROC, proc)` 子类化；**回调对象必须保存在实例属性上**，
   否则被 GC 回收后进程会崩
5. 窗口过程里收到 `WM_DROPFILES` 时：
   * `DragQueryFileW(hDrop, 0xFFFFFFFF, None, 0)` 取个数，逐个取路径（先问长度再取内容）
   * **立刻 `DragFinish(hDrop)`**
   * **只把路径 append 到 `self._pending`（和一个线程安全的位置），其他什么都不做**
   * `return 0`；其它消息 `return CallWindowProcW(old_proc, ...)`
6. 主线程用 `take_pending()` 取走 → 交给界面处理

> 窗口过程里**不要**操作 Tk 控件、不要扫描文件系统。
> 实测在回调里做重活会让 CPython 抛 `Fatal Python error: PyEval_RestoreThread: NULL tstate`
> 直接崩进程（见 [7](#7-踩坑记录) T8）。在回调里碰 Tk 的用法**偶尔**能跑通，但不值得赌。

`dnd.py` 里还提供一个测试专用函数：

```python
post_drop(hwnd, paths)   # 自己构造 WM_DROPFILES 消息投递给窗口，模拟真实拖放
```

它需要：`GlobalAlloc(GMEM_MOVEABLE)` 一块内存 → 写入 `DROPFILES` 头
（`<IiiII` = `pFiles=20, pt={0,0}, fNC=0, fWide=1`）+ 各路径的 UTF-16LE 串 + 双 `\0`
→ `GlobalLock/memmove/GlobalUnlock` → `PostMessageW(hwnd, WM_DROPFILES, hMem, 0)`。
**注意给 `GlobalAlloc/GlobalLock/PostMessageW` 声明 `argtypes/restype`**，
否则 64 位句柄会报 `OverflowError: int too long to convert`。

### 6.5 编写 GUI 和 CLI

**`imgtool/gui.py`**（参考实现，约 460 行）：

* 顶部标题 + 引擎版本（`core.engine_version()`）
* 拖放区：`tk.Canvas` 画虚线框 + 文案，点击 = 打开文件选择框
* 选项行：输出位置（同名目录 / 自定义）、目录已存在策略、符号链接策略、
  完成后打开目录、写链接清单、**拖进来就自动解压（默认开）**
* `ttk.Treeview` 任务表：文件 / 状态 / 输出目录，双击行 = 打开输出目录
* `ttk.Progressbar` + 状态文字 + `开始解压 / 取消 / 清空列表`
* 深色只读 `tk.Text` 当日志
* **线程模型**：解压跑在 `threading.Thread`，所有界面更新通过
  `queue.Queue` + `root.after(80, self._pump)` 回主线程；
  `_pump` 里同时轮询 `drop_target.take_pending()` 处理拖放
* 取消 = `threading.Event`，传给 `core.extract_image(cancel=flag.is_set)`
* 关窗时若正在解压，弹确认框
* 注意：GUI 里**不要**写多行字符串时混用中文引号，`""` 会直接造成语法错误

**`imgtool/cli.py`**：`argparse`，参数见 [2.2](#22-三种用法)。
输出用 `%` 格式化，逐行 flush，方便被 `2-拖放解压.cmd` 实时显示。

**入口文件**（放仓库根目录，避免包内相对导入问题）：

```python
# imgtool_gui.pyw
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from imgtool import gui
if __name__ == "__main__":
    sys.exit(gui.main())
```

### 6.6 编写启动器

**铁律：`.bat` / `.cmd` 内容只用 ASCII，行尾用 CRLF。**

原因见 [7](#7-踩坑记录) T4：cmd.exe 是**按字节偏移**重新读取批处理文件的，
UTF-8 中文在 GBK 代码页下会让解析器错位，出现 `'thon' is not recognized` 这种鬼报错。
文件名可以是中文（文件系统负责），内容不行。

**`1-启动解压工具.bat`** 找 Python 的顺序：

1. `where pythonw` → 直接用
2. `where python` → 把 `python.exe` 替换成 `pythonw.exe` 后判断是否存在
3. 常见安装位置兜底（`%USERPROFILE%\anaconda3`、`%LOCALAPPDATA%\Programs\Python\Python3xx` 等）
4. 都没有就 `echo` 提示 + `pause`

找到后 `start "" "%PYW%" "%HERE%imgtool_gui.pyw"`（`start` 让 GUI 脱离控制台）。

**`2-拖放解压.cmd`**：`%*` 就是被拖进来的文件列表，直接透传给
`python imgtool_cli.py %*`；无参数双击时提示手动输入路径。末尾 `pause` 让用户看到结果。

**`3-制作测试镜像.bat`**：透传参数给 `tests\make_fixtures.py`。

### 6.7 构造测试镜像

要验证"任意 IMG 都能解"，必须自己造镜像。Windows 上普通用户**无法创建符号链接**
（`os.symlink` 报 `WinError 1314`），所以不能用磁盘目录当源——**用 tar 当源**：

```python
mkfs.erofs [压缩选项] --tar -T 1700000000 out.img src.tar
                       ^^^^^^ 必须有！否则 mkfs 会把 tar 当成"待重建的已有镜像"去解析，
                              报 cannot find valid erofs superblock
```

测试 tar 由 `tarfile` 逐条构造（`tarfile.TarInfo` 手工设置 `mode/uid/gid/mtime/type/linkname`），
覆盖：普通文件、空文件、只读文件(0444)、私有文件(0600)、可执行(0755)、目录、空目录、
中文名、空格名、深层嵌套、全零文件、高压缩比文本、随机大文件、**硬链接(LNKTYPE)**、
**符号链接(SYMTYPE，相对/绝对/悬空/指向目录)**、设备节点/ FIFO（CHRTYPE/FIFOTYPE）。

`tests\make_fixtures.py` 里的布局矩阵（用 `mkfs.erofs` 的选项）：

| 名字 | 选项 | 结果 |
| --- | --- | --- |
| plain | （无） | ✅ |
| lz4 | `-zlz4` | ✅ |
| lz4hc9 | `-zlz4hc,9` | ✅ |
| lzma | `-zlzma,9` | ✅ |
| zstd | `-zzstd,9` | ✅ |
| deflate | `-zdeflate,9` | ✅ |
| chunk64k | `-zlz4 -C65536` | ✅ |
| dedupe | `-zlz4 -Ededupe` | ✅ |
| allroot | `-zlz4 --all-root` | ✅ |
| ztailpacking | `-zlz4 -C65536 -Eztailpacking` | ✅ |
| chunksize | `-zlz4 --chunksize=4096` | ❌ Cygwin 版 mkfs 失败（见 [10](#10-已知限制)） |
| big | `-zlz4`，96 MB 随机数据 | ✅（吞吐测试） |
| fragments / metacomp / dircompress | `-Efragments` / `-m4096` / `--zD` | ❌ Cygwin 版 mkfs 失败（`failed to initialize packedfile/metadata`） |

> mkfs 失败时**必须删掉它留下的输出文件**：`--chunksize` 那次会在磁盘上留下一个
> 逻辑大小 2 TB 的稀疏文件（见 [7](#7-踩坑记录) T7）。

### 6.8 测试与验收

```bat
:: 一键：端到端 + GUI 拖放 + 启动器 + 文档自检
powershell -File tests\run_all.ps1

:: 或分开跑
python tests\e2e_test.py
python tests\gui_test.py
powershell -File tests\launcher_test.ps1
python tests\make_demo_img.py
```

**验收标准**：

* `e2e_test.py` 退出码 0，末尾打印 `结果：45 项通过，0 项失败`
* `gui_test.py` 退出码 0，末尾 `结果：PASS`，且输出目录等于 `<镜像同目录>\<镜像名>`
* `launcher_test.ps1` 退出码 0：GUI 进程被拉起（窗口标题 `IMG 解压工具 · EROFS`），
  且拖放解压生成同名目录
* `make_demo_img.py` 三个镜像自检全 PASS

`e2e_test.py` 的断言分组：

| 分组 | 覆盖内容 |
| --- | --- |
| 1 | 生成 11 个测试镜像 |
| 2 | 每种压缩算法/布局解压后逐文件 SHA256 比对（内容/大小/链接/硬链接 inode） |
| 2b | 高级布局用普通目录源再试一次（失败则记录，不判失败） |
| 3 | 默认输出目录 = 镜像同目录同名文件夹，且返回值正确 |
| 4 | `auto` 自动加序号；`overwrite` 删除重建且旧文件被清掉 |
| 4b | 符号链接三种模式（native / copy / keep）+ 清单文件 |
| 5 | Android sparse：识别 → 展开 → 解压 → 临时文件已清理 |
| 6 | 非 0 偏移（前面塞 4 KB 别的数据）自动识别 offset=4096 |
| 7 | 中文/空格路径（镜像路径与输出路径都带中文） |
| 8 | 错误处理：垃圾文件、空文件、不存在、ext4、f2fs |
| 9 | 取消正在进行的解压（由进度回调触发，保证在解压途中取消） |
| 10 | 含设备节点/FIFO 的镜像整盘解压不中断 |

### 6.9 复现自检清单

- [ ] `engine\fsck.erofs.exe --help` 能打印用法（不是 `couldn't create signal pipe`）
- [ ] `python -c "from imgtool import core; print(core.engine_version())"` 打印 `1.8.10-…`
- [ ] 随便造一个镜像，`python imgtool_cli.py --info x.img` 能识别成 `EROFS 镜像`
- [ ] `python imgtool_cli.py x.img` 在镜像旁生成同名目录，文件数与源一致
- [ ] 双击 `1-启动解压工具.bat` 能出窗口；拖入 `示例镜像\system_demo.img` 能自动解压
- [ ] `python tests\e2e_test.py` → `45 项通过，0 项失败`
- [ ] `python tests\gui_test.py` → `结果：PASS`
- [ ] `powershell -File tests\launcher_test.ps1` → `结果：PASS`
- [ ] 输出目录里符号链接的表现符合 [4.2](#42-解压流程) 的三级降级（用 Explorer 看）
- [ ] 中文目录名、带空格目录名都能正常解出

---

## 7 踩坑记录

> 这一节是本项目最有价值的部分：每条都是实际踩到并修掉的，附症状 / 原因 / 对策。
> 复现时如果遇到同样症状，直接照方抓药。

### T1 Cygwin 默认把符号链接写成 Windows 读不了的重解析点

* **症状**：解压出来的符号链接是 0 字节文件，属性带 `ReparsePoint`，Python/PowerShell
  读不了（`WinError 1920 系统无法访问此文件`），`del`、`rd /s /q`、`fsutil reparsepoint delete`
  全部 `Access is denied`，连删都删不掉。
* **诊断**：`fsutil reparsepoint query <文件>` 显示
  `Reparse Tag Value : 0xa000001d`，数据是 `02 00 00 00 6d 6b 73 68`（`mksh`）。
  `0xA000001D` 是 **`IO_REPARSE_TAG_LX_SYMLINK`**，也就是 **WSL 的符号链接标签**——
  Cygwin 3.4+ 默认造"WSL 认得、Windows 自己反而打不开"的链接。
* **对策**：给引擎进程设环境变量 `CYGWIN=winsymlinks:sys`，符号链接就变成普通文件：
  `"!<symlink>" + FF FE + 目标(UTF-16LE) + 00 00`，Windows 完全可以读，
  我们再后处理成真链接 / 目录联接 / 保留目标文件。

### T2 `fsck.erofs --overwrite` 遇到硬链接会整个中断

* **症状**：往已有目录里二次解压，即使加了 `--overwrite` 也会失败：
  `<E> erofs: failed to extract hard link: …/system/bin/sh (File exists)`。
  不加 `--overwrite` 时更早失败：`failed to open: …/deep.txt (File exists)`。
* **原因**：上游 `--overwrite` 只处理普通文件的覆盖，硬链接路径没走覆盖逻辑。
* **对策**：把"覆盖"策略实现成**先 `safe_rmtree` 删除旧目录，再整盘解压**（干净、可预测）；
  并把 `(File exists)` 映射成给用户看的中文提示。放弃语义含糊的 "merge" 策略。

### T3 `shutil.rmtree` 会跟进目录联接

* **症状**：清理上一次解压结果时，`shutil.rmtree(..., ignore_errors=True)` 偶发失败，
  且目录里 junction 指向的内容被"删了两遍"。
* **原因**：Python 3.8 的 `shutil.rmtree` 用 `entry.is_dir()` 判断目录，
  junction 会被当成普通目录**递归进去**。如果链接指向别的地方，那就是在删别人的数据。
* **对策**：自己写 `safe_rmtree`：用 `st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT (0x400)`
  识别重解析点，只删链接本身，绝不跟进。测试里也统一改用它。

### T4 cmd.exe 解析不了带 UTF-8 中文的 `.bat`

* **症状**：批处理报一堆莫名其妙的错：`'thon' is not recognized`、
  `'efined' is not recognized`、`'p0"' is not recognized`，像是文件被撕碎了。
* **原因**：cmd.exe 执行批处理时是**按字节偏移**从文件里重新读取下一行的；文件是 UTF-8、
  控制台代码页是 GBK(936) 时，一行里的多字节字符会让它算错下一行的起点，从此错位。
  `chcp 65001` 也救不了（切换代码页本身还会改变偏移计算）。
* **对策**：`.bat` / `.cmd` **内容只用 ASCII**（中文只出现在文件名、README、GUI 和 Python 输出里），
  行尾统一 CRLF，并在 `.gitattributes` 里钉死 `*.bat text eol=crlf`。

### T5 Cygwin 程序必须有命名管道才能启动

* **症状**：`fatal error - couldn't create signal pipe, Win32 error 5`，退出码 `-1073741502`。
  在本项目的 DSH 沙箱里 100% 复现；普通桌面环境下不会出现。
* **原因**：cygwin1.dll 初始化时要创建 `\\.\pipe\cygwin-<hash>-…` 作为信号管道；
  受限令牌 / 沙箱 / 部分杀软会拒绝创建命名管道。
* **对策**：这不是代码问题。放宽沙箱（本项目开发时用 `danger-full-access`）、
  给引擎目录加杀软白名单即可。文档里对测试脚本专门加了提示。

### T6 `mkfs.erofs` 吃 tar 必须显式加 `--tar`

* **症状**：`mkfs.erofs out.img src.tar` 报
  `<W> EXPERIMENTAL rebuild mode in use` + `cannot find valid erofs superblock`——
  它把 tar 当成"待重建的已有镜像"了。
* **原因**：上游 tar 输入由独立开关控制（`mkfs/main.c` 里 `{"tar", optional_argument, …}`，
  `mkfs_parse_tar_cfg(NULL)` 时只置 `tar_mode = true`）。
* **对策**：`mkfs.erofs … --tar -T <ts> out.img src.tar`。不带参数即可，不需要 `--tar=值`。

### T7 mkfs 失败会留下超大稀疏文件

* **症状**：`mkfs.erofs --chunksize=4096` 返回 1，但在磁盘上留下了一个
  **逻辑大小 2 TB**（`2097152 MB`）的稀疏文件，把目录统计、备份、Explorer 都搞乱。
* **对策**：mkfs 失败或产物大于 4 GB 时**立刻删掉输出文件**；测试收尾再清理 > 32 MB 的产物。

### T8 在拖放回调里做重活会让 CPython 崩溃

* **症状**：`Fatal Python error: PyEval_RestoreThread: NULL tstate`，
  栈停在 `tkinter/__init__.py in update`，进程直接死掉。
  最小复现（`tools\probe_dnd.py`）显示：回调里只 `append` 一个列表 → 正常；
  回调里操作 Tk 控件 + 扫文件系统 → 崩。
* **原因**：`WM_DROPFILES` 是在 Tcl 事件循环内部被派发的，此时 GIL 已释放；
  在这个窗口里再大量回调进 Tk/CPython，状态容易失衡。
* **对策**：窗口过程只做三件事——取路径、`DragFinish`、`self._pending.append(paths)`；
  真正处理放到主线程 `root.after(80, self._pump)` 轮询里。

### T9 ctypes 不声明 argtypes 会 `OverflowError`

* **症状**：`ctypes.ArgumentError: argument 1: <class 'OverflowError'>: int too long to convert`
  （`GlobalLock(hMem)`）。
* **对策**：给 `GlobalAlloc/GlobalLock/GlobalUnlock/PostMessageW/CreateFileW` 等
  显式声明 `argtypes` 与 `restype`，句柄用 `wintypes.HGLOBAL/HANDLE`。

### T10 设备节点在 Windows 上会变成 `.lnk`

* **症状**：镜像里的 `dev/null`（字符设备）、`dev/fifo` 解压后变成
  `dev/null.lnk`、`dev/fifo.lnk`（0444 只读的小文件，内容是 Windows 快捷方式头
  `4C 00 00 00 01 14 02 00 …`）。
* **原因**：NTFS 没有字符设备，Cygwin 用快捷方式文件占位。
* **对策**：接受这个行为（解压不中断），在文档里说明；测试里只断言"整盘解压不中断"。

### T11 EROFS 超级块结构体不能解错

* **症状**：镜像明明是 EROFS（`mkfs.erofs` 刚生成的），`sniff()` 却报"无法识别的镜像格式"。
* **原因**：结构体格式串写成了 `<IIBBHI`（把 `feature_compat` 当单字节），
  于是 `blkszbits` 取到错误字节，块大小校验必失败。
* **对策**：正确格式是 `<IIIBBH`（magic / checksum / feature_compat / blkszbits / sb_extslots / root_nid）。
  另外"扫到 magic 但校验不过"时不要直接放弃，退回第一个候选交给 `fsck.erofs` 判定。

---

## 8 测试

### 8.1 测试镜像里有什么

`tests\make_fixtures.py` 从零构造的 tar 内容（真人可逐项核对）：

| 类别 | 具体条目 |
| --- | --- |
| 目录 | `system/`、`system/bin`、`system/lib64`、`system/priv-app/MyApp`、`vendor/lib64`、`etc/init`、`usr/share`、`emptydir/`、`a/b/c/d/e/f/g/`、`中文目录/`、`apps/我的应用/`、`path with space/` |
| 普通文件 | `etc/hosts`、`system/bin/mksh`(0755)、`system/bin/toolbox`、`vendor/lib64/libfoo.so`、`libbar.so`（与 libfoo 同内容，测去重）、`system/priv-app/MyApp/base.apk`(4 MB 随机)、`usr/share/zeros.bin`(1 MB 全零)、`text.txt`(高压缩比)、`readonly.txt`(0444)、`secret.conf`(0600)、`empty.conf`(0 字节)、`中文文件.txt`、`带#符号.txt`、`file name.txt` |
| 符号链接 | `sh_link→mksh`（相对）、`mksh_abs→/system/bin/mksh`（绝对）、`libfoo.so.1→libfoo.so`、`broken_link→nowhere/…`（悬空）、`中文链接→中文目录/中文文件.txt`、`system/lib64_alias→/vendor/lib64`（指向目录）、`vendor/syslib→../system`（指向目录，相对） |
| 硬链接 | `system/bin/sh` ⇄ `system/bin/mksh` |
| 特殊文件（torture） | `dev/null`、`dev/urandom`（字符设备）、`dev/fifo`（FIFO） |

### 8.2 怎么跑

```bat
:: 一键跑完全部验收（推荐）
powershell -File tests\run_all.ps1

:: 或者分开跑
python tests\make_fixtures.py         :: 只造镜像
python tests\e2e_test.py              :: 造镜像 + 全部端到端断言（--quick 可跳过慢项）
python tests\gui_test.py              :: GUI + 真实拖放消息
powershell -File tests\launcher_test.ps1
python tests\make_demo_img.py         :: 生成"示例镜像\"给人工试
python tools\check_docs.py            :: 文档自检（锚点 / 相对链接 / 提到的文件是否存在）
```

产物落在 `test\`（`e2e_test.py` 收尾会自动删掉 > 32 MB 的中间文件）。

### 8.3 实测结果

本文档对应的版本，在 Windows 11 (build 26100) + Python 3.8.3 + erofs-utils 1.8.10-gee46dd74
上实测：

```
=== tests\e2e_test.py ===
引擎：fsck.erofs 1.8.10-gee46dd74 @ <repo>\engine
[1]  生成测试镜像                                     共 11 个
[2]  解压 plain/lz4/lz4hc9/lzma/zstd/deflate/        全部 PASS
     chunk64k/dedupe/allroot/ztailpacking
     解压 big（96 MB）                                PASS，约 520 MB/s
[2b] fragments / metacomp / dircompress               mkfs 失败，跳过（不影响解压主流程）
[3]  默认输出目录 = 同名文件夹                        PASS
[4]  auto 加序号 / overwrite 删除重建                 PASS
[4b] 符号链接 native / copy / keep                     PASS
[5]  Android sparse（展开→解压→清理临时文件）          PASS
[6]  非 0 偏移（offset=4096）                          PASS
[7]  中文 / 空格路径                                   PASS
[8]  错误处理（垃圾/空/不存在/ext4/f2fs）              PASS
[9]  取消正在进行的解压                                PASS
[10] 设备节点 / FIFO 不中断解压                        PASS
结果：45 项通过，0 项失败

=== tests\gui_test.py ===
窗口已创建，拖放可用 = True
投递 WM_DROPFILES → 任务状态：完成 → 输出目录：…\test\gui\dropped
结果：PASS

=== tests\launcher_test.ps1 ===
[PASS] GUI 进程已启动，窗口标题: IMG 解压工具 · EROFS
[PASS] 生成同名目录 system\，22 个文件
结果：PASS
```

小镜像（6.4 MB）端到端约 0.2~0.4 s（大部分开销是进程启动 + 后处理），
96 MB 镜像的解压吞吐实测约 **520 MB/s**（lz4）；lzma 明显更慢，属算法本身特性。

---

## 9 常见问题

**Q：为什么不用 WSL？**
A：要额外安装、占空间、可能要重启。Cygwin 版 `fsck.erofs` 是上游原版代码，
一个 exe + 一个 DLL 就跑起来了，绿色免安装。

**Q：杀毒软件报警怎么办？**
A：`engine\` 下是第三方预编译二进制（上游 erofs-utils，许可证与来源见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)）。不放心可以只保留
`fsck.erofs.exe` + `cygwin1.dll`，或者按 [6.1](#61-准备引擎) 自己校验哈希后加白名单。

**Q：解出来的符号链接为什么是文本文件？**
A：Windows 建真符号链接需要开发者模式/管理员权限，详见
[4.2](#42-解压流程)。开启「开发人员模式」后重新解压即可拿到真链接。

**Q：为什么"覆盖"是删除后重建，不能增量覆盖？**
A：`fsck.erofs` 的 `--overwrite` 遇到硬链接会直接中断（上游限制），详见 [7](#7-踩坑记录) T2。

**Q：文件权限/属主和手机里不一样？**
A：NTFS 没有 POSIX uid/gid，只能近似（只读位、可执行位）。做 ROM 修改请以镜像里的
`fs_config` / `file_contexts` 为准。

**Q：能只解压镜像里的某个子目录吗？**
A：当前版本整盘解压。`fsck.erofs` 不支持选择性解压，但 `engine\extract.erofs.exe` 支持，
接口已预留（见 [11](#11-扩展路线)）。

**Q：解压很慢？**
A：lzma/deflate 比 lz4 慢一个数量级，属算法特性。大镜像先确认目标盘空间。

**Q：`.bat` 里为什么全是英文？**
A：见 [7](#7-踩坑记录) T4，cmd.exe 与 UTF-8 中文天生不合。

**Q：能解 `super.img` 吗？**
A：不能。`super.img` 是动态分区容器（LP metadata），里面才是真正的 `system.img` 等。
先用别的工具拆出单个分区镜像再拖进来。

---

## 10 已知限制

1. **只支持 EROFS**。ext4/f2fs/squashfs 只能识别并提示，不解压（本项目的定位就是 fsck.erofs 前端）。
2. **fragments / 元数据压缩 / chunk 化镜像没有实测过**。不是解压端的问题
   （fsck.erofs 由上游负责读），而是 Cygwin 版 `mkfs.erofs` 造不出这类镜像用于测试
   （报 `failed to initialize packedfile/metadata`）。真机镜像可以照常试，欢迎反馈结果。
3. **设备节点/FIFO 只能变成 `.lnk` 占位文件**（NTFS 限制）。
4. **不做选择性解压**，整盘解出。
5. **不做回打包**（把目录重新压回 EROFS）。`mkfs.erofs.exe` 已在引擎里，接上不难（见 [11](#11-扩展路线)）。
6. **sparse 镜像需要额外汇空间**：展开出的 raw 放在镜像同目录，大小 = `blk_sz * total_blks`
   （例如 4 GB 的 sparse 展开可能占满同盘）。临时文件用完即删，可 `--keep-temp` 保留排查。
7. **32 位 Python 未测试**；Cygwin 引擎本身是 x86_64。
8. **符号链接真链接**依赖系统权限；无权限时是目录联接或目标文件（行为已在 UI/日志中说明）。
9. **不做进度精确百分比**：引擎不输出进度，界面按条目数估算。

---

## 11 扩展路线

按"性价比"排序，供二次开发者挑选：

1. **选择性解压**：接 `engine\extract.erofs.exe`（支持 `-X/--extract=<路径>`、
   `-p` 打印条目、`-c` 配置文件），让用户在镜像里勾选要解出的目录。
2. **导出 `fs_config` / `file_contexts`**：同一个 `extract.erofs.exe` 就能产出，
   对 ROM 修改党非常实用；可在 GUI 加一个复选框。
3. **回打包**：`mkfs.erofs --tar -zlz4 out.img src.tar`，把已经解压好的目录重新打成镜像
   （注意权限/属主信息在 NTFS 上已经不完整，需要从 `fs_config` 恢复）。
4. **更多格式**：集成 `simg2img`（已内置 Python 版）、`7z`（squashfs/ext4）、
   `payload.bin` 解析（OTA 包），把工具做成"任意 IMG 都能开"。
5. **资源管理器集成**：SendTo 菜单 / 右键菜单"用 imgtool 解压"，一条注册表项即可。
6. **真符号链接增强**：检测到无权限时给出"一键开启开发者模式"的引导（deep link 到设置页）。
7. **多语言**：把 GUI 文案抽成 `lang/*.json`，加英文界面。
8. **打包成单文件 exe**：PyInstaller `--onefile`，把 `engine\` 作为数据一并塞进去，
   部署更省事（注意 GPL/LGPL 分发义务）。

---

## 12 许可证与第三方组件

| 部分 | 许可证（SPDX） | 说明 |
| --- | --- | --- |
| 本项目代码（`imgtool\`、`tests\`、`tools\`、各脚本、文档） | **`0BSD`** | 见 [LICENSE](LICENSE) |
| `engine\fsck.erofs.exe`、`mkfs.erofs.exe`、`dump.erofs.exe` | **`GPL-2.0-or-later`** | 来自 [erofs-utils](https://github.com/erofs/erofs-utils) |
| `engine\extract.erofs.exe` | **`GPL-2.0-or-later`** | 来自 [sekaiacg/erofs-tools](https://github.com/sekaiacg/erofs-tools) |
| `engine\cygwin1.dll` | **`LGPL-3.0-or-later`**（含链接例外） | [Cygwin](https://cygwin.com/) 运行库 |

许可证全文随仓库提供：[LICENSES/GPL-2.0.txt](LICENSES/GPL-2.0.txt)、
[LICENSES/GPL-3.0.txt](LICENSES/GPL-3.0.txt)、[LICENSES/LGPL-3.0.txt](LICENSES/LGPL-3.0.txt)。
版本、SHA256 校验值、构建方式与精确到 tag/commit 的源码获取点，见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

### 这些 `.exe` 是怎么来的

先分清三方，别混：

| 角色 | 是谁 | 地址 | 干什么 |
| --- | --- | --- | --- |
| **① 官方上游** | **erofs-utils** —— EROFS 文件系统（Android `system` 分区用的只读文件系统）的**官方用户态工具集**，由 EROFS 作者（Xiang Gao / `hsiangkao`）等人维护 | 主开发树 <https://git.kernel.org/pub/scm/linux/kernel/git/xiang/erofs-utils.git><br>官方 GitHub 镜像 <https://github.com/erofs/erofs-utils> | 写 `fsck.erofs` / `mkfs.erofs` / `dump.erofs` 的**全部源码** |
| **② 第三方构建工程** | **sekaiacg/erofs-tools** —— 个人（sekaiacg）维护的**打包/构建工程**，不是 erofs-utils 的官方发行渠道 | <https://github.com/sekaiacg/erofs-tools> | 它**不写文件系统代码**，只负责把 ① 的源码连同依赖编成各平台成品并发布 |
| **③ 本项目** | **imgtool** | <https://github.com/littlecoca/erofs_tool_win> | 下载 ② 的 Windows 成品，套一层好用的 GUI/CLI |

> **一句话**：本项目 `engine\` 里的 `.exe`，是**官方项目 erofs-utils（①）的源码**，
> 被**第三方构建工程 sekaiacg/erofs-tools（②）**在 **GitHub Actions 的 Ubuntu 机器**上，
> 用**目标平台为 Cygwin 的 Clang 交叉编译器**编译成 Windows 可执行文件；
> 本项目（③）只下载成品、用 `subprocess` 调起来。
>
> 换句话说：这几个 exe **从来没有在 Windows 上编译过**——编译它们的是 Linux，
> 只是"目标平台"设置成了 Cygwin（`x86_64-pc-cygwin`）。

**② 到底是怎么构建的**（四步，细节见 [详解文档](docs/ENGINE_PROVENANCE.md)）：

1. **收源码**：把 ① 的 erofs-utils 源码，外加 11 个依赖
   （lz4 / zstd / xz / zlib / xxHash / libfuse / e2fsprogs / pcre / selinux / libcxx），
   全部以 git submodule 形式收进自己的仓库并**锁定提交**，另开 `build/cmake/` 一套 CMake 构建系统。
2. **定目标**：`build/cmake/erofs-tools/erofs_tools.cmake` 里逐个工具声明目标 ——
   `file(GLOB fsck/*.c)` → `add_executable(fsck.erofs …)`，mkfs/dump 同理；
   并把 liberofs 与各压缩库**全部静态链接**进去。
3. **交叉编译**：在 GitHub Actions 的 `ubuntu-latest` 上
   `apt install cygwin cygwin-gcc cygwin-libiconv cygwin-xclang cygwin-libc++`
   （社区打包的 Cygwin 交叉工具链），然后跑 `build_cygwin.sh`：

   ```bash
   cmake -S ./build/cmake -B ./out -G Ninja \
         -DCMAKE_SYSTEM_NAME="CYGWIN" \
         -DCMAKE_C_COMPILER="x86_64-pc-cygwin-clang" \
         -DCMAKE_CXX_COMPILER="x86_64-pc-cygwin-clang++" \
         -DCMAKE_BUILD_TYPE="Release" -DMAX_BLOCK_SIZE="4096"
   ninja -C ./out
   ```

4. **打包发布**：把 `*.erofs.exe` 四个成品 + 交叉 sysroot 里的
   `/usr/x86_64-pc-cygwin/bin/cygwin1.dll` 拷到一起，统一时间戳后压成
   `erofs-utils-v1.8.10-gee46dd74-251217-Cygwin_x86_64.zip`，作为 GitHub Release 资产发布。

**完整链路**（每个依赖的锁定提交、CMake 原文、4 个补丁改了什么、CI 步骤、自己重编的三种方式、
常见疑问、术语表）见 [**docs/ENGINE_PROVENANCE.md**](docs/ENGINE_PROVENANCE.md)。

```
①  erofs/erofs-utils                       上游源码（C 语言，GPL-2.0-or-later）
    fsck/main.c → fsck.erofs    mkfs/main.c → mkfs.erofs    dump/main.c → dump.erofs
    lib/、include/ → liberofs（lz4 / lzma / deflate / zstd 解码、inode、xattr）
    lib/ 与 include/ 采用 GPL-2.0+ 或 Apache-2.0 双许可，其余文件为 GPL-2.0+
                    │  源码 + 11 个依赖（lz4/zstd/xz/zlib/xxHash/libfuse/
                    │  e2fsprogs/pcre/selinux/libcxx），全部以 submodule 锁定提交
                    ▼
②  sekaiacg/erofs-tools                    第三方构建工程（GPL-2.0）
    · 用 CMake（build/cmake/）替代上游 autotools，逐库描述怎么编
    · 构建定义 build/cmake/erofs-tools/erofs_tools.cmake：
          file(GLOB fsck_srcs "${PROJECT_ROOT_DIR}/fsck/*.c")
          add_executable(fsck.erofs ${fsck_srcs})
          target_link_libraries(fsck.erofs  erofs_static cutils base log selinux
                               lz4_static liblzma z_static libzstd_static pcre2 xxhash
                               ext2_uuid iconv  ntdll)     # 后三个是 CYGWIN 追加的
      → 所有依赖**静态链接**，所以单个 exe 只有 ~2 MB 却支持全部压缩算法，
        运行时除 cygwin1.dll 不依赖任何其它 DLL
    · 4 个 Cygwin 兼容补丁（build/cmake/lib/patch/cygwin/）：
        给 Android libbase/liblog 和 libselinux 的 #if 补上 `|| defined(__CYGWIN__)`，
        以及把 __selinux_once 换成 pthread_once ——
        核心的 fsck/mkfs/dump/lib C 代码**未改动**
                    │  build_cygwin.sh
                    ▼
③  build_cygwin.sh                         构建脚本
    cmake -S ./build/cmake -B ./out -G Ninja \
          -DCMAKE_SYSTEM_NAME="CYGWIN" \
          -DCMAKE_C_COMPILER="x86_64-pc-cygwin-clang" \
          -DCMAKE_CXX_COMPILER="x86_64-pc-cygwin-clang++" \
          -DCMAKE_BUILD_TYPE="Release" -DMAX_BLOCK_SIZE="4096" -DENABLE_FULL_LTO="OFF"
    ninja -C ./out
    cp -af $BUILD/*.erofs.exe $TARGET_DIR_PATH                     # 4 个 exe
    cp -af /usr/x86_64-pc-cygwin/bin/cygwin1.dll $TARGET_DIR_PATH  # 交叉 sysroot 里的运行库
    touch -c -d "2009-01-01 00:00:00" $TARGET_DIR_PATH/*           # 统一时间戳便于比对
    注：CMAKE_SYSTEM_NAME=CYGWIN 会让顶层 CMakeLists 走 CYGWIN 分支，加
        -Wl,-s,-x,--gc-sections（strip + 去死代码）并追加 ext2_uuid/iconv/ntdll
                    │  谁执行？
                    ▼
④  GitHub Actions .github/workflows/build-erofs-utils.yml
    触发：push 到 dev 分支 / 手动 workflow_dispatch
    四个并行 job：Build-android · Build-on-linux · **Build-cygwin** · Build-on-macOS
    Build-cygwin 跑在 ubuntu-latest 上：
        sudo apt install cygwin cygwin-gcc cygwin-libiconv cygwin-xclang cygwin-libc++
        chmod +x build_cygwin.sh && ./build_cygwin.sh
        → 上传 target/Cygwin_x86_64/erofs-utils-v*/
    release job 收集各平台产物并发布 Release
                    ▼
⑤  erofs-utils-v1.8.10-gee46dd74-251217-Cygwin_x86_64.zip   (5 146 583 字节)
    里面就 5 个文件：fsck.erofs.exe · mkfs.erofs.exe · dump.erofs.exe ·
                     extract.erofs.exe · cygwin1.dll
    资产名里的 gee46dd74 = 构建时 git describe 出的上游提交短哈希（exe -V 也这么报）
                    │  tools/fetch_engine.py：查 API 取最新 release →
                    │  挑名字含 Cygwin_x86_64 的资产 → 下载 → 解包
                    ▼
⑥  engine\                                 ← imgtool 用 subprocess 调用：
    参数：--extract=<输出目录> [--offset=N] -d2 <镜像>（路径一律转成正斜杠）
    环境：CYGWIN=winsymlinks:sys（让符号链接落成可读文件而非 WSL 重解析点）
          LC_ALL=C.UTF-8、PATH 前置 engine 目录
    cwd = engine 目录（保证 cygwin1.dll 能被找到）；CREATE_NO_WINDOW 不弹黑框
```

**怎么自己核对**（三层，从轻到重）：

```powershell
.\engine\fsck.erofs.exe -V                    # ① 自报 1.8.10-gee46dd74 + 可用压缩算法
Get-FileHash .\engine\fsck.erofs.exe -Algorithm SHA256   # ② 比对第 3 节的 SHA256 表
python tools\verify_engine_provenance.py      # ③ 23 项审计：对着上游核 tag/资产大小/
                                              #    构建脚本/补丁/CI/上游许可证 + 本地哈希
python tools\verify_engine_provenance.py --offline       # 只校验本地文件（不联网）
```

审计脚本当前 **23 项全部 PASS**。

### 为什么本项目用 0BSD

**0BSD（BSD Zero Clause）是没有附加条件的最宽松许可证**：不需要署名、不需要保留版权声明、
不需要附带许可证文本，商用 / 闭源 / 改名 / 再许可全都可以。

* ✅ **OSI 认证**，FSF 认定为自由软件，且**与 GPL 兼容**——本项目必须与 GPL 兼容，
  因为 `engine\` 里分发的是 `GPL-2.0-or-later` 的二进制，两者要能一起分发。
* ✅ 相比 Unlicense / CC0 这类"放弃版权、进入公有领域"的声明，0BSD 是**标准授权条款**
  而非版权放弃，在中国大陆、德国等不承认"任意放弃著作权"的法域更稳；
  企业法务也普遍接受（不少公司明令禁止 Unlicense，理由是"无法确认已获得授权"）。
* ⚠️ 代价：0BSD **不含专利授权**。若项目涉及专利风险需要明确专利许可，应改用 Apache-2.0
  （但 Apache-2.0 要求署名、标注变更、附带 NOTICE，不如 0BSD 宽松）。

源码文件头部均带 `SPDX-License-Identifier: 0BSD`，便于机器识别。

**分发注意**：`engine\` 里的二进制不是本项目的代码，而是独立程序。本项目通过命令行调用它们，
属于 GPL 意义上的"聚合"。如果你要**分发**这套目录（包括打包成 exe 发布）：

* 保留 `engine\README.md` 与 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 中的
  来源、版本、许可证与源码链接；
* 一并提供 [LICENSES/](LICENSES) 里的许可证全文，以及对应源码的获取方式
  （精确地址见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 第 4 节）；
* 不要声称这些二进制由本项目授权。

只想自己用、或者仓库里只提交 `tools\fetch_engine.py` 让用户自行下载引擎，都没有这些顾虑。

---

## 13 变更记录与致谢

### 变更记录

见 [CHANGELOG.md](CHANGELOG.md)。当前版本 **v0.1.0**。

### 致谢

* [erofs-utils](https://github.com/erofs/erofs-utils) —— EROFS 用户态工具集，本项目的解压引擎
* [sekaiacg/erofs-tools](https://github.com/sekaiacg/erofs-tools) —— 提供 Cygwin/多平台预编译构建
* [Cygwin](https://cygwin.com/) —— 让 Linux 工具在 Windows 上跑起来的兼容层
* EROFS 文件系统本身由华为、阿里等团队贡献给 Linux 内核，现为 Android 只读分区的默认选择

### 贡献

欢迎 Issue / PR。提交前请确保：

```bat
python tests\e2e_test.py            :: 45 项全绿
python tests\gui_test.py            :: PASS
powershell -File tests\launcher_test.ps1
```

并遵守两条硬规矩：**`.bat`/`.cmd` 只用 ASCII + CRLF**；**不要在拖放回调里做重活**。
