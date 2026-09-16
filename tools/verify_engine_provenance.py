# -*- coding: utf-8 -*-
# SPDX-License-Identifier: 0BSD
"""审计 engine\\ 里二进制的来历：把文档里的每个说法都对着上游核一遍。

用法：
    python tools\\verify_engine_provenance.py            # 联网核对（推荐）
    python tools\\verify_engine_provenance.py --offline  # 只校验本地文件的 SHA256

核对内容：
    · 发布版 tag / 资产名 / 资产大小
    · 本地 engine\\*.exe 与 cygwin1.dll 的 SHA256 是否与文档一致
    · 构建脚本 build_cygwin.sh 是否用 x86_64-pc-cygwin-clang + CMake/Ninja
    · CMake 里 fsck.erofs 目标的定义方式
    · CI 工作流里是否存在 Build-cygwin 任务
    · 上游 erofs-utils 的许可证模式（GPL-2.0+ / lib 目录另有 Apache-2.0 选项）
"""

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 imgtool-provenance-audit"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TOOLS_REPO = "sekaiacg/erofs-tools"
TAG = "v1.8.10-251217"
TAG_COMMIT = "7274417816e3adfe0cd6d4a8ff194ec5f41268f4"
ASSET = "erofs-utils-v1.8.10-gee46dd74-251217-Cygwin_x86_64.zip"
ASSET_SIZE = 5146583

EXPECTED = {
    "fsck.erofs.exe": (1965568, "81890a95aa6e9dd710119b22c674d089a311cd48474d270923873fbc37c05afa"),
    "mkfs.erofs.exe": (2073600, "e2bd628cefd10cc3abca747a65f344b21fc6ce2ae0ec36e5cfb9bc64d521202c"),
    "dump.erofs.exe": (1964544, "85456613664605b40e752fc22eb2a6a24e2966a5c4029af442a52adf7b4286cb"),
    "extract.erofs.exe": (3077632, "d7378ddb500c4338c4ef02f0da7601693a16807faafa453c1dc5750baf3b0dca"),
    "cygwin1.dll": (3012149, "ab77212a71c2e2e8b870452d2c32bc72a6708d6e963dd3ebe2ac1a946cffc242"),
}

RAW = "https://raw.githubusercontent.com/%s/%s/" % (TOOLS_REPO, TAG)
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print("  [%s] %-46s %s" % ("PASS" if ok else "FAIL", name, detail))


def get(url, timeout=20, retries=2):
    """带重试的 GET。

    GitHub raw 偶尔会限流或重置连接；但 4xx（除了 429）是确定性错误，
    不重试，免得白等。
    """
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code != 429 and 400 <= e.code < 500:
                raise
            last = e
        except Exception as e:              # noqa: BLE001
            last = e
        if i + 1 < retries:
            time.sleep(1.0)
    raise last


def jget(url, retries=3):
    return json.loads(get(url, retries=retries))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def audit_local():
    print("=" * 74)
    print("1) 本地 engine\\ 文件校验（不联网）")
    print("=" * 74)
    eng = os.path.join(ROOT, "engine")
    for name, (size, digest) in EXPECTED.items():
        path = os.path.join(eng, name)
        if not os.path.isfile(path):
            check(name, False, "文件不存在")
            continue
        real_size, real_sha = os.path.getsize(path), sha256(path)
        ok = (real_size == size and real_sha == digest)
        check(name, ok, "%d 字节  %s" % (real_size, real_sha[:16] + "…" if ok else "SHA256 不符！"))


def audit_online():
    """联网核对；每一节独立容错，网络抖动不会让整轮审计中断。"""
    def section(title, fn):
        print()
        print("=" * 74)
        print(title)
        print("=" * 74)
        try:
            fn()
        except Exception as e:              # noqa: BLE001
            check(title.split(")", 1)[-1].strip() + " —— 本节未完成", False,
                  "%s: %s" % (type(e).__name__, e))

    def sec_release():
        tags = {t["name"]: t["commit"]["sha"] for t in jget(
            "https://api.github.com/repos/%s/tags?per_page=30" % TOOLS_REPO)}
        check("tag %s 存在" % TAG, TAG in tags, tags.get(TAG, ""))
        check("tag 指向提交 %s" % TAG_COMMIT[:8], tags.get(TAG) == TAG_COMMIT)
        rel = jget("https://api.github.com/repos/%s/releases/tags/%s" % (TOOLS_REPO, TAG))
        assets = {a["name"]: a for a in rel.get("assets", [])}
        check("发布资产存在", ASSET in assets, ASSET)
        if ASSET in assets:
            check("资产大小与文档一致", assets[ASSET]["size"] == ASSET_SIZE,
                  "%d 字节" % assets[ASSET]["size"])

    def sec_build():
        sh = get(RAW + "build_cygwin.sh")
        check("构建脚本用 Cygwin 目标 clang",
              "x86_64-pc-cygwin-clang" in sh and "x86_64-pc-cygwin-clang++" in sh)
        check("构建脚本用 CMake + Ninja", "cmake" in sh and "ninja" in sh)
        check("构建脚本设置了 CMAKE_SYSTEM_NAME=CYGWIN", "CYGWIN" in sh)
        check("打包时带上 cygwin1.dll", "cygwin1.dll" in sh)
        cm = get(RAW + "build/cmake/erofs-tools/erofs_tools.cmake")
        check("fsck.erofs 由 file(GLOB fsck/*.c) 生成",
              "GLOB fsck_srcs" in cm and "add_executable(${TARGET_fsck}" in cm)
        check("压缩/公共库静态链接",
              all(k in cm for k in ("erofs_static", "lz4_static", "liblzma",
                                    "libzstd_static", "z_static", "selinux", "xxhash")))
        check("Cygwin 额外链接 ntdll", "ntdll" in cm)

    def sec_patch():
        tree = jget("https://api.github.com/repos/%s/git/trees/%s?recursive=1"
                    % (TOOLS_REPO, TAG_COMMIT))["tree"]
        names = [t["path"] for t in tree]
        check("存在 Cygwin 兼容补丁",
              any(p.startswith("build/cmake/lib/patch/cygwin/") for p in names),
              "%d 个 .patch" % sum(1 for p in names if p.endswith(".patch")))

    def sec_ci():
        wf = get(RAW + ".github/workflows/build-erofs-utils.yml")
        check("存在 Build-cygwin 任务", "Build-cygwin:" in wf)
        check("用交叉工具链编译 Cygwin 目标", "cygwin-xclang" in wf)
        check("执行 build_cygwin.sh", "./build_cygwin.sh" in wf)

    def sec_license():
        copying = get("https://raw.githubusercontent.com/erofs/erofs-utils/v1.8.10/COPYING")
        check("lib/include 为 GPL-2.0+ OR Apache-2.0", "GPL-2.0+ OR Apache-2.0" in copying)
        check("其余文件为 GPL-2.0+", "GPL-2.0+ license" in copying)
        main_c = get("https://raw.githubusercontent.com/erofs/erofs-utils/v1.8.10/fsck/main.c")
        check("fsck/main.c 标注 GPL-2.0+", "GPL-2.0+" in main_c[:200])

    section("2) 上游发布信息（tag / 资产）", sec_release)
    section("3) 构建脚本与构建定义", sec_build)
    section("4) Cygwin 兼容补丁", sec_patch)
    section("5) CI 工作流", sec_ci)
    section("6) 上游许可证模式", sec_license)


def main():
    audit_local()
    if "--offline" not in sys.argv:
        try:
            audit_online()
        except Exception as e:
            check("联网核对", False, "%s: %s" % (type(e).__name__, e))

    bad = [r for r in results if not r[1]]
    print()
    print("=" * 74)
    print("结论：%d 项通过，%d 项失败" % (len(results) - len(bad), len(bad)))
    for name, _ok, detail in bad:
        print("   FAIL %s  %s" % (name, detail))
    print("=" * 74)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
