# -*- coding: utf-8 -*-
# SPDX-License-Identifier: 0BSD
"""生成给用户手动拖拽测试用的演示 IMG（放在 示例镜像\\ 目录里）。

产出：
    示例镜像\\system_demo.img          EROFS + lz4（最常见）
    示例镜像\\system_demo_lzma.img     EROFS + lzma（Android 上也不少，解压慢一点）
    示例镜像\\system_demo_sparse.img   外面套 Android sparse 外壳（官方工厂镜像常见）
    示例镜像\\期望结果.txt              手动对照清单

生成完会自己解压一遍做校验，确认交出去的镜像是好的。

用法：python tests\\make_demo_img.py
"""

import hashlib
import io
import os
import shutil
import sys
import tarfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from imgtool import core, sparse                      # noqa: E402
from tests import make_fixtures as mf                 # noqa: E402

DEMO = os.path.join(ROOT, "\u793a\u4f8b\u955c\u50cf")   # 示例镜像
BIG_MB = 6
APK_MB = 2


def build_demo_tar(tar_path):
    """构造一个"像 system 分区"的内容树，返回清单 dict。"""
    ti = mf._ti
    entries = []
    manifest = {}

    # ---- 目录 ----
    for d, mode in [("bin", 0o755), ("etc", 0o755), ("lib", 0o755),
                    ("app", 0o755), ("app/DemoApp", 0o755),
                    ("\u4e2d\u6587\u76ee\u5f55", 0o755),
                    ("\u5e26 \u7a7a\u683c \u7684\u76ee\u5f55", 0o755),
                    ("empty_dir", 0o755)]:
        entries.append((ti(d, mode=mode, typ=tarfile.DIRTYPE), None))
        manifest[d] = ("dir", mode)

    # ---- 普通文件 ----
    readme = (
        "\u8fd9\u662f imgtool \u7684\u6f14\u793a\u955c\u50cf\uff0c\u91cc\u9762\u53ea\u6709\u6d4b\u8bd5\u5185\u5bb9\u3002\n"
        "\u5982\u679c\u4f60\u80fd\u5728 Windows \u4e0a\u770b\u5230\u8fd9\u884c\u5b57\uff0c"
        "\u8bf4\u660e EROFS \u955c\u50cf\u88ab\u6b63\u786e\u89e3\u5f00\u4e86\u3002\n"
    ).encode("utf-8")
    files = [
        ("readme_\u8bf4\u660e.txt", readme, 0o644, 0, 0),
        ("build.prop", b"ro.product.model=imgtool-demo\nro.build.version.release=13\n", 0o644, 0, 0),
        ("etc/hosts", b"127.0.0.1 localhost\n::1 localhost\n", 0o644, 0, 0),
        ("bin/mksh", b"#!/bin/sh\necho \"hello from mksh\"\n", 0o755, 0, 2000),
        ("bin/toybox", b"toybox binary placeholder\n" * 200, 0o755, 0, 2000),
        ("lib/libdemo.so", mf.rand_bytes(300 * 1024, 42), 0o644, 0, 0),
        ("app/DemoApp/DemoApp.apk", mf.rand_bytes(APK_MB * 1024 * 1024, 7), 0o644, 1000, 1000),
        ("\u4e2d\u6587\u76ee\u5f55/\u4e2d\u6587\u6587\u4ef6\u540d.txt",
         "\u4f60\u597d\uff0c\u8fd9\u662f\u4e2d\u6587\u5185\u5bb9\u3002\n".encode("utf-8"), 0o644, 0, 0),
        ("\u5e26 \u7a7a\u683c \u7684\u76ee\u5f55/\u6587\u4ef6\u540d \u4e5f\u6709\u7a7a\u683c.txt",
         b"path with spaces\n", 0o644, 0, 0),
        ("readonly.txt", b"\xe5\x8f\xaa\xe8\xaf\xbb\xe6\x96\x87\xe4\xbb\xb6\n", 0o444, 0, 0),
        ("empty_file.txt", b"", 0o644, 0, 0),
        ("big.bin", mf.rand_bytes(BIG_MB * 1024 * 1024, 2024), 0o644, 0, 0),
    ]
    for name, data, mode, uid, gid in files:
        t = ti(name, mode=mode, uid=uid, gid=gid)
        t.size = len(data)
        entries.append((t, data))
        manifest[name] = ("file", mode, len(data), hashlib.sha256(data).hexdigest())

    # ---- 硬链接 ----
    t = ti("bin/sh_hard", mode=0o755, typ=tarfile.LNKTYPE)
    t.linkname = "bin/mksh"
    entries.append((t, None))
    manifest["bin/sh_hard"] = ("hardlink", "bin/mksh")

    # ---- 符号链接 ----
    links = [
        ("bin/sh", "mksh"),                                     # 相对文件链接
        ("bin/mksh_abs", "/bin/mksh"),                          # 绝对文件链接
        ("lib64", "lib"),                                       # 指向目录（会做成目录联接）
        ("lib/libdemo.so.1", "libdemo.so"),                     # 相对文件链接
        ("dangling", "/nowhere/missing"),                       # 悬空链接
        ("\u4e2d\u6587\u94fe\u63a5", "\u4e2d\u6587\u76ee\u5f55/\u4e2d\u6587\u6587\u4ef6\u540d.txt"),
    ]
    for name, target in links:
        t = ti(name, mode=0o777, typ=tarfile.SYMTYPE)
        t.linkname = target
        entries.append((t, None))
        manifest[name] = ("symlink", target)

    with tarfile.open(tar_path, "w", format=tarfile.GNU_FORMAT) as tf:
        for t, data in entries:
            if data is None:
                tf.addfile(t)
            else:
                tf.addfile(t, io.BytesIO(data))
    return manifest


def write_expectations(path, manifest, shas):
    n_file = sum(1 for v in manifest.values() if v[0] == "file")
    n_link = sum(1 for v in manifest.values() if v[0] == "symlink")
    n_hard = sum(1 for v in manifest.values() if v[0] == "hardlink")
    n_dir = sum(1 for v in manifest.values() if v[0] == "dir")

    def find(prefix):
        for k, v in manifest.items():
            if v[0] == "file" and k.startswith(prefix):
                return v[3]
        return ""

    lines = []
    A = lines.append
    A("imgtool \u6f14\u793a\u955c\u50cf \u2014\u2014 \u624b\u52a8\u6d4b\u8bd5\u8bf4\u660e")
    A("=" * 60)
    A("")
    A("\u7528\u6cd5\uff1a\u5148\u53cc\u51fb\u9879\u76ee\u6839\u76ee\u5f55\u7684\u300c1-\u542f\u52a8\u89e3\u538b\u5de5\u5177.bat\u300d\uff0c")
    A("      \u7136\u540e\u628a\u4e0b\u9762\u7684 .img \u62d6\u8fdb\u7a97\u53e3\uff0c\u677e\u624b\u5c31\u5f00\u59cb\u89e3\u538b\u3002")
    A("")
    A("  system_demo.img         EROFS + lz4\uff08\u6700\u5e38\u89c1\uff0c\u5efa\u8bae\u5148\u8bd5\u8fd9\u4e2a\uff09")
    A("  system_demo_lzma.img    EROFS + lzma\uff08\u538b\u7f29\u7387\u66f4\u9ad8\uff0c\u89e3\u538b\u6162\u4e00\u4e9b\uff09")
    A("  system_demo_sparse.img  \u5916\u9762\u5957\u4e86\u4e00\u5c42 Android sparse\uff08\u5b98\u65b9\u5de5\u5382\u955c\u50cf\u5e38\u89c1\uff09")
    A("")
    A("\u9884\u671f\u7ed3\u679c")
    A("-" * 60)
    A("\u89e3\u538b\u540e\u4f1a\u5728\u955c\u50cf\u65c1\u8fb9\u751f\u6210\u540c\u540d\u6587\u4ef6\u5939\uff0c\u4f8b\u5982\uff1a")
    A("  \u793a\u4f8b\u955c\u50cf\\system_demo.img  ->  \u793a\u4f8b\u955c\u50cf\\system_demo\\")
    A("")
    A("\u91cc\u9762\u5e94\u8be5\u6709\uff1a%d \u4e2a\u666e\u901a\u6587\u4ef6\u3001%d \u4e2a\u7b26\u53f7\u94fe\u63a5\u3001"
      "%d \u4e2a\u786c\u94fe\u63a5\u3001%d \u4e2a\u76ee\u5f55" % (n_file, n_link, n_hard, n_dir))
    A("")
    A("\u9010\u9879\u68c0\u67e5\u70b9")
    A("-" * 60)
    A("1. readme_\u8bf4\u660e.txt         \u80fd\u6253\u5f00\uff0c\u91cc\u9762\u662f\u4e2d\u6587\u8bf4\u660e")
    A("2. bin\\sh                   \u6307\u5411 mksh\u3002\u6ca1\u5f00\u5f00\u53d1\u8005\u6a21\u5f0f\u65f6\uff0c")
    A("                            \u5b83\u662f\u4e2a\u5c0f\u6587\u4ef6\uff0c\u5185\u5bb9\u662f !<symlink>mksh")
    A("3. lib64                    \u76ee\u5f55\u8054\u63a5\uff08junction\uff09\uff0c\u53cc\u51fb\u80fd\u8fdb\u53bb\uff0c")
    A("                            \u91cc\u9762\u5c31\u662f lib \u76ee\u5f55\u7684\u5185\u5bb9")
    A("4. dangling                 \u60ac\u7a7a\u94fe\u63a5\uff08\u6307\u5411\u4e0d\u5b58\u5728\u7684\u8def\u5f84\uff09\uff0c\u4e0d\u4f1a\u5bfc\u81f4\u89e3\u538b\u5931\u8d25")
    A("5. bin\\sh \u4e0e bin\\mksh        \u786c\u94fe\u63a5\uff0c\u540c\u4e00\u4e2a inode\uff08\u6539\u4e00\u4e2a\u53e6\u4e00\u4e2a\u4e5f\u53d8\uff09")
    A("6. \u4e2d\u6587\u76ee\u5f55\\\u4e2d\u6587\u6587\u4ef6\u540d.txt  \u4e2d\u6587\u8def\u5f84\u6ca1\u4e71\u7801")
    A("7. \u5e26 \u7a7a\u683c \u7684\u76ee\u5f55\\...      \u5e26\u7a7a\u683c\u7684\u8def\u5f84\u6b63\u5e38")
    A("8. readonly.txt             \u53ea\u8bfb\u6587\u4ef6\uff08\u5c5e\u6027\u91cc\u6709\u300c\u53ea\u8bfb\u300d\uff09")
    A("9. empty_dir\\               \u7a7a\u76ee\u5f55\u4e5f\u4f1a\u88ab\u8fd8\u539f")
    A("10. \u4e00\u81f4\u6027\u6821\u9a8c\uff1a\u4e0b\u9762\u8fd9\u4e24\u4e2a\u6587\u4ef6\u7684 SHA256 \u5e94\u5f53\u4e0e\u6b64\u5904\u76f8\u7b26")
    A("    big.bin       %s" % find("big.bin"))
    A("    DemoApp.apk   %s" % find("app/DemoApp/DemoApp.apk"))
    A("")
    A("\uff08\u7528 PowerShell \u6821\u9a8c\uff1aGet-FileHash .\\system_demo\\big.bin -Algorithm SHA256\uff09")
    A("")
    A("\u955c\u50cf\u672c\u8eab\u7684\u6821\u9a8c\u503c\uff08SHA256\uff09")
    A("-" * 60)
    for name, digest in shas.items():
        A("  %-26s %s" % (name, digest))
    A("")
    A("\u7531 tests\\make_demo_img.py \u81ea\u52a8\u751f\u6210\u4e8e %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def verify(img, tar_path, manifest, label):
    """解压一遍跟 tar 清单比对，确认镜像是好的。"""
    out = os.path.join(DEMO, "_verify")
    if os.path.isdir(out):
        core.safe_rmtree(out)
    res = core.extract_image(img, dest=out, policy="overwrite", symlinks="native")
    bad = []
    with tarfile.open(tar_path) as tf:
        for m in tf.getmembers():
            dst = os.path.join(out, *m.name.split("/"))
            if m.isdir():
                if not os.path.isdir(dst):
                    bad.append("缺目录 " + m.name)
            elif m.issym():
                if not os.path.lexists(dst):
                    bad.append("缺链接 " + m.name)
                else:
                    tgt = core.read_cygwin_symlink(dst)
                    if tgt is None:
                        kind, det = "junction", None
                        try:
                            det = os.readlink(dst)
                        except OSError:
                            pass
                        if det is None:
                            bad.append("链接形态异常 " + m.name)
                    elif tgt != m.linkname:
                        bad.append("链接目标不符 %s" % m.name)
            elif m.islnk():
                if not os.path.exists(dst):
                    bad.append("缺硬链接 " + m.name)
            elif m.isfile():
                if not os.path.isfile(dst):
                    bad.append("缺文件 " + m.name)
                else:
                    h = hashlib.sha256(open(dst, "rb").read()).hexdigest()
                    if h != hashlib.sha256(tf.extractfile(m).read()).hexdigest():
                        bad.append("内容不符 " + m.name)
    core.safe_rmtree(out)
    print("  [%s] %s -> %d 个文件 %.1f MB %.1fs%s"
          % ("PASS" if not bad else "FAIL", label, res.files, res.size / 1048576.0, res.seconds,
             "" if not bad else "  问题：" + "；".join(bad[:5])))
    return not bad


def main():
    print("=" * 70)
    print("\u751f\u6210\u6f14\u793a\u955c\u50cf")
    print("\u5f15\u64ce\uff1afsck.erofs %s @ %s" % (core.engine_version(), core.engine_dir()))
    print("=" * 70)

    os.makedirs(DEMO, exist_ok=True)
    tar_path = os.path.join(DEMO, "demo_src.tar")
    manifest = build_demo_tar(tar_path)
    print("\n\u5185\u5bb9\u6811\uff1a%d \u4e2a\u6761\u76ee" % len(manifest))

    targets = [
        ("system_demo.img", ["-zlz4"], "EROFS + lz4"),
        ("system_demo_lzma.img", ["-zlzma,9"], "EROFS + lzma"),
    ]
    made = []
    print("\n\u538b\u5236\u955c\u50cf\uff1a")
    for name, opts, desc in targets:
        img = os.path.join(DEMO, name)
        if os.path.exists(img):
            os.remove(img)
        t0 = time.time()
        rc, out = mf.mkfs_from_tar(img, tar_path, opts, log=True)
        if rc != 0 or not os.path.exists(img):
            print("  [\u5931\u8d25] %s" % name)
            continue
        print("  %-26s %7.2f MB  %.2fs  %s" % (name, os.path.getsize(img) / 1048576.0,
                                               time.time() - t0, desc))
        made.append((name, img, desc))

    # sparse 外壳版本（用 lz4 那个包一层）
    src = os.path.join(DEMO, "system_demo.img")
    if os.path.exists(src):
        sp = os.path.join(DEMO, "system_demo_sparse.img")
        if os.path.exists(sp):
            os.remove(sp)
        t0 = time.time()
        sparse.raw_to_sparse(src, sp)
        print("  %-26s %7.2f MB  %.2fs  Android sparse \u5916\u58f3"
              % ("system_demo_sparse.img", os.path.getsize(sp) / 1048576.0, time.time() - t0))
        made.append(("system_demo_sparse.img", sp, "Android sparse"))

    print("\n\u81ea\u68c0\uff08\u89e3\u538b\u4e00\u904d\u9010\u6587\u4ef6\u6bd4\u5bf9\uff09\uff1a")
    ok = True
    for name, img, desc in made:
        ok = verify(img, tar_path, manifest, name) and ok

    shas = {}
    for name, img, _d in made:
        h = hashlib.sha256()
        with open(img, "rb") as f:
            for c in iter(lambda: f.read(1 << 20), b""):
                h.update(c)
        shas[name] = h.hexdigest()

    txt = os.path.join(DEMO, "\u671f\u671b\u7ed3\u679c.txt")
    write_expectations(txt, manifest, shas)
    os.remove(tar_path)          # 中间产物不留着

    print("\n\u4ea7\u51fa\uff1a")
    for f in sorted(os.listdir(DEMO)):
        p = os.path.join(DEMO, f)
        print("  %-28s %8.2f MB" % (f, os.path.getsize(p) / 1048576.0))
    print("\n\u81ea\u68c0\u7ed3\u679c\uff1a%s" % ("\u5168\u90e8 PASS" if ok else "\u6709 FAIL"))
    print("\u628a \u793a\u4f8b\u955c\u50cf\\system_demo.img \u62d6\u8fdb GUI \u5c31\u80fd\u8bd5\u4e86\u3002")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
