# 引擎来历：`engine\*.exe` 是怎么造出来的

> 本文回答一个问题：仓库里 `engine\` 下的 `fsck.erofs.exe`、`mkfs.erofs.exe`、
> `dump.erofs.exe`、`extract.erofs.exe`、`cygwin1.dll` **到底从哪来、谁编的、怎么编的、
> 怎么核对**。
>
> 读完之后你应该能：独立复核每一个结论、从源码自己重编一份、知道分发时要履行什么义务。

**目录**

- [1 一句话结论](#1-一句话结论)
- [2 九个环节](#2-九个环节)
  - [2.1 第 1 环 上游源码 erofs-utils](#21-第-1-环-上游源码-erofs-utils)
  - [2.2 第 2 环 构建工程 erofs-tools](#22-第-2-环-构建工程-erofs-tools)
  - [2.3 第 3 环 构建定义 三个 exe 的诞生处](#23-第-3-环-构建定义-三个-exe-的诞生处)
  - [2.4 第 4 环 Cygwin 兼容补丁](#24-第-4-环-cygwin-兼容补丁)
  - [2.5 第 5 环 构建脚本 build_cygwin.sh](#25-第-5-环-构建脚本-build_cygwinsh)
  - [2.6 第 6 环 CI 谁在跑构建](#26-第-6-环-ci-谁在跑构建)
  - [2.7 第 7 环 发布资产](#27-第-7-环-发布资产)
  - [2.8 第 8 环 本项目取用](#28-第-8-环-本项目取用)
  - [2.9 第 9 环 运行期调用](#29-第-9-环-运行期调用)
  - [2.10 第 10 环 CMake 到底是怎么编出 exe 的](#210-第-10-环-cmake-到底是怎么编出-exe-的)
- [3 版本与校验值](#3-版本与校验值)
- [4 自己验证](#4-自己验证)
- [5 从源码自己编一份](#5-从源码自己编一份)
- [6 常见疑问](#6-常见疑问)
- [7 许可证与分发](#7-许可证与分发)
- [8 术语表](#8-术语表)

---

## 1 一句话结论

先分清三方：

| 角色 | 是谁 | 地址 | 职责 |
| --- | --- | --- | --- |
| **① 官方上游** | **erofs-utils** —— EROFS 文件系统的**官方用户态工具集** | 主开发树 <https://git.kernel.org/pub/scm/linux/kernel/git/xiang/erofs-utils.git><br>官方 GitHub 镜像 <https://github.com/erofs/erofs-utils> | 提供 `fsck.erofs` / `mkfs.erofs` / `dump.erofs` / `erofsfuse` 的**全部源码**（纯 C） |
| **② 第三方构建工程** | **sekaiacg/erofs-tools** —— 个人维护的打包/构建工程，**不是** erofs-utils 的官方发行渠道 | <https://github.com/sekaiacg/erofs-tools> | **不写文件系统代码**，只把 ① 的源码连同依赖编成各平台成品并发布 Release |
| **③ 本项目** | **imgtool** | <https://github.com/littlecoca/erofs_tool_win> | 下载 ② 的 Windows 成品，套一层 GUI / CLI |

> **一句话**：`engine\` 里的 `.exe`，是**官方项目 erofs-utils（①）的源码**，
> 被**第三方构建工程 sekaiacg/erofs-tools（②）**在
> **GitHub Actions 的 Ubuntu 构建机**上，用**目标平台为 Cygwin 的 Clang 交叉编译器**
> （`x86_64-pc-cygwin-clang`）**交叉编译**成的 Windows PE 可执行文件，
> 连同交叉环境里的 `cygwin1.dll` 一起打包发布；本项目（③）下载成品并调用。

> ### 谁编译的？——② 编译的，本项目一个 exe 都没编
>
> **本项目（imgtool）从来不编译任何 `.exe`**，只做两件事：用 `tools/fetch_engine.py`
> 把 ② 发布好的 zip 下载解包到 `engine\`，运行时用 `subprocess` 调用它。
> 本项目自己"产出"的只有 Python/GUI 代码、文档，以及测试用的 `.img` 镜像
> （那些镜像确实是用引擎里的 `mkfs.erofs.exe` 生成的，但那是**使用**引擎，不是**构建**引擎）。
>
> **三条可自行核对的证据**：
>
> 1. **PE 链接时间戳**：4 个 exe 分别是
>    `2025-12-17 11:11:54 / 11:11:54 / 11:11:54 / 11:11:56 UTC`（同一次 CI 构建连续链出）；
>    而该 Release 的资产上传时间是 `2025-12-17 11:15:01 UTC` —— 相隔约 3 分钟，
>    正是 CI 流水线"编译 → 上传产物 → 发布 Release"的正常节奏。
> 2. **本机没有任何 C/C++ 编译器**：`gcc` / `clang` / `make` / `cmake` / `ninja` 全部不存在，
>    物理上不可能在本机编出这些 exe。
> 3. **本仓库没有任何引擎构建脚本**：`git ls-files` 里找不到 CMakeLists / Makefile /
>    `build_cygwin.sh`；`build_cygwin.sh` 只存在于 ② 的仓库里。
>
> 验证命令：
>
> ```powershell
> python tools\probe_pe.py engine\fsck.erofs.exe        # 看链接时间戳、导入表、是否 strip
> Get-Command gcc,clang,make,cmake,ninja                 # 全部报"找不到"
> git ls-files | Select-String 'cmake|Makefile|\.sh$'    # 没有任何构建脚本
> ```
>
> 顺带一提：`cygwin1.dll` 的链接时间戳是 `2024-04-03 17:33:10 UTC` —— 比那几个 exe 早了一年多，
> 因为它是 **Cygwin 官方运行库**，由 Cygwin 项目自己在 2024 年编好，
> ② 只是把它从交叉工具链的 sysroot 里**拷**进了发布包，并没有编译它。

**这几个 exe 从来没有在 Windows 上编译过。** 编译它们的是 Linux，
只是"目标平台"被设置成了 Cygwin —— 详见 [2.5 构建脚本](#25-第-5-环-构建脚本-build_cygwinsh)。

② 的构建过程可以概括成四步，后面九个小节逐环展开：

| 步骤 | 做什么 | 关键文件 / 命令 | 详见 |
| --- | --- | --- | --- |
| 1 收源码 | 把 ① 的 erofs-utils 和 11 个依赖以 submodule 收进仓库并锁定提交 | `.gitmodules` | [2.2](#22-第-2-环-构建工程-erofs-tools) |
| 2 定目标 | 用 CMake 声明 `fsck.erofs` / `mkfs.erofs` / `dump.erofs` 三个可执行目标，依赖全部静态链接 | `build/cmake/erofs-tools/erofs_tools.cmake` | [2.3](#23-第-3-环-构建定义-三个-exe-的诞生处) |
| 3 交叉编译 | 在 Ubuntu 上装 Cygwin 交叉工具链，`CMAKE_SYSTEM_NAME=CYGWIN` + `x86_64-pc-cygwin-clang`，Ninja 编译 | `build_cygwin.sh` | [2.5](#25-第-5-环-构建脚本-build_cygwinsh) · [2.6](#26-第-6-环-ci-谁在跑构建) |
| 4 打包发布 | 4 个 exe + 交叉 sysroot 里的 `cygwin1.dll` → zip → GitHub Release | `erofs-utils-…-Cygwin_x86_64.zip` | [2.7](#27-第-7-环-发布资产) |

---

## 2 九个环节

### 2.1 第 1 环 上游源码 erofs-utils

| 项 | 内容 |
| --- | --- |
| 仓库 | <https://github.com/erofs/erofs-utils> |
| 是什么 | EROFS（Enhanced Read-Only File System）文件系统的**用户态工具集**，纯 C |
| EROFS 用在哪 | Android 手机的 `system`/`vendor`/`product` 分区、容器镜像、只读 rootfs —— 只读、可压缩、元数据不压缩 |
| 版本 | 本引擎基于 **1.8.10** |
| 许可证 | `lib/`、`include/`：`GPL-2.0+ OR Apache-2.0`（双许可）；其余文件：`GPL-2.0+` |
| 依赖 | lz4、xz(liblzma)、zlib、libdeflate、zstd、xxHash、libuuid(e2fsprogs)、libselinux、libfuse（仅 Linux/Android 用于 `erofsfuse`） |

它提供四个程序，本项目只用到前三个：

| 程序 | 源文件 | 干什么 |
| --- | --- | --- |
| `mkfs.erofs` | `mkfs/*.c` | 把目录/tar 打成 EROFS 镜像 |
| `fsck.erofs` | `fsck/*.c` | 校验镜像**并解压**（`--extract=<目录>`）——本项目的解压主力 |
| `dump.erofs` | `dump/*.c` | 打印超级块/目录/inode 信息 |
| `erofsfuse` | `fuse/*.c` | 用 FUSE 挂载镜像（Windows 上没意义，本项目不用） |

### 2.2 第 2 环 构建工程 erofs-tools

上游 erofs-utils 提供的是 autotools（`autogen.sh` → `configure` → `make`）流程，
在 Windows/Cygwin 上跑得起来但很别扭，而且没有现成的 Windows 发行包。
[sekaiacg/erofs-tools](https://github.com/sekaiacg/erofs-tools)（仓库声明 GPL-2.0）做了三件事：

1. **把源码和依赖全部收进来并锁定提交**。它的 `.gitmodules` 里有 11 个子模块：

   | 依赖 | 仓库 | 用途 |
   | --- | --- | --- |
   | `erofs-utils` | erofs/erofs-utils（dev 分支） | 主角 |
   | `lz4` / `zstd` / `xz` / `zlib` | lz4 · facebook/zstd · tukaani/xz · AOSP zlib | 四种压缩算法 |
   | `xxHash` | Cyan4973/xxHash | `-Ededupe` 去重 |
   | `libfuse` | sekaiacg 分支 | `erofsfuse`（非 Cygwin 平台） |
   | `e2fsprogs` | AOSP | libuuid |
   | `pcre` | AOSP | SELinux 上下文正则 |
   | `selinux` | sekaiacg 的 AOSP 分支 | `--file-contexts` 的 SELinux 标签 |
   | `libcxx` | topjohnwu/libcxx | Android 平台的 C++ 运行库 |

2. **写一套 CMake 构建系统**（`build/cmake/`），替代 autotools：
   `check.cmake` 探测编译器支持哪些 flag，`lib/*.cmake` 逐个描述依赖库怎么编，
   `patch/*.patch` 给不兼容的平台打补丁。
3. **为每个平台写一份构建脚本**：`build_cygwin.sh`、`build_darwin.sh`、`build.sh` 等，
   再由 GitHub Actions 在各平台环境里执行。

> 仓库在 2025-12（本引擎那个 tag）时的布局是：erofs-utils 源码直接放在仓库根
> （`fsck/ mkfs/ dump/ lib/ include/`）+ `build/cmake/` + `extract/`（自研工具）。
> 之后再重构成了 `src/lib/erofs-utils` 子模块的布局 —— 两种布局都存在过，
> 引用时请注意 tag。

### 2.3 第 3 环 构建定义 三个 exe 的诞生处

`build/cmake/erofs-tools/erofs_tools.cmake` 就是这三个 exe 的诞生处（原文节选）：

```cmake
set(common_static_link_lib
    ${ld_start_group}
    dl erofs_static cutils base log selinux
    lz4_static liblzma z_static libzstd_static pcre2 xxhash
    ${ld_end_group})

if (CMAKE_SYSTEM_NAME MATCHES "Darwin|CYGWIN")
    list(APPEND common_static_link_lib "ext2_uuid" "iconv")
endif ()

if (CYGWIN)
    # extract.erofs 用 ntdll 的函数把目录改成大小写敏感，所以要链 ntdll
    list(APPEND common_static_link_lib "ntdll")
endif ()

###############################------fsck.erofs------###############################
set(TARGET_fsck fsck.erofs)
file(GLOB fsck_srcs "${PROJECT_ROOT_DIR}/fsck/*.c")
add_executable(${TARGET_fsck} ${fsck_srcs})
target_include_directories(${TARGET_fsck} PRIVATE ${common_headers})
target_link_libraries(${TARGET_fsck} ${common_static_link_lib})
target_compile_options(${TARGET_fsck} PRIVATE ${common_compile_flags})
##################################################################################
```

`mkfs.erofs` 与 `dump.erofs` 是同样的写法，只是把 `fsck/*.c` 换成 `mkfs/*.c`、`dump/*.c`。

**两个关键结论：**

* `file(GLOB fsck/*.c)` 意味着 `fsck/` 下所有 C 文件（`main.c`、`namei.c`、`rebuild.c`…）
  编成同一个可执行文件 —— 所以 `fsck.erofs.exe` 就是上游 `fsck.erofs` 本体，不是简化版。
* **所有依赖都是静态链接**（`erofs_static`、`lz4_static`、`liblzma`、`z_static`、
  `libzstd_static`、`pcre2`、`xxhash`、`selinux`、`cutils`、`base`、`log`…）——
  这就是为什么单个 exe 只有 ~2 MB 却支持全部压缩算法，而运行时除了 `cygwin1.dll`
  不依赖任何其它 DLL。
* Cygwin 平台**额外多链三个库**：`ext2_uuid`（libuuid，mkfs 生成 UUID 用）、
  `iconv`、`ntdll`。

### 2.4 第 4 环 Cygwin 兼容补丁

在 `build/cmake/lib/patch/cygwin/` 下有 4 个补丁，都是**可移植性守卫**级别的小改动，
作用是让依赖库里那些"只判断了 Linux / MinGW"的 `#if` 也认 Cygwin：

| 补丁 | 改的地方 | 改法 |
| --- | --- | --- |
| `0001-Cygwin-libbase-Add-cygwin-flags.patch` | Android `libbase` 的 `file.cpp`（`Realpath`）、`threads.cpp`（`GetThreadId`） | `#if defined(__linux__)` → `#if defined(__linux__) \|\| defined(__CYGWIN__)` |
| `0001-Cygwin-liblog-Add-cygwin-flags.patch` | Android `liblog` 的 `logger_write.cpp` | `#elif defined(_WIN32)` → `#elif defined(_WIN32) \|\| defined(__CYGWIN__)` |
| `0001-Cygwin-libselinux-Replace-__selinux_once-to-__pthrea.patch` | libselinux | 把 `__selinux_once` 换成 `pthread_once` |
| `libselinux_init.c.patch` | libselinux `init.c` | 同上系列的小修 |

注意影响范围：这些补丁改的是 **libbase / liblog / libselinux** ——
`libbase`/`liblog` 是 `extract.erofs`（C++ 工具）用的，`libselinux` 是 mkfs 处理
SELinux 标签用的。**核心的 `fsck/`、`mkfs/`、`dump/`、`lib/` C 代码没有被改**，
是直接从上游源码编的。

### 2.5 第 5 环 构建脚本 build_cygwin.sh

`build_cygwin.sh` 全文不长，逐步拆解如下：

```bash
OUT="./out"                                        # 构建目录
BUILD_DIR="./build/cmake"
EROFS_VERSION="v$(. scripts/get-version-number)"   # 版本号取自源码树
EXT=".exe"                                          # 目标平台后缀 → 生成的 exe 名字

# ① 配置 + 编译
cmake -S ${BUILD_DIR} -B ${OUT} -G Ninja \
      -DCMAKE_SYSTEM_NAME="CYGWIN" \
      -DCMAKE_BUILD_TYPE="Release" \
      -DCMAKE_C_COMPILER_LAUNCHER="ccache" \
      -DCMAKE_CXX_COMPILER_LAUNCHER="ccache" \
      -DCMAKE_C_COMPILER="x86_64-pc-cygwin-clang" \
      -DCMAKE_CXX_COMPILER="x86_64-pc-cygwin-clang++" \
      -DCMAKE_C_FLAGS="" -DCMAKE_CXX_FLAGS="" \
      -DENABLE_FULL_LTO="OFF" \
      -DMAX_BLOCK_SIZE="4096"
ninja -C $OUT            # 没装 ninja 时退化成 make -C $OUT -j$(nproc)

# ② 打包（这一步决定了 engine\ 里为什么是一个 exe + 一个 DLL）
local BUILD="$OUT/erofs-tools"
cp -af $BUILD/*.erofs.exe $TARGET_DIR_PATH                        # 四个 exe
cp -af /usr/x86_64-pc-cygwin/bin/cygwin1.dll $TARGET_DIR_PATH     # 交叉 sysroot 里的运行库
touch -c -d "2009-01-01 00:00:00" $TARGET_DIR_PATH/*              # 统一时间戳，便于复现比对

# ③ 目录名就是 Release 资产名
TARGE_DIR_NAME="erofs-utils-${EROFS_VERSION}-$(TZ=UTC-8 date +%y%m%d)-${TARGET}_${ABI}"
# → erofs-utils-v1.8.10-gee46dd74-251217-Cygwin_x86_64
```

逐点解释：

* **`-DCMAKE_SYSTEM_NAME=CYGWIN`**：告诉 CMake"目标系统是 Cygwin"，
  于是顶层 `CMakeLists.txt` 走 CYGWIN 分支加 `-Wl,-s,-x,--gc-sections`（strip + 去死代码），
  链接库清单也会追加 `ext2_uuid` / `iconv` / `ntdll`。
* **`x86_64-pc-cygwin-clang`**：这是**交叉编译器**的可执行文件名，
  它的"目标三元组"是 `x86_64-pc-cygwin` —— 产出的就是 Cygwin 平台（Windows）的 PE 文件。
* **`MAX_BLOCK_SIZE=4096`**：把 EROFS 最大块大小定为 4096。
* **`-c` 与 `2009-01-01`**：产物时间戳统一，方便别人按位比对。
* **`cygwin1.dll` 的来源**：交叉工具链 sysroot 里的 `/usr/x86_64-pc-cygwin/bin/`，
  和 exe 由同一套工具链产生，版本天然匹配。

### 2.6 第 6 环 CI 谁在跑构建

`.github/workflows/build-erofs-utils.yml`（**push 到 `dev` 分支或手动 `workflow_dispatch`** 触发）：

```
jobs:
  Build-android        在 ubuntu 上（NDK 交叉）编 Android 版
  Build-on-linux       在 ubuntu 上编 Linux 版（会额外编 erofsfuse）
  Build-cygwin         在 ubuntu 上（Cygwin 交叉工具链）编本引擎 ★
  Build-on-macOS       在 mac 上编 Darwin 版
  release              needs 上面四个，收集产物并发布 Release
```

`Build-cygwin` 这个 job 的实际步骤：

```yaml
- name: Setup cygwin cross toolchains
  run: |
    echo "${{ env.cygwin_prebuilt_packages }}" | sudo tee /etc/apt/sources.list.d/deb-cygwin.list
    sudo apt update && sudo apt install cygwin cygwin-gcc cygwin-libiconv cygwin-xclang cygwin-libc++
- name: Build
  run: |
    chmod a+x build_cygwin.sh
    ./build_cygwin.sh
- name: Upload erofs-utils Cygwin_x86_64
  # 上传 target/Cygwin_x86_64/erofs-utils-v*/ 下的文件
```

关键点：**在 Ubuntu 上 `apt install cygwin-xclang`** —— 装的是社区维护的
Debian 打包版 Cygwin 交叉工具链（`deb-cygwin-debian` 仓库），
所以整个编译过程跑在 Linux 上，不需要任何 Windows 机器。

### 2.7 第 7 环 发布资产

同一次构建会产出多平台资产，命名规则：

```
erofs-utils-<版本>-<yymmdd>-<平台>_<架构>.zip
   ├─ Android_arm64-v8a / Android_armeabi-v7a / Android_x86 / Android_x86_64
   ├─ Linux_aarch64 / Linux_x86_64 / Linux_loongarch64
   ├─ Darwin_aarch64 / Darwin_x86_64
   ├─ Cygwin_x86_64      ★ 本项目用这个
   └─ WSL_x86_64
```

每个 zip 里就是 **4 个 exe + cygwin1.dll**（Cygwin 版），例如：

```
erofs-utils-v1.8.10-gee46dd74-251217-Cygwin_x86_64.zip   (5 146 583 字节)
   ├─ fsck.erofs.exe       1 965 568
   ├─ mkfs.erofs.exe       2 073 600
   ├─ dump.erofs.exe       1 964 544
   ├─ extract.erofs.exe    3 077 632
   └─ cygwin1.dll          3 012 149
```

资产名里的 `gee46dd74` 是构建时 `git describe` 得到的**上游提交短哈希**
（`fsck.erofs.exe -V` 也会打印 `1.8.10-gee46dd74`）。
⚠️ erofs-utils 的 `dev` 分支会被维护者 rebase，**这个提交如今在上游已查不到**
（API 返回 422）。追源码请用 tag 级地址，见 [第 7 节](#7-许可证与分发)。

### 2.8 第 8 环 本项目取用

`tools/fetch_engine.py` 做的事：

```
1. GET https://api.github.com/repos/sekaiacg/erofs-tools/releases/latest
2. 在 assets 里挑名字含 "Cygwin_x86_64" 的那个
3. 若本地已有同名且大小一致的 zip → 跳过下载
4. 否则下载到 engine\ ，然后 zipfile.extractall() 解包
5. 解包后 engine\ 里得到 4 个 exe + cygwin1.dll
```

之后 `tools/verify_engine_provenance.py` 会把本地文件的 SHA256 与上游信息交叉核对。

### 2.9 第 9 环 运行期调用

`imgtool/core.py` 是这么把它们跑起来的：

```python
argv = [engine\fsck.erofs.exe,
        "--extract=<输出目录>",     # 路径转成正斜杠：D:/a/b（Cygwin 认得，且不会把 \ 当转义）
        "--offset=<N>",            # 仅当 EROFS 不在文件开头
        "-d2",                     # 日志级别
        "<镜像路径>"]

env["CYGWIN"] = "winsymlinks:sys"  # ★ 关键：让符号链接落成可读文件而不是 WSL 重解析点
env["LC_ALL"] = "C.UTF-8"          # 中文文件名走 UTF-8
env["PATH"]   = engine_dir + ";" + PATH
cwd = engine_dir                   # 保证 cygwin1.dll 与临时文件都在引擎目录下解析
creationflags = CREATE_NO_WINDOW   # pythonw 启动时不要闪黑框
```

退出码 0 = 成功；输出用独立线程逐行读走（避免管道写满死锁），
一边回传给界面日志，一边用于失败原因的中文映射。

> 为什么必须设 `CYGWIN=winsymlinks:sys`：默认情况下 Cygwin 会把符号链接写成
> **WSL 的 `LX_SYMLINK` 重解析点**（tag `0xa000001d`），Windows 自己反而读不了、
> 连删都删不掉。设成 `sys` 后写成 `"!<symlink>" + UTF-16LE 目标`的普通文件，
> 我们就能读出来再还原成真链接 / 目录联接。细节见 README 踩坑记录 T1。

### 2.10 第 10 环 CMake 到底是怎么编出 exe 的

前面几环说了"用 CMake + Cygwin 交叉工具链"，这一节把它拆到命令行级别：
`.c` 是怎么一步步变成 `fsck.erofs.exe` 的，以及**怎么从编好的 exe 里反推出这些步骤**。

#### 2.10.1 CMake 的三个阶段

CMake 不是编译器，它只负责"生成构建文件"，真正干活的是编译器和 Ninja：

```
① configure（配置）   cmake -S ./build/cmake -B ./out -G Ninja -DCMAKE_SYSTEM_NAME=CYGWIN …
        · 读 CMakeLists.txt
        · 探测编译器能力：cmake/check.cmake 里用 try_compile 逐个试
          “这个 flag 编译器认不认”，不认就不加（所以同一份构建脚本能跨平台用）
        · 定下目标平台、工具链、编译/链接选项

② generate（生成）    →  产出 ./out/build.ninja（+ CMakeCache.txt、compile_commands.json）
        · 每个 .c/.cpp 文件变成一条编译规则
        · 每个 add_executable() 变成一条链接规则，依赖关系也写进去了

③ build（构建）       ninja -C ./out
        · 先编依赖库（.a 静态库），再编 exe，最后链接（增量构建只重编改动的文件）
```

#### 2.10.2 目标平台决定了"产物长什么样"

`-DCMAKE_SYSTEM_NAME=CYGWIN` 这一句的影响贯穿全程：

| CMake 变量 | CYGWIN 下的值 | 后果 |
| --- | --- | --- |
| `CMAKE_EXECUTABLE_SUFFIX` | `.exe` | `add_executable(fsck.erofs)` 产出 `fsck.erofs.exe` |
| `CMAKE_STATIC_LIBRARY_SUFFIX` | `.a` | 依赖库编成 `liberofs.a`、`liblz4.a`… |
| `CMAKE_SHARED_LIBRARY_SUFFIX` | `.dll` | 共享库后缀（本项目不用） |
| 顶层 `CMakeLists.txt` 的分支 | `if (CMAKE_SYSTEM_NAME MATCHES "CYGWIN")` | 追加 `-Wl,-s,-x,--gc-sections` |
| `erofs_tools.cmake` 的分支 | `if (CYGWIN)` | 链接库清单追加 `ext2_uuid`、`iconv`、`ntdll` |

如果不指定 `CMAKE_SYSTEM_NAME`，CMake 会认为"在本机（Linux）构建"，产物就是 Linux ELF，
名字也不会带 `.exe` —— 这正是"交叉编译"的关键开关。

#### 2.10.3 三条命令：编译 → 归档 → 链接

以 `fsck.erofs` 为例（**下面命令行是按 CMake 的生成规则还原的**；
想看逐字不差的原始命令，自己构建时加 `ninja -v`，或看 CMake 自动生成的
`compile_commands.json`）：

**第 1 步 编译（每个 .c 一条命令）**

```bash
x86_64-pc-cygwin-clang \
    -D_FILE_OFFSET_BITS=64 -D_LARGEFILE_SOURCE -D_LARGEFILE64_SOURCE \
    -Os -D_FORTIFY_SOURCE=2 -fstack-protector-strong \
    -fdata-sections -ffunction-sections -fvisibility=hidden \
    -std=gnu11 \
    -I<erofs-utils>/include -I<erofs-utils>/lib -I<依赖头文件目录>… \
    -c <erofs-utils>/fsck/main.c \
    -o out/…/fsck/main.c.o
```

`-fdata-sections -ffunction-sections` 把每个函数/数据放到独立节区，
是为了后面链接时能按节丢弃（配合 `--gc-sections`）。

**第 2 步 归档（每个依赖库一条命令）**

```bash
x86_64-pc-cygwin-ar qc liberofs.a <erofs-utils/lib/*.o>      # 静态库就是一堆 .o 的压缩包
x86_64-pc-cygwin-ar qc liblz4.a  <lz4/*.o>
x86_64-pc-cygwin-ar qc libzstd.a <zstd/*.o>
…                                                            # xz / zlib / pcre2 / xxhash / selinux / libbase / liblog …
```

**第 3 步 链接（每个 exe 一条命令）**

```bash
x86_64-pc-cygwin-clang \
    out/…/fsck/*.o \                          # ① fsck/ 下所有源文件的目标文件
    liberofs.a libcutils.a libbase.a liblog.a libselinux.a \
    liblz4.a liblzma.a libz.a libzstd.a libpcre2.a libxxhash.a \
    -lext2_uuid -liconv -lntdll \             # ② CYGWIN 分支追加的三个库
    -Wl,-s -Wl,-x -Wl,--gc-sections \         # ③ CYGWIN 分支追加的链接标志
    -o out/erofs-tools/fsck.erofs.exe
```

> CMake 会把 `target_link_libraries(fsck.erofs erofs_static lz4_static …)` 里的
> **目标名**翻译成对应的 `.a` 文件路径（并自动补 `-L` 搜索路径）。

#### 2.10.4 链接器最后做了什么（从产物反推）

把编出来的 `fsck.erofs.exe` 拆开看，就能验证上面每一步都生效了
（用 `python tools\probe_pe.py engine\fsck.erofs.exe` 可复现）：

| 观察到的现象 | 说明它对应哪一步 |
| --- | --- |
| `PE32+（64 位）`、机器类型 `AMD64`、子系统 `WINDOWS_CUI`（控制台） | 因为目标是 Cygwin/x86_64，且是命令行程序 |
| **只导入 2 个 DLL：`cygwin1.dll`（229 个函数）+ `KERNEL32.dll`（7 个函数）** | ② 的静态链接生效了 —— lz4/lzma/zlib/zstd/pcre2/xxhash/selinux 全部进了 exe 本体 |
| `cygwin1.dll` 那 229 个函数（`__errno`、`__getreent`、`__locale_*`、`open`、`read`…） | 链接时**隐式**带进了 Cygwin 的启动代码与系统调用层（`crt0.o` + `libcygwin.a`），这就是"必须带这个 DLL"的根本原因 |
| `KERNEL32.dll` 那 7 个（`RaiseException`、`RtlCaptureContext`、`RtlLookupFunctionEntry`、`RtlUnwindEx`…） | 编译器运行时（异常/栈展开支持）直接调用的 Windows 原生 API |
| **COFF 符号表已被去掉**（0 个符号） | ③ 的 `-Wl,-s` 生效，所以反编译看不到函数名 |
| 没有调试目录 | `CMAKE_BUILD_TYPE=Release`，没带 `-g` |
| `.text .data .rdata .pdata .xdata .bss .idata .rsrc .reloc` 九个节区 | 常规 PE 布局；`.pdata`/`.xdata` 是 x64 的异常处理表 |
| 带 `.rsrc` 节 | 里面是 Windows 清单（声明不需要 UAC 提权等） |
| `mkfs.erofs.exe` 与 `fsck.erofs.exe` 的链接时间戳完全相同 | 同一次 `ninja` 运行里连续链出来的 |
| 二进制里能搜到 `cygwin/cygwin-libc++/src/libcxxabi/src/cxa_personality.cpp` | 工具链连了 Cygwin 交叉环境自带的 libc++abi |

#### 2.10.5 交叉工具链到底"交叉"在哪

关键在于 `x86_64-pc-cygwin-clang` 这个**驱动**：它把"目标三元组 `x86_64-pc-cygwin`"
连同 Cygwin 的 sysroot（头文件、`libcygwin.a`、`crt0.o`、`libntdll.a` 等）绑在一起，
于是同一条 `clang -c/-o` 命令在 Linux 上跑，产出的却是 Windows PE 文件。

`cygwin-xclang` 这个 Debian 包（社区维护）提供的就是这套驱动 + sysroot；
Cygwin 官方运行库 `cygwin1.dll` 也在其中（所以 `build_cygwin.sh` 能直接
从 `/usr/x86_64-pc-cygwin/bin/` 把它拷进发布包）。

#### 2.10.6 想自己看真实命令行

```bash
# 方式 1：构建时把命令行打印出来
ninja -C ./out -v

# 方式 2：CMake 会自动导出编译数据库（顶层 CMakeLists 里设了
#         CMAKE_EXPORT_COMPILE_COMMANDS ON）
cat ./out/compile_commands.json

# 方式 3：不重新构建，直接从产物反推（本项目自带脚本）
python tools\probe_pe.py engine\fsck.erofs.exe
python tools\probe_pe.py engine\cygwin1.dll      # 顺带能看到 Cygwin 本体是 GCC 11.4.0 编的
```

---

## 3 版本与校验值
本仓库当前对应的引擎：

| 项 | 值 |
| --- | --- |
| 构建工程 | [sekaiacg/erofs-tools](https://github.com/sekaiacg/erofs-tools) |
| 发布 tag | `v1.8.10-251217` |
| tag 指向提交 | `7274417816e3adfe0cd6d4a8ff194ec5f41268f4` |
| 上游 erofs-utils | 1.8.10（二进制自报 `1.8.10-gee46dd74`） |
| 资产 | `erofs-utils-v1.8.10-gee46dd74-251217-Cygwin_x86_64.zip` |

| 文件 | 字节 | SHA256 |
| --- | --- | --- |
| `erofs-utils-v1.8.10-gee46dd74-251217-Cygwin_x86_64.zip` | 5 146 583 | `b6a24de0cfe49a95283cf306db1d158bdb63850e0687c8a8b0f4c4a540ba35ba` |
| `fsck.erofs.exe` | 1 965 568 | `81890a95aa6e9dd710119b22c674d089a311cd48474d270923873fbc37c05afa` |
| `mkfs.erofs.exe` | 2 073 600 | `e2bd628cefd10cc3abca747a65f344b21fc6ce2ae0ec36e5cfb9bc64d521202c` |
| `dump.erofs.exe` | 1 964 544 | `85456613664605b40e752fc22eb2a6a24e2966a5c4029af442a52adf7b4286cb` |
| `extract.erofs.exe` | 3 077 632 | `d7378ddb500c4338c4ef02f0da7601693a16807faafa453c1dc5750baf3b0dca` |
| `cygwin1.dll` | 3 012 149 | `ab77212a71c2e2e8b870452d2c32bc72a6708d6e963dd3ebe2ac1a946cffc242` |

---

## 4 自己验证

三个层次，从轻到重：

```powershell
# ① 跑一下，看它自报什么
.\engine\fsck.erofs.exe -V            # 应打印 1.8.10-gee46dd74 与可用压缩算法
.\engine\fsck.erofs.exe --help        # 应列出 lz4/lz4hc/lzma/deflate/zstd

# ② 比对本地文件哈希（只信本地，不联网）
Get-FileHash .\engine\fsck.erofs.exe -Algorithm SHA256
python tools\verify_engine_provenance.py --offline

# ③ 对着上游核一遍：tag、资产大小、构建脚本、补丁、CI、上游许可证
python tools\verify_engine_provenance.py
```

第 ③ 步当前是 **23 项全部 PASS**，它核对的正是本文的每一条结论：

| 核对项 | 依据 |
| --- | --- |
| 本地 5 个文件的字节数与 SHA256 | 与本文第 3 节表格比对 |
| tag `v1.8.10-251217` 存在且指向 `7274417…` | GitHub tags API |
| 资产名与大小 5 146 583 | GitHub releases API |
| 构建脚本用 `x86_64-pc-cygwin-clang` + CMake/Ninja + `CMAKE_SYSTEM_NAME=CYGWIN` | `build_cygwin.sh` 原文 |
| 打包时拷贝 `cygwin1.dll` | 同上 |
| `fsck.erofs` 由 `file(GLOB fsck/*.c)` 生成、静态链接压缩库、Cygwin 加链 `ntdll` | `erofs_tools.cmake` 原文 |
| 存在 Cygwin 兼容补丁 | 该 tag 的源码树 |
| CI 有 `Build-cygwin` 任务、装 `cygwin-xclang`、执行 `build_cygwin.sh` | workflow YAML 原文 |
| 上游 `lib/include` 为 `GPL-2.0+ OR Apache-2.0`、其余为 `GPL-2.0+` | 上游 `COPYING` 原文 |
| `fsck/main.c` 文件头标注 `GPL-2.0+` | 上游源码原文 |

---

## 5 从源码自己编一份

如果你不想用别人的预编译二进制，有三条路。**推荐第 1 条**（最省事，产物结构一致）。

### 方式 1 在 Windows 上装 Cygwin 后本地编译（推荐）

```bash
# 在 Cygwin 终端里（Cygwin 安装器里勾上 git cmake ninja make gcc-g++ clang
#                       以及 liblz4-devel liblzma-devel zlib-devel libzstd-devel
#                       libselinux-devel libuuid-devel libiconv-devel pkg-config）
git clone https://github.com/sekaiacg/erofs-tools.git
cd erofs-tools
git checkout v1.8.10-251217
git submodule update --init --recursive
chmod +x build_cygwin.sh
./build_cygwin.sh
# 产物：target/Cygwin_x86_64/erofs-utils-v1.8.10-<日期>-Cygwin_x86_64/
#         ├─ fsck.erofs.exe  mkfs.erofs.exe  dump.erofs.exe  extract.erofs.exe
#         └─ cygwin1.dll     （脚本会自己从 /usr/x86_64-pc-cygwin/bin/ 拷）
```

> 也可以在原生 Cygwin 里用本机 clang/gcc：把脚本里的
> `-DCMAKE_C_COMPILER=x86_64-pc-cygwin-clang` 改成 `clang` 或 `gcc`，
> `-DCMAKE_SYSTEM_NAME` 去掉即可（本机编译不需要指定目标系统）。

### 方式 2 在 Linux 上复刻 CI 的交叉编译

```bash
# Ubuntu（复刻 GitHub Actions 的做法）
echo "deb [trusted=yes] https://github.com/affggh/deb-cygwin-debian/releases/download/.../ ./" \
  | sudo tee /etc/apt/sources.list.d/deb-cygwin.list
sudo apt update && sudo apt install cygwin cygwin-gcc cygwin-libiconv cygwin-xclang cygwin-libc++
git clone https://github.com/sekaiacg/erofs-tools.git && cd erofs-tools
git checkout v1.8.10-251217 && git submodule update --init --recursive
./build_cygwin.sh
```

### 方式 3 只编上游 erofs-utils 本体（最"干净"，但没有 extract.erofs）

在 Cygwin 里用上游自己的 autotools 流程：

```bash
git clone https://github.com/erofs/erofs-utils.git
cd erofs-utils && git checkout v1.8.10
./autogen.sh
./configure --enable-lz4 --enable-lzma --with-zlib --with-libzstd \
            --with-xxhash --with-uuid --with-selinux --with-libdeflate
make -j$(nproc)
# 产物：fsck/fsck.erofs.exe  mkfs/mkfs.erofs.exe  dump/dump.erofs.exe
```

编译开关取自上游 `configure.ac`（`--enable-lz4`、`--enable-lzma`、`--with-zlib`、
`--with-libzstd`、`--with-xxhash`、`--with-uuid`、`--with-selinux`、
`--with-libdeflate`、`--enable-fuse` 等），少了哪个开关就会少一种压缩算法支持。

自己编完之后，把新产物放进 `engine\` 覆盖，再跑一遍
`python tools\verify_engine_provenance.py --offline`（哈希会与你预期不同，属正常），
最后跑 `powershell -File tests\run_all.ps1` 确认功能没退化。

---

## 6 常见疑问

**Q1：这些 `.exe` 是你们自己编译的吗？**
A：**不是。** 4 个 exe 全部是 [sekaiacg/erofs-tools](https://github.com/sekaiacg/erofs-tools)
的 GitHub Actions 编出来的，本项目只下载成品（见 [第 1 节](#1-一句话结论) 的证据）。
本项目自己只写了 Python/GUI/文档，以及用引擎生成测试镜像。

**Q2：为什么不直接用 Linux 版 + WSL？**
A：本项目明确不依赖 WSL（要额外安装、占空间、可能要重启）。Cygwin 版是上游原版代码，
一个 exe + 一个 DLL 就能跑。

**Q3：为什么是 4 个 exe？各干什么？**
A：`fsck.erofs`（解压主力）、`dump.erofs`（读元数据/识别格式）、`mkfs.erofs`（造镜像，
本项目用来生成测试镜像）、`extract.erofs`（第三方增强工具，可导出 `fs_config`，暂未使用）。

**Q4：能不能不要 `cygwin1.dll`？**
A：不能。这几个 exe 的导入表里就写着 `cygwin1.dll` —— 文件操作、符号链接、权限等
POSIX 调用都由它提供。删了就报"找不到 DLL"。想彻底摆脱它只能改用别的引擎（比如自己
用 MSVC 重写解析器），那就不是 `fsck.erofs` 了。

**Q5：这些 exe 安全吗？怎么确认没被掉包？**
A：三层核对（见第 4 节）：`-V` 自报版本 → 本地 SHA256 → 审计脚本对着上游核 23 项。
另外可以把 `engine\` 整体删掉，用 `python tools\fetch_engine.py` 重新下载比对。

**Q6：二进制里的 `gee46dd74` 查不到怎么办？**
A：那是构建时 erofs-utils `dev` 分支的提交，被维护者 rebase 掉了。
"相应源码"请用 `sekaiacg/erofs-tools` 的 tag `v1.8.10-251217`——
那个 tag 里就有构建这批二进制时的完整源码树与脚本。

**Q7：为什么解析压缩算法是"编进去"的？**
A：因为全部静态链接（见 [2.3](#23-第-3-环-构建定义-三个-exe-的诞生处)）。好处是部署简单、
不挑环境；代价是体积比动态链接大一点，而且换算法版本要重新编译。

**Q8：Cygwin 是什么？它算不算"虚拟机"？**
A：不算。Cygwin 是一个**用户态的 POSIX 兼容层 DLL**（不是内核驱动、不是虚拟化），
程序是真正的 Windows PE 可执行文件，只是系统调用经由 `cygwin1.dll` 翻译。
所以不需要管理员权限、不需要开 Hyper-V。

**Q9：为什么这些 exe 会弹"无法验证发布者"？**
A：因为它们**没有代码签名**（社区构建，无签名证书）。这是开源小工具的常态；
在意的话就自己编译（[第 5 节](#5-从源码自己编一份)），或者加杀软白名单。

**Q10：README 里说"用 mkfs.erofs 压缩了一个 IMG"，那算不算本项目在构建？**
A：不算。那是**使用**下载来的引擎去生成测试镜像（`tests/make_fixtures.py`），
和"构建引擎本身"是两件事。本项目从头到尾没有编译过任何 C 代码。

---

## 7 许可证与分发

| 组件 | 许可证（SPDX） | 完整文本 |
| --- | --- | --- |
| `fsck.erofs.exe`、`mkfs.erofs.exe`、`dump.erofs.exe` | `GPL-2.0-or-later` | [LICENSES/GPL-2.0.txt](../LICENSES/GPL-2.0.txt) |
| `extract.erofs.exe` | `GPL-2.0-or-later` | [LICENSES/GPL-2.0.txt](../LICENSES/GPL-2.0.txt) |
| `cygwin1.dll` | `LGPL-3.0-or-later`（含链接例外） | [LICENSES/LGPL-3.0.txt](../LICENSES/LGPL-3.0.txt) + [LICENSES/GPL-3.0.txt](../LICENSES/GPL-3.0.txt) |

**对应源码（GPL-2.0 §3 意义上的"相应源码"）**：

| 用途 | 地址 |
| --- | --- |
| 本目录二进制的完整对应源码（含构建脚本与补丁） | <https://github.com/sekaiacg/erofs-tools/tree/v1.8.10-251217> |
| 上游 erofs-utils 官方源码 | <https://github.com/erofs/erofs-utils/tree/v1.8.10> |
| Cygwin 源码 | <https://cygwin.com/sources.html> |

分发前请对照 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) 第 5 节的清单逐项检查。

---

## 8 术语表

| 术语 | 含义 |
| --- | --- |
| **EROFS** | Enhanced Read-Only File System，Linux 内核的只读文件系统，Android 系统分区默认用它 |
| **liberofs** | erofs-utils 的公共 C 库（`lib/`），实现 EROFS 的解析/解压/写入 |
| **PE 文件** | Portable Executable，Windows 可执行文件格式；`.exe`/`.dll` 都是 PE |
| **Cygwin** | Windows 上的 POSIX 兼容层（`cygwin1.dll`），本项目引擎的运行环境 |
| **交叉编译** | 在 A 平台编译出 B 平台的可执行文件；本项目是在 Linux 上编 Windows/Cygwin 程序 |
| **目标三元组** | 形如 `x86_64-pc-cygwin` 的字符串，描述"给哪个平台编" |
| **submodule** | git 子模块，把一个仓库嵌进另一个仓库并锁定提交 |
| **静态链接** | 把依赖库的目标代码直接合并进可执行文件；本项目除 Cygwin 运行库外全是静态链接 |
| **重解析点（reparse point）** | NTFS 上实现符号链接/联接的机制；Cygwin 默认的 WSL 式符号链接 Windows 读不了 |
| **`GPL-2.0-or-later`** | GPL v2 或（由你选择）任何更新的版本；SPDX 记作 `GPL-2.0+` |
| **聚合（mere aggregation）** | GPL 术语：两个独立程序放在同一分发物里，不构成派生作品 |
