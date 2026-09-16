# 第三方组件声明（Third-Party Notices）

本仓库的 `imgtool/`、`tests/`、`tools/`、启动脚本与文档均为本项目原创，采用 **0BSD**
（BSD Zero Clause License，SPDX: `0BSD`）——不需要署名、不需要保留版权声明、没有任何附加条件，
且与 GPL 兼容。许可证全文见 [LICENSE](LICENSE)，第三方许可证全文见 [LICENSES/](LICENSES)。

`engine/` 目录下的可执行文件**不是**本项目的代码，而是独立第三方程序，随本仓库一并分发。
本项目仅通过命令行调用它们（`subprocess` 拉起 `fsck.erofs.exe`），属于 GPL 术语中的
**"聚合"（mere aggregation）**，不是派生作品。清单、来源、构建方式与许可证如下。

---

## 0. 一览表

| 文件 | 许可证（SPDX） | 上游项目 | 完整文本 |
| --- | --- | --- | --- |
| `engine/fsck.erofs.exe` | `GPL-2.0-or-later` | [erofs-utils](https://github.com/erofs/erofs-utils) | [LICENSES/GPL-2.0.txt](LICENSES/GPL-2.0.txt) |
| `engine/mkfs.erofs.exe` | `GPL-2.0-or-later` | 同上 | 同上 |
| `engine/dump.erofs.exe` | `GPL-2.0-or-later` | 同上 | 同上 |
| `engine/extract.erofs.exe` | `GPL-2.0-or-later` | [sekaiacg/erofs-tools](https://github.com/sekaiacg/erofs-tools) | 同上 |
| `engine/cygwin1.dll` | `LGPL-3.0-or-later`（含链接例外） | [Cygwin](https://cygwin.com/) | [LICENSES/LGPL-3.0.txt](LICENSES/LGPL-3.0.txt) + [LICENSES/GPL-3.0.txt](LICENSES/GPL-3.0.txt) |

---

## 1. erofs-utils —— fsck.erofs / mkfs.erofs / dump.erofs

| 项目 | 内容 |
| --- | --- |
| 组件 | `engine\fsck.erofs.exe`、`engine\mkfs.erofs.exe`、`engine\dump.erofs.exe` |
| 上游项目 | <https://github.com/erofs/erofs-utils>（EROFS 文件系统的官方用户态工具集，C 语言） |
| 版本 | **1.8.10**（二进制自报版本号 `1.8.10-gee46dd74`，其中 `gee46dd74` 是构建时的上游提交短哈希） |
| 许可证（SPDX） | **`GPL-2.0-or-later`** |
| 许可证全文 | [LICENSES/GPL-2.0.txt](LICENSES/GPL-2.0.txt) |
| 构建来源 | <https://github.com/sekaiacg/erofs-tools> release `v1.8.10-251217`，资产 `erofs-utils-v1.8.10-gee46dd74-251217-Cygwin_x86_64.zip` |
| 构建方式 | 在 GitHub Actions 的 Ubuntu 构建机上，用 **Cygwin 交叉工具链 `x86_64-pc-cygwin-clang`** + CMake/Ninja 交叉编译（详见 [engine/README.md](engine/README.md)） |

### 许可证说明（重要）

上游 `COPYING` 写明 erofs-utils **使用两套许可**：

* `lib/`、`include/` 目录下的 liberofs 代码：**`GPL-2.0+` 或 `Apache-2.0`**（双许可，二选一）；
* 其余所有文件（含 `fsck/main.c`、`mkfs/main.c`、`dump/main.c`）：**`GPL-2.0+`**。

由于工具入口文件只提供 GPL 选项，链接后的这三个可执行文件整体按
**`GPL-2.0-or-later`** 分发（`+` 即 "or later"，收件人也可以按 GPL-3.0 使用）。

上游原文：<https://github.com/erofs/erofs-utils/blob/v1.8.10/COPYING>

### 校验值

```
erofs-utils-v1.8.10-gee46dd74-251217-Cygwin_x86_64.zip
  bytes  5146583
  sha256 b6a24de0cfe49a95283cf306db1d158bdb63850e0687c8a8b0f4c4a540ba35ba

fsck.erofs.exe   1965568  81890a95aa6e9dd710119b22c674d089a311cd48474d270923873fbc37c05afa
mkfs.erofs.exe   2073600  e2bd628cefd10cc3abca747a65f344b21fc6ce2ae0ec36e5cfb9bc64d521202c
dump.erofs.exe   1964544  85456613664605b40e752fc22eb2a6a24e2966a5c4029af442a52adf7b4286cb
```

---

## 2. extract.erofs（第三方增强工具，本项目暂未使用）

| 项目 | 内容 |
| --- | --- |
| 组件 | `engine\extract.erofs.exe` |
| 来源 | <https://github.com/sekaiacg/erofs-tools> 的 `extract/`（C++ 编写，链接 liberofs） |
| 许可证（SPDX） | `GPL-2.0-or-later`（仓库整体声明 GPL-2.0，且链接了 GPL 的 liberofs） |
| 完整文本 | [LICENSES/GPL-2.0.txt](LICENSES/GPL-2.0.txt) |
| 特殊之处 | 支持按路径选择性解压，并可导出 `fs_config` / `file_contexts` / `mkfs_option`；Cygwin 版额外链接了 `ntdll`（用其接口把目录改为大小写敏感） |
| 本项目是否使用 | **当前未使用**，保留备用（见 README 第 11 节扩展路线） |
| 校验值 | `3077632` 字节，sha256 `d7378ddb500c4338c4ef02f0da7601693a16807faafa453c1dc5750baf3b0dca` |

---

## 3. Cygwin 运行库

| 项目 | 内容 |
| --- | --- |
| 组件 | `engine\cygwin1.dll` |
| 上游项目 | <https://cygwin.com/> |
| 许可证（SPDX） | **`LGPL-3.0-or-later`**（DLL 内代码），另含 **链接例外**；Cygwin 的 `utils/` 等工具为 GPL-3.0+，部分文件为 BSD 类 |
| 完整文本 | [LICENSES/LGPL-3.0.txt](LICENSES/LGPL-3.0.txt)（LGPL-3.0 以 GPL-3.0 为基础，故同时提供 [LICENSES/GPL-3.0.txt](LICENSES/GPL-3.0.txt)） |
| 原始条款 | <https://github.com/cygwin/cygwin/blob/main/winsup/CYGWIN_LICENSE> |
| 源码 | <https://cygwin.com/sources.html> |
| 校验值 | `3012149` 字节，sha256 `ab77212a71c2e2e8b870452d2c32bc72a6708d6e963dd3ebe2ac1a946cffc242` |

### 链接例外（对本项目有利）

`CYGWIN_LICENSE` 原文摘录：

> Linking Exception: As a special exception, the copyright holders of the Cygwin library
> grant you additional permission to link libcygwin.a, crt0.o, and gcrt0.o with independent
> modules to produce an executable, and to convey the resulting executable under terms of
> your choice, without any need to comply with the conditions of LGPLv3 section 4.

也就是说，把 `fsck.erofs.exe` 与 `cygwin1.dll` 一起分发**不会**让本项目代码被迫变成 LGPL；
这几个 exe 的许可证由它们自己的来源（erofs-utils 的 GPL-2.0+）决定。

---

## 4. 对应源码（GPL-2.0 §3 意义上的"相应源码"）

| 用途 | 获取地址 |
| --- | --- |
| **本目录二进制的完整对应源码**（erofs-utils 源码 + 构建脚本 + Cygwin 补丁 + 依赖子模块） | <https://github.com/sekaiacg/erofs-tools/tree/v1.8.10-251217>（commit `7274417816e3adfe0cd6d4a8ff194ec5f41268f4`） |
| 上游 erofs-utils 官方源码 | <https://github.com/erofs/erofs-utils/tree/v1.8.10> |
| Cygwin 源码 | <https://cygwin.com/sources.html> |
| 构建依赖 | lz4 · zstd · xz · zlib(AOSP) · xxHash · libfuse · e2fsprogs(AOSP) · pcre(AOSP) · selinux(sekaiacg 分支) · libcxx(topjohnwu) —— 均在 `v1.8.10-251217` 的 `.gitmodules` 中锁定提交 |

> **注意**：二进制自报的提交短哈希 `gee46dd74` 来自构建当时的 erofs-utils `dev` 分支，
> 而该分支会被维护者 rebase，**这个提交如今在上游已经查不到**。
> 因此追源码请使用上表中 tag 级的地址（`erofs-tools` 的 `v1.8.10-251217` 包含了构建这批
> 二进制时的完整源码树与脚本，是最准确的"相应源码"）。

---

## 5. 分发清单（发布前逐项打勾）

- [ ] `LICENSES/GPL-2.0.txt`、`LICENSES/GPL-3.0.txt`、`LICENSES/LGPL-3.0.txt` 随分发物一起提供
- [ ] `engine/README.md` 与本文档未被删除或改写来源信息
- [ ] 第 4 节的源码获取地址对收件人可见（README / Release 说明里都写上更好）
- [ ] 未修改任何上游源码 —— 若修改过，必须一并提供修改后的源码
- [ ] 未对 GPL 二进制附加额外限制，也未声称它们由本项目授权
- [ ] 若走商业分发，建议直接附带源码压缩包，或提供 GPL-2.0 第 3 节所述的**书面要约**

### 想彻底不背这些义务？

仓库已提供引擎获取脚本，可让使用者自行下载第三方二进制：

```powershell
python tools\fetch_engine.py     # 下载并解包最新 Cygwin x86_64 版 erofs-utils 到 engine\
```

在 `.gitignore` 中取消注释 `/engine/*.exe` 与 `/engine/*.dll` 后，
仓库分发物中将**只包含 0BSD 的本项目源码**，不含任何第三方二进制。
