# engine —— 解压引擎（第三方二进制）

本目录里**没有一行是本项目的代码**。这些是第三方预编译二进制，本项目用命令行调用它们
（`subprocess` 拉起 `fsck.erofs.exe`），属于 GPL 意义上的"聚合"使用。

| 文件 | 作用 | 本项目是否使用 |
| --- | --- | --- |
| `fsck.erofs.exe` | **解压主力**：校验并解压 EROFS 镜像（`--extract=<目录>`） | ✅ 每次解压都用 |
| `dump.erofs.exe` | 打印超级块 / 目录 / inode 信息 | ✅ 识别镜像信息、估算进度 |
| `mkfs.erofs.exe` | 制作 EROFS 镜像 | ✅ 生成测试镜像（`3-制作测试镜像.bat`） |
| `extract.erofs.exe` | 第三方增强解包工具，可导出 `fs_config` / `file_contexts` | ⬜ 暂未使用（预留给选择性解压） |
| `cygwin1.dll` | Cygwin 运行库，**必须与上述 exe 同目录** | ✅ 必需 |

---

## 一句话来历

先分清三方：

| 角色 | 是谁 | 地址 |
| --- | --- | --- |
| **① 官方上游** | **erofs-utils** —— EROFS 文件系统的官方用户态工具集（`fsck` / `mkfs` / `dump` / `fuse` 全部源码） | 主开发树 <https://git.kernel.org/pub/scm/linux/kernel/git/xiang/erofs-utils.git>；官方 GitHub 镜像 <https://github.com/erofs/erofs-utils> |
| **② 第三方构建工程** | **sekaiacg/erofs-tools** —— 个人维护的打包/构建工程，**不是**官方发行渠道，只负责把 ① 编成各平台成品 | <https://github.com/sekaiacg/erofs-tools> |
| **③ 本项目** | **imgtool** —— 下载 ② 的 Windows 成品并调用 | <https://github.com/littlecoca/erofs_tool_win> |

**一句话**：本目录的 `.exe` 是**官方 erofs-utils（①）的源码**，
被**第三方构建工程 sekaiacg/erofs-tools（②）**在 **GitHub Actions 的 Ubuntu 机器**上，
用**目标平台为 Cygwin 的 Clang 交叉编译器**（`x86_64-pc-cygwin-clang`）**交叉编译**出来的
Windows 可执行文件；本项目（③）下载成品并用 `subprocess` 调用。

这几个 `.exe` **从未在 Windows 上编译过** —— 编译它们的是 Linux，只是目标平台设成了 Cygwin。

```
① erofs/erofs-utils       上游 C 源码（GPL-2.0-or-later）
      │  源码 + 11 个依赖（submodule 锁定提交）
      ▼
② sekaiacg/erofs-tools    构建工程（GPL-2.0）
      · CMake 目标：file(GLOB fsck/*.c) → add_executable(fsck.erofs …)
        liberofs 与 lz4/lzma/zlib/zstd/pcre2/xxhash/selinux 全部静态链接
      · 4 个 Cygwin 兼容补丁（都在依赖库上，核心 C 代码未改动）
      · build_cygwin.sh：CMAKE_SYSTEM_NAME=CYGWIN + x86_64-pc-cygwin-clang + Ninja
      │  在 GitHub Actions 的 ubuntu-latest 上执行
      │  （apt install cygwin cygwin-gcc cygwin-libiconv cygwin-xclang cygwin-libc++）
      ▼
   erofs-utils-v1.8.10-gee46dd74-251217-Cygwin_x86_64.zip
      │  = 4 个 exe + 交叉 sysroot 里的 cygwin1.dll
      ▼
③ tools\fetch_engine.py 下载解包 → engine\ → imgtool 用 subprocess 调用
```

👉 **完整链路（每个依赖的锁定提交、CMake 原文、补丁内容、CI 步骤、自己重编的三种方式、
常见疑问、术语表）见 [docs/ENGINE_PROVENANCE.md](../docs/ENGINE_PROVENANCE.md)。**

---

## 版本与校验值

对应 [sekaiacg/erofs-tools](https://github.com/sekaiacg/erofs-tools) 的 release
**`v1.8.10-251217`**（tag 提交 `7274417816e3adfe0cd6d4a8ff194ec5f41268f4`），
上游版本 erofs-utils **1.8.10**（二进制自报 `1.8.10-gee46dd74`）。

| 文件 | 字节 | SHA256 |
| --- | --- | --- |
| `erofs-utils-v1.8.10-gee46dd74-251217-Cygwin_x86_64.zip` | 5 146 583 | `b6a24de0cfe49a95283cf306db1d158bdb63850e0687c8a8b0f4c4a540ba35ba` |
| `fsck.erofs.exe` | 1 965 568 | `81890a95aa6e9dd710119b22c674d089a311cd48474d270923873fbc37c05afa` |
| `mkfs.erofs.exe` | 2 073 600 | `e2bd628cefd10cc3abca747a65f344b21fc6ce2ae0ec36e5cfb9bc64d521202c` |
| `dump.erofs.exe` | 1 964 544 | `85456613664605b40e752fc22eb2a6a24e2966a5c4029af442a52adf7b4286cb` |
| `extract.erofs.exe` | 3 077 632 | `d7378ddb500c4338c4ef02f0da7601693a16807faafa453c1dc5750baf3b0dca` |
| `cygwin1.dll` | 3 012 149 | `ab77212a71c2e2e8b870452d2c32bc72a6708d6e963dd3ebe2ac1a946cffc242` |

> 资产名里的 `gee46dd74` 是构建时 `git describe` 得到的上游提交短哈希。
> erofs-utils 的 `dev` 分支会被维护者 rebase，**该提交如今在上游已查不到**；
> 追源码请用上面的 tag 地址。

---

## 自己验证

```powershell
.\engine\fsck.erofs.exe -V                           # 自报版本与可用压缩算法
python tools\verify_engine_provenance.py             # 23 项审计：本地 SHA256 + 上游 tag/脚本/补丁/CI/许可证
python tools\verify_engine_provenance.py --offline   # 只校验本地文件（不联网）
python tools\probe_pe.py engine\fsck.erofs.exe       # 拆开 exe：PE 头 / 导入表 / 编译器指纹
python tools\smoke_engine.ps1                        # 最小闭环：mkfs → fsck → 比 SHA256
```

---

## 许可证与源码

| 组件 | 许可证（SPDX） | 完整文本 |
| --- | --- | --- |
| `fsck.erofs.exe`、`mkfs.erofs.exe`、`dump.erofs.exe` | `GPL-2.0-or-later` | [`LICENSES/GPL-2.0.txt`](../LICENSES/GPL-2.0.txt) |
| `extract.erofs.exe` | `GPL-2.0-or-later` | 同上 |
| `cygwin1.dll` | `LGPL-3.0-or-later`（含链接例外） | [`LICENSES/LGPL-3.0.txt`](../LICENSES/LGPL-3.0.txt) + [`LICENSES/GPL-3.0.txt`](../LICENSES/GPL-3.0.txt) |

* erofs-utils 的 `lib/`、`include/` 为 `GPL-2.0+ OR Apache-2.0` 双许可，其余文件为 `GPL-2.0+`；
  链接后的可执行文件整体按 `GPL-2.0-or-later` 分发。
* Cygwin 的**链接例外**明确允许把 `libcygwin.a` / `crt0.o` 与独立模块链接，
  生成的程序可按你自己的条款分发。

**对应源码（GPL-2.0 §3 意义上的"相应源码"）**：

| 用途 | 地址 |
| --- | --- |
| 本目录二进制的完整对应源码（含构建脚本与补丁） | <https://github.com/sekaiacg/erofs-tools/tree/v1.8.10-251217> |
| 上游 erofs-utils 官方源码 | <https://github.com/erofs/erofs-utils/tree/v1.8.10> |
| Cygwin 源码 | <https://cygwin.com/sources.html> |

分发义务清单见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) 与 [LICENSE](../LICENSE)。

---

## 重新获取 / 升级引擎

```powershell
python tools\fetch_engine.py      # 自动挑最新 Cygwin_x86_64 资产并解包到本目录
```

升级后请重跑验收，并同步更新本文与 `docs/ENGINE_PROVENANCE.md` 里的版本/校验值表格：

```bat
python tools\verify_engine_provenance.py
powershell -File tests\run_all.ps1
```

---

## 这套引擎实测能做到什么

**已实测通过**（见 `tests/e2e_test.py`，45 项断言）：

* 压缩算法：不压缩 / `lz4` / `lz4hc` / `lzma` / `deflate` / `zstd`
* 布局选项：`-C65536` 分簇、`-Ededupe` 内容去重、`--all-root`、`-Eztailpacking`
* 符号链接（相对 / 绝对 / 悬空 / 指向目录）、硬链接、中文与空格文件名、
  只读与私有权限位、空目录、空文件
* 96 MB 镜像解压约 520 MB/s（lz4）

**未实测**（不是"不支持"，而是本机造不出样本）：

* `-Efragments`、`-m4096` 元数据压缩、`--zD` 目录压缩、`--chunksize` 分块化
  —— Cygwin 版 `mkfs.erofs` 生成这几类镜像时依赖 Linux 专有接口、会报
  `failed to initialize packedfile/metadata`；解压这类真机镜像由上游 `fsck.erofs` 负责，
  理论上支持，但本项目没有验证过。
* 设备节点 / FIFO 只能写成 `.lnk` 占位文件（NTFS 限制）。
