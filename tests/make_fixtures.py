# -*- coding: utf-8 -*-
# SPDX-License-Identifier: 0BSD
"""生成 EROFS 测试镜像（"自己压缩一个 IMG" 的那一步）。

思路：先在内存里构造一个内容丰富的 tar（含符号链接、硬链接、中文名、各种权限、
空目录、大文件、全零文件……，跟真实 Android system.img 的结构类似），
再用引擎自带的 mkfs.erofs 把 tar 压成 EROFS 镜像，覆盖各种压缩算法与布局选项。

用法：
    python tests/make_fixtures.py [--out test\\fixtures] [--quick]
"""

import argparse
import hashlib
import io
import os
import random
import shutil
import subprocess
import sys
import tarfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from imgtool import core  # noqa: E402


def rand_bytes(n, seed):
    rng = random.Random(seed)
    return rng.getrandbits(8 * n).to_bytes(n, "little")


def _ti(name, mode=0o644, uid=0, gid=0, mtime=1700000000, typ=tarfile.REGTYPE):
    ti = tarfile.TarInfo(name)
    ti.mode = mode
    ti.uid = uid
    ti.gid = gid
    ti.mtime = mtime
    ti.type = typ
    ti.uname = ""
    ti.gname = ""
    return ti


def build_fixture_tar(tar_path, big_mb=4):
    """构造测试用 tar 包，返回 {相对路径: 描述} 清单。"""
    manifest = {}
    big = rand_bytes(big_mb * 1024 * 1024, 20240521)

    entries = []
    # ---- 目录 ----
    for d, mode in [("system", 0o755), ("system/bin", 0o755), ("system/lib64", 0o755),
                    ("system/priv-app", 0o755), ("system/priv-app/MyApp", 0o755),
                    ("vendor", 0o755), ("vendor/lib64", 0o755),
                    ("etc", 0o755), ("etc/init", 0o750),
                    ("usr/share", 0o755), ("emptydir", 0o755),
                    ("a/b/c/d/e/f/g", 0o755),
                    ("\u4e2d\u6587\u76ee\u5f55", 0o755),
                    ("apps/\u6211\u7684\u5e94\u7528", 0o755),
                    ("path with space", 0o755)]:
        entries.append((_ti(d, mode=mode, typ=tarfile.DIRTYPE), None))
        manifest[d] = "dir mode=%o" % mode

    # ---- 普通文件 ----
    files = [
        ("etc/hosts", b"127.0.0.1 localhost\n::1 localhost\n", 0o644, 0, 0),
        ("system/bin/mksh", b"#!/system/bin/sh\necho mksh\n", 0o755, 0, 2000),
        ("system/bin/toolbox", b"#!toolbox\n" + b"x" * 4096, 0o755, 0, 2000),
        ("vendor/lib64/libfoo.so", rand_bytes(300 * 1024, 7), 0o644, 0, 0),
        ("vendor/lib64/libbar.so", rand_bytes(300 * 1024, 7), 0o644, 0, 0),   # 内容相同，测去重
        ("system/priv-app/MyApp/base.apk", big, 0o644, 1000, 1000),
        ("usr/share/zeros.bin", b"\0" * (1024 * 1024), 0o644, 0, 0),
        ("usr/share/text.txt", (b"the quick brown fox jumps over the lazy dog\n" * 20000), 0o644, 0, 0),
        ("usr/share/readonly.txt", b"read only file\n", 0o444, 0, 0),
        ("etc/init/secret.conf", b"secret=1\n", 0o600, 0, 0),
        ("etc/init/empty.conf", b"", 0o644, 0, 0),
        ("a/b/c/d/e/f/g/deep.txt", b"deep\n", 0o644, 0, 0),
        ("\u4e2d\u6587\u76ee\u5f55/\u4e2d\u6587\u6587\u4ef6.txt",
         "\u4f60\u597d\uff0cEROFS\uff01\n".encode("utf-8"), 0o644, 0, 0),
        ("apps/\u6211\u7684\u5e94\u7528/\u8bf4\u660e.md",
         "# \u8bf4\u660e\n\u8fd9\u662f\u4e00\u4e2a\u6d4b\u8bd5\u6587\u4ef6\u3002\n".encode("utf-8"), 0o644, 0, 0),
        ("path with space/file name.txt", b"space in name\n", 0o644, 0, 0),
        ("system/priv-app/MyApp/\u5e26#\u7b26\u53f7.txt", b"hash\n", 0o644, 0, 0),
    ]
    for name, data, mode, uid, gid in files:
        ti = _ti(name, mode=mode, uid=uid, gid=gid)
        ti.size = len(data)
        entries.append((ti, data))
        manifest[name] = "file size=%d mode=%o uid=%d gid=%d sha256=%s" % (
            len(data), mode, uid, gid, hashlib.sha256(data).hexdigest())

    # ---- 硬链接（与 system/bin/mksh 同 inode） ----
    ti = _ti("system/bin/sh", mode=0o755, typ=tarfile.LNKTYPE)
    ti.linkname = "system/bin/mksh"
    entries.append((ti, None))
    manifest["system/bin/sh"] = "hardlink -> system/bin/mksh"

    # ---- 符号链接 ----
    links = [
        ("system/bin/sh_link", "mksh"),                       # 相对
        ("system/bin/mksh_abs", "/system/bin/mksh"),          # 绝对（Android 里到处都是）
        ("vendor/lib64/libfoo.so.1", "libfoo.so"),
        ("broken_link", "nowhere/does_not_exist"),            # 悬空链接
        ("\u4e2d\u6587\u94fe\u63a5", "\u4e2d\u6587\u76ee\u5f55/\u4e2d\u6587\u6587\u4ef6.txt"),
        ("system/lib64_alias", "/vendor/lib64"),              # 指向目录（绝对）
        ("vendor/syslib", "../system"),                       # 指向目录（相对）
    ]
    for name, target in links:
        ti = _ti(name, mode=0o777, typ=tarfile.SYMTYPE)
        ti.linkname = target
        entries.append((ti, None))
        manifest[name] = "symlink -> " + target

    with tarfile.open(tar_path, "w", format=tarfile.GNU_FORMAT) as tf:
        for ti, data in entries:
            if data is None:
                tf.addfile(ti)
            else:
                tf.addfile(ti, io.BytesIO(data))
    return manifest


def build_torture_tar(tar_path):
    """带特殊文件（设备节点 / FIFO）的 tar，用来观察引擎在 Windows 上的行为。"""
    manifest = {}
    entries = []
    entries.append((_ti("dev", mode=0o755, typ=tarfile.DIRTYPE), None))
    ti = _ti("dev/null", mode=0o666, typ=tarfile.CHRTYPE)
    ti.devmajor, ti.devminor = 1, 3
    entries.append((ti, None))
    manifest["dev/null"] = "chardev 1:3"
    ti = _ti("dev/urandom", mode=0o666, typ=tarfile.CHRTYPE)
    ti.devmajor, ti.devminor = 1, 9
    entries.append((ti, None))
    manifest["dev/urandom"] = "chardev 1:9"
    entries.append((_ti("dev/fifo", mode=0o644, typ=tarfile.FIFOTYPE), None))
    manifest["dev/fifo"] = "fifo"
    data = b"torture\n"
    ti = _ti("normal.txt", mode=0o644)
    ti.size = len(data)
    entries.append((ti, data))
    manifest["normal.txt"] = "file"
    with tarfile.open(tar_path, "w", format=tarfile.GNU_FORMAT) as tf:
        for ti, d in entries:
            if d is None:
                tf.addfile(ti)
            else:
                tf.addfile(ti, io.BytesIO(d))
    return manifest


# 覆盖各种压缩算法与布局选项（tar 源）
VARIANTS = [
    ("plain", []),
    ("lz4", ["-zlz4"]),
    ("lz4hc9", ["-zlz4hc,9"]),
    ("lzma", ["-zlzma,9"]),
    ("zstd", ["-zzstd,9"]),
    ("deflate", ["-zdeflate,9"]),
    ("chunk64k", ["-zlz4", "-C65536"]),
    ("chunksize", ["-zlz4", "--chunksize=4096"]),
    ("dedupe", ["-zlz4", "-Ededupe"]),
    ("allroot", ["-zlz4", "--all-root"]),
    ("ztailpacking", ["-zlz4", "-C65536", "-Eztailpacking"]),
]

# 这几项在 tar 源下会报 "failed to initialize packedfile/metadata"，
# 改用普通目录当源来测（见 make_layout_fixtures）。
LAYOUT_VARIANTS = [
    ("fragments", ["-zlz4", "-Efragments"]),
    ("metacomp", ["-zlz4", "-m4096"]),
    ("dircompress", ["-zlz4", "--zD"]),
]


def run_engine(name, args, log=True):
    argv = [core.tool_path(name)] + args
    env = os.environ.copy()
    env["PATH"] = core.engine_dir() + os.pathsep + env.get("PATH", "")
    env.setdefault("LC_ALL", "C.UTF-8")
    p = subprocess.run(argv, capture_output=True, env=env, cwd=core.engine_dir())
    out = (p.stdout + p.stderr).decode("utf-8", "replace")
    if log and p.returncode != 0:
        print("    ! %s 返回 %d: %s" % (name, p.returncode, out.strip()[:300]))
    return p.returncode, out


def _cyg(p):
    return os.path.abspath(p).replace("\\", "/")


def mkfs_from_tar(img_path, tar_path, opts=(), log=True):
    """用 mkfs.erofs --tar 把 tar 压成 EROFS 镜像。

    注意：--tar 是必须的，否则 mkfs 会把 tar 当成"待重建的已有镜像"来解析。
    """
    args = list(opts) + ["--tar", "-T", "1700000000", _cyg(img_path), _cyg(tar_path)]
    return run_engine("mkfs.erofs", args, log=log)


def make_layout_fixtures(out_dir=None, log=True):
    """高级布局（fragments / 元数据压缩 / 目录压缩）：这几项用普通目录当源。

    返回 [(name, img_path, src_dir)]，src_dir 用来逐文件比对。
    """
    out_dir = out_dir or os.path.join(ROOT, "test", "fixtures")
    os.makedirs(out_dir, exist_ok=True)
    src = os.path.join(out_dir, "layout_src")
    shutil.rmtree(src, ignore_errors=True)
    os.makedirs(os.path.join(src, "bin"))
    os.makedirs(os.path.join(src, "lib64"))
    os.makedirs(os.path.join(src, "empty"))
    with open(os.path.join(src, "bin", "sh"), "wb") as f:
        f.write(b"#!/system/bin/sh\necho hello\n")
    with open(os.path.join(src, "lib64", "liba.so"), "wb") as f:
        f.write(rand_bytes(200 * 1024, 3))
    with open(os.path.join(src, "lib64", "libb.so"), "wb") as f:
        f.write(rand_bytes(200 * 1024, 3))          # 同内容，测去重
    with open(os.path.join(src, "text.txt"), "wb") as f:
        f.write(b"compress me please\n" * 5000)
    with open(os.path.join(src, "\u4e2d\u6587.txt"), "wb") as f:
        f.write("\u4e2d\u6587\u5185\u5bb9\n".encode("utf-8"))

    made = []
    for name, opts in LAYOUT_VARIANTS:
        img = os.path.join(out_dir, "layout_%s.img" % name)
        if os.path.exists(img):
            os.remove(img)
        rc, out = run_engine("mkfs.erofs", opts + ["-T", "1700000000", _cyg(img), _cyg(src)],
                             log=log)
        if rc != 0 or not os.path.exists(img) or os.path.getsize(img) > (4 << 30):
            if log:
                print("  [跳过] %-12s mkfs 失败（该布局可能要求 Linux 环境）" % name)
            try:
                if os.path.exists(img):
                    os.remove(img)
            except OSError:
                pass
            continue
        made.append((name, img, src))
        if log:
            print("  [生成] %-12s %8.1f KB  %s" % (name, os.path.getsize(img) / 1024.0, " ".join(opts)))
    return made


def make_all(out_dir=None, quick=False, log=True):
    """生成全部测试镜像，返回 [(variant, img_path, tar_path, manifest)]。"""
    out_dir = out_dir or os.path.join(ROOT, "test", "fixtures")
    os.makedirs(out_dir, exist_ok=True)
    tar_path = os.path.join(out_dir, "fixture_src.tar")
    manifest = build_fixture_tar(tar_path, big_mb=1 if quick else 4)
    torture_tar = os.path.join(out_dir, "torture_src.tar")
    build_torture_tar(torture_tar)

    made = []
    for name, opts in VARIANTS:
        if quick and name in ("deflate", "ztailpacking", "allroot", "zstd", "chunksize"):
            continue
        img = os.path.join(out_dir, "fixture_%s.img" % name)
        if os.path.exists(img):
            os.remove(img)
        t0 = time.time()
        rc, out = mkfs_from_tar(img, tar_path, opts, log=log)
        if rc != 0 or not os.path.exists(img) or os.path.getsize(img) > (4 << 30):
            if log:
                print("  [跳过] %-12s mkfs 失败%s" % (
                    name, "（留下了异常大的文件，已删除）" if os.path.exists(img) else ""))
            try:
                if os.path.exists(img):
                    os.remove(img)      # mkfs 失败时可能留下巨大的稀疏文件
            except OSError:
                pass
            continue
        made.append((name, img, tar_path, manifest))
        if log:
            print("  [生成] %-12s %8.1f KB  %.2fs  %s" % (
                name, os.path.getsize(img) / 1024.0, time.time() - t0, " ".join(opts) or "(不压缩)"))
    # 超大镜像（顺便测吞吐）
    if not quick:
        big_tar = os.path.join(out_dir, "big_src.tar")
        big_manifest = _build_big_tar(big_tar, 96)
        img = os.path.join(out_dir, "fixture_big.img")
        rc, _ = mkfs_from_tar(img, big_tar, ["-zlz4"], log=log)
        if rc == 0:
            made.append(("big", img, big_tar, big_manifest))
            print("  [生成] %-12s %8.1f MB" % ("big", os.path.getsize(img) / 1048576.0))
    return made


def _build_big_tar(tar_path, mb):
    """一个 ~48MB 的镜像，用来测解压速度。"""
    manifest = {}
    rng = random.Random(99)
    with tarfile.open(tar_path, "w", format=tarfile.GNU_FORMAT) as tf:
        for i in range(mb // 8):
            data = rng.getrandbits(8 * (8 * 1024 * 1024)).to_bytes(8 * 1024 * 1024, "little")
            name = "data/chunk%02d.bin" % i
            ti = _ti(name, mode=0o644)
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
            manifest[name] = "file size=%d sha256=%s" % (len(data), hashlib.sha256(data).hexdigest())
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    print("引擎：fsck.erofs %s @ %s" % (core.engine_version(), core.engine_dir()))
    made = make_all(args.out, quick=args.quick)
    print("\n共生成 %d 个测试镜像" % len(made))
    return 0 if made else 1


if __name__ == "__main__":
    sys.exit(main())
