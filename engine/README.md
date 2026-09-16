# engine —— 解压引擎：这些 `.exe` 是怎么来的

本目录里**没有一行是本项目的代码**，全部是第三方预编译二进制。
本项目只是用命令行调用它们（`subprocess` 拉起 `fsck.erofs.exe`），属于 GPL 意义上的
"聚合"使用。本文把每个文件的来历、版本、构建方式、校验值和源码获取点写清楚。

| 文件 | 作用 | 本项目是否使用 |
| --- | --- | --- |
| `fsck.erofs.exe` | **解压主力**：校验并解压 EROFS 镜像（`--extract=<目录>`） | ✅ 每次解压都用 |
| `dump.erofs.exe` | 打印超级块 / 目录 / inode 信息 | ✅ 识别镜像信息、估算进度 |
| `mkfs.erofs.exe` | 制作 EROFS 镜像 | ✅ 生成测试镜像（`3-制作测试镜像.bat`） |
| `extract.erofs.exe` | sekaiacg 自研的解包工具，可导出 `fs_config` / `file_contexts` / `mkfs_option` | ⬜ 暂未使用（预留：选择性解压） |
| `cygwin1.dll` | Cygwin 运行库，**必须与上述 exe 放在同一目录** | ✅ 必需 |

---

## 1. 一句话来历

> 官方 EROFS 用户态工具集 **erofs-utils** 的源码，
> 由第三方构建项目 **sekaiacg/erofs-tools** 在 **GitHub Actions 的 Ubuntu 构建机**上、
> 用 **Cygwin 交叉工具链（`x86_64-pc-cygwin-clang`）+ CMake/Ninja** **交叉编译**成
> Windows 可执行文件，连同交叉环境里的 `cygwin1.dll` 一起打包成 zip
> 发布在 GitHub Releases；本项目下载其中 `Cygwin_x86_64` 那个资产并解包到本目录。

> 值得强调：这几个 `.exe` **从未在 Windows 上编译过**，
> 而是在 Linux 上由"目标平台为 Cygwin 的 Clang"交叉编译出来的 Windows PE 文件。

---

## 2. 完整构建链路（可逐环验证）

```
① 上游源码
   erofs/erofs-utils  ——  EROFS 文件系统的用户态工具集，C 语言
       fsck/main.c    → fsck.erofs（校验/解压）
       mkfs/main.c    → mkfs.erofs（造镜像）
       dump/main.c    → dump.erofs（打印元数据）
       lib/、include/ ——  公共库 liberofs（lz4/lzma/deflate/zstd 解码、inode、xattr…）
       ↑ 这些文件头部写着 SPDX-License-Identifier: GPL-2.0+ (lib/include 另有 OR Apache-2.0)

② 构建项目
   sekaiacg/erofs-tools  ——  第三方构建工程（仓库声明 GPL-2.0），做的事包括：
       · 把 erofs-utils 及全部依赖以 git submodule / 源码树方式收进来并锁定提交：
           erofs-utils  7db78788…（上游 dev 分支）      lz4      0774d055…
           zstd         82d322c4…                      xz       c8b8ab2e…
           zlib         b6a40b22…（AOSP 版）           xxHash / libfuse / e2fsprogs
           pcre / selinux（sekaiacg 的 AOSP 分支）/ libcxx（topjohnwu 版）
       · 用 CMake 组织编译（`cmake/check.cmake` 探测编译器支持哪些 flag，
         `cmake/patch.cmake` 用 patch 命令给依赖打补丁）
       · 为每个平台写一份构建脚本：build_cygwin.sh / build_darwin.sh / build.sh …

③ 构建定义：fsck.erofs 这个目标是怎么定义的
   build/cmake/erofs-tools/erofs_tools.cmake 就是三个 exe 的诞生处：
       set(common_static_link_lib
           dl erofs_static cutils base log selinux
           lz4_static liblzma z_static libzstd_static pcre2 xxhash)
       if (CMAKE_SYSTEM_NAME MATCHES "Darwin|CYGWIN")
           list(APPEND common_static_link_lib "ext2_uuid" "iconv")
       endif ()
       if (CYGWIN)
           # extract.erofs 用 ntdll 的函数把目录改成大小写敏感，所以要链 ntdll
           list(APPEND common_static_link_lib "ntdll")
       endif ()

       set(TARGET_fsck fsck.erofs)
       file(GLOB fsck_srcs "${PROJECT_ROOT_DIR}/fsck/*.c")
       add_executable(${TARGET_fsck} ${fsck_srcs})
       target_link_libraries(${TARGET_fsck} ${common_static_link_lib})
   要点：`fsck/*.c` 全部源文件编成一个可执行文件，并把
   **liberofs、lz4、xz(lzma)、zlib、zstd、pcre2、xxhash、selinux、libcutils、libbase、liblog
   全部当静态库链进去** —— 这就是为什么单个 exe 只有 ~2 MB 却什么压缩算法都能解，
   运行时除了 `cygwin1.dll` 不依赖任何其它 DLL。

④ Cygwin 构建脚本
   build_cygwin.sh 关键内容：
       cmake -S ./build/cmake -B ./out -G Ninja \
             -DCMAKE_SYSTEM_NAME="CYGWIN" \
             -DCMAKE_BUILD_TYPE="Release" \
             -DCMAKE_C_COMPILER="x86_64-pc-cygwin-clang" \
             -DCMAKE_CXX_COMPILER="x86_64-pc-cygwin-clang++" \
             -DCMAKE_C_COMPILER_LAUNCHER="ccache" \
             -DENABLE_FULL_LTO="OFF" \
             -DMAX_BLOCK_SIZE="4096"
       ninja -C ./out
       # 然后：
       cp -af $BUILD/*.erofs.exe        $TARGET_DIR_PATH   # 四个 exe
       cp -af /usr/x86_64-pc-cygwin/bin/cygwin1.dll $TARGET_DIR_PATH
       touch -c -d "2009-01-01 00:00:00" $TARGET_DIR_PATH/*  # 统一时间戳
   要点：
       · 编译器是 **Cygwin 目标的 Clang**（`x86_64-pc-cygwin-clang`），不是 MSVC，也不是 MinGW
       · 构建系统 CMake + Ninja，Release 优化，`MAX_BLOCK_SIZE=4096`
       · `cygwin1.dll` 直接取自交叉工具链 sysroot 里的 `/usr/x86_64-pc-cygwin/bin/`
       · 顶层 CMakeLists 里有专门的 CYGWIN 分支：`-Wl,-s,-x,--gc-sections`（strip + 去死代码）
       · 对 libbase / liblog / libselinux 打了少量 **Cygwin 兼容补丁**，
         补丁文件公开在 `build/cmake/lib/patch/cygwin/*.patch`

⑤ CI：谁在跑这套构建
   .github/workflows/build-erofs-utils.yml（push 到 dev 分支或手动触发）
       四个并行 job：Build-android / Build-on-linux / **Build-cygwin** / Build-on-macOS
       Build-cygwin 这个 job 干的事：
         · 在 ubuntu-latest 上从社区仓库装交叉工具链：
             sudo apt install cygwin cygwin-gcc cygwin-libiconv cygwin-xclang cygwin-libc++
         · chmod +x build_cygwin.sh && ./build_cygwin.sh
         · 上传产物到 target/Cygwin_x86_64/erofs-utils-v*/
       最后 release job 收集各平台产物，用 workflow_dispatch 发布成 GitHub Release

⑥ 发布
   产物打成 `erofs-utils-<版本>-<yymmdd>-<平台>_<架构>.zip`，
   作为 GitHub Release 资产发布（同一版本会同时发 Android / Linux / Darwin /
   Cygwin / WSL 等多个平台）

⑦ 本项目取用
   下载 Cygwin_x86_64 那个 zip → 解包到 engine\ → 用 tools\fetch_engine.py
   可自动完成（自动挑最新 Cygwin_x86_64 资产）
```

### 为什么是一个 exe + 一个 DLL

exe 是标准的 Windows PE 可执行文件，但它链接的是 **Cygwin 的 POSIX 运行库**：
文件操作、符号链接、权限、`fork` 等系统调用都由 `cygwin1.dll` 提供。
压缩算法（lz4 / lzma / deflate / zstd）则是**静态编进 exe** 的
（依赖都以 submodule 形式源码内联），所以单个 exe 只有 ~2 MB，
运行时唯一的外部依赖就是同目录的 `cygwin1.dll`。

---

## 3. 版本与校验值

本文档对应的引擎来自
[sekaiacg/erofs-tools](https://github.com/sekaiacg/erofs-tools) 的 release
**`v1.8.10-251217`**（2025-12-17 发布），资产名
`erofs-utils-v1.8.10-gee46dd74-251217-Cygwin_x86_64.zip`。

| 文件 | 字节 | SHA256 |
| --- | --- | --- |
| `erofs-utils-v1.8.10-gee46dd74-251217-Cygwin_x86_64.zip` | 5 146 583 | `b6a24de0cfe49a95283cf306db1d158bdb63850e0687c8a8b0f4c4a540ba35ba` |
| `fsck.erofs.exe` | 1 965 568 | `81890a95aa6e9dd710119b22c674d089a311cd48474d270923873fbc37c05afa` |
| `mkfs.erofs.exe` | 2 073 600 | `e2bd628cefd10cc3abca747a65f344b21fc6ce2ae0ec36e5cfb9bc64d521202c` |
| `dump.erofs.exe` | 1 964 544 | `85456613664605b40e752fc22eb2a6a24e2966a5c4029af442a52adf7b4286cb` |
| `extract.erofs.exe` | 3 077 632 | `d7378ddb500c4338c4ef02f0da7601693a16807faafa453c1dc5750baf3b0dca` |
| `cygwin1.dll` | 3 012 149 | `ab77212a71c2e2e8b870452d2c32bc72a6708d6e963dd3ebe2ac1a946cffc242` |

资产名里的 `gee46dd74` 是构建时 `git describe` 得到的上游提交短哈希
（二进制 `-V` 也会打印 `1.8.10-gee46dd74`）。
注意：erofs-utils 的 `dev` 分支会被维护者 rebase，**这个提交如今在上游已经查不到了**，
所以追源码请用下面的 tag 级地址（见第 5 节）。

---

## 4. 自己验证一遍

```powershell
# 版本与可用压缩算法
.\engine\fsck.erofs.exe -V
.\engine\fsck.erofs.exe --help

# 校验值对不上就说明文件被换过/下载损坏
Get-FileHash .\engine\fsck.erofs.exe -Algorithm SHA256

# 最小闭环：造镜像 → 解压 → 比 SHA256（需要 Python）
python tools\smoke_engine.ps1
python tools\probe_engine.py     # 更全面地探测引擎能力
```

---

## 5. 许可证与源码获取点

| 组件 | 许可证（SPDX） | 完整文本 |
| --- | --- | --- |
| `fsck.erofs.exe`、`mkfs.erofs.exe`、`dump.erofs.exe` | `GPL-2.0-or-later` | [`LICENSES/GPL-2.0.txt`](../LICENSES/GPL-2.0.txt) |
| `extract.erofs.exe` | `GPL-2.0-or-later` | [`LICENSES/GPL-2.0.txt`](../LICENSES/GPL-2.0.txt) |
| `cygwin1.dll` | `LGPL-3.0-or-later`（含链接例外） | [`LICENSES/LGPL-3.0.txt`](../LICENSES/LGPL-3.0.txt) + [`LICENSES/GPL-3.0.txt`](../LICENSES/GPL-3.0.txt) |

* erofs-utils 的 `lib/`、`include/` 是 **GPL-2.0+ 或 Apache-2.0 双许可**，
  其余文件是 **GPL-2.0+**；因为 `fsck/main.c` 等只给 GPL 选项，
  链接后的可执行文件整体按 **GPL-2.0-or-later** 分发。
  上游 `COPYING` 原文见 <https://github.com/erofs/erofs-utils/blob/v1.8.10/COPYING>。
* Cygwin 运行库的许可见 `winsup/CYGWIN_LICENSE`：DLL 内代码为 **LGPLv3+**，
  并附带**链接例外**——允许把 `libcygwin.a`、`crt0.o`、`gcrt0.o` 与独立模块链接，
  生成的程序可按你自己的条款分发。
  <https://github.com/cygwin/cygwin/blob/main/winsup/CYGWIN_LICENSE>

### 对应源码（GPL-2.0 §3 意义上的"相应源码"获取点）

| 用途 | 地址 |
| --- | --- |
| 本目录二进制的**完整对应源码**（含 erofs-utils 源码 + 构建脚本 + Cygwin 补丁） | <https://github.com/sekaiacg/erofs-tools/tree/v1.8.10-251217> （commit `7274417816e3adfe0cd6d4a8ff194ec5f41268f4`） |
| 上游 erofs-utils 官方源码 | <https://github.com/erofs/erofs-utils/tree/v1.8.10> |
| 构建依赖（子模块，构建时按提交锁定） | lz4 · zstd · xz · zlib(AOSP) · xxHash · libfuse · e2fsprogs(AOSP) · pcre(AOSP) · selinux(sekaiacg) |
| Cygwin 源码 | <https://cygwin.com/sources.html> |

> 分发本目录（含打包成 exe 发布）时的义务清单见
> [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) 与 [LICENSE](../LICENSE)。
> 一句话：附上 `LICENSES/` 里的许可证全文 + 上面这几条源码地址，别删来源声明。

---

## 6. 重新获取 / 升级引擎

```powershell
python tools\fetch_engine.py      # 自动挑最新 Cygwin_x86_64 资产并解包到本目录
```

升级后请重新跑一次验收，并同步更新本文件的版本与校验值表格：

```bat
powershell -File tests\run_all.ps1
```

---

## 7. 这套引擎实测能做到什么

**已实测通过**（见 `tests/e2e_test.py`，45 项断言）：

* 压缩算法：不压缩 / `lz4` / `lz4hc` / `lzma` / `deflate` / `zstd`
* 布局选项：`-C65536` 分簇、`-Ededupe` 内容去重、`--all-root`、`-Eztailpacking`
* 符号链接（相对 / 绝对 / 悬空 / 指向目录）、硬链接、中文与空格文件名、
  只读与私有权限位、空目录、空文件
* 96 MB 镜像解压约 520 MB/s（lz4）

**未实测**（不是"不支持"，而是本机造不出样本）：

* `-Efragments`、`-m4096` 元数据压缩、`--zD` 目录压缩、`--chunksize` 分块化
  —— Cygwin 版 `mkfs.erofs` 生成这几类镜像时会报
  `failed to initialize packedfile/metadata`（依赖 Linux 专有接口）；
  解压这类真机镜像由上游 `fsck.erofs` 负责，理论上支持，但没有验证过。
* 设备节点 / FIFO 只能写成 `.lnk` 占位文件（NTFS 限制）。
