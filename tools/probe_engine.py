# -*- coding: utf-8 -*-
# SPDX-License-Identifier: 0BSD
"""Probe the Cygwin erofs-utils engine: options, codecs, edge cases.

Run with a widened sandbox (Cygwin needs to create its signal pipe).
"""
import hashlib
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(ROOT, "engine")
WORK = os.path.join(ROOT, "test", "probe")


def W(p):
    """cygwin-friendly windows path (forward slashes)"""
    return os.path.abspath(p).replace("\\", "/")


def run(argv, timeout=600):
    t0 = time.time()
    env = dict(os.environ)
    env["PATH"] = ENGINE + os.pathsep + env.get("PATH", "")
    p = subprocess.run(argv, capture_output=True, env=env, cwd=ENGINE, timeout=timeout)
    dt = time.time() - t0

    def dec(b):
        for enc in ("utf-8", "gbk", "latin-1"):
            try:
                return b.decode(enc)
            except Exception:
                continue
        return repr(b)
    return p.returncode, dec(p.stdout), dec(p.stderr), dt


def exe(name):
    return os.path.join(ENGINE, name + ".exe")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def section(t):
    print("\n" + "=" * 72 + "\n== " + t + "\n" + "=" * 72)


# ---------------------------------------------------------------- help texts
for tool in ("fsck.erofs", "mkfs.erofs", "extract.erofs", "dump.erofs"):
    section(tool + " --help")
    rc, out, err, _ = run([exe(tool), "--help"])
    print("rc=%s" % rc)
    print(out[:4000])
    if err.strip():
        print("[stderr]", err[:800])

# ---------------------------------------------------------------- test tree
section("build test tree")
shutil.rmtree(WORK, ignore_errors=True)
src = os.path.join(WORK, "src")
os.makedirs(os.path.join(src, "a", "b", "c"))
with open(os.path.join(src, "hello.txt"), "w", newline="") as f:
    f.write("hello erofs\n")
with open(os.path.join(src, "a", "b", "c", "deep.txt"), "w") as f:
    f.write("deep" * 1000)
with open(os.path.join(src, "\u4e2d\u6587\u540d\u4ef6.txt"), "w", encoding="utf-8") as f:
    f.write("\u4e2d\u6587\u5185\u5bb9 content\n")
with open(os.path.join(src, "with space.txt"), "w") as f:
    f.write("space\n")
blob = os.urandom(3 * 1024 * 1024)
with open(os.path.join(src, "blob.bin"), "wb") as f:
    f.write(blob)
with open(os.path.join(src, "zeros.bin"), "wb") as f:
    f.write(b"\0" * (512 * 1024))
os.makedirs(os.path.join(src, "emptydir"))
os.makedirs(os.path.join(src, "\u4e2d\u6587\u76ee\u5f55"))
with open(os.path.join(src, "\u4e2d\u6587\u76ee\u5f55", "inner.log"), "w") as f:
    f.write("inner\n")

link_ok = True
try:
    os.symlink("hello.txt", os.path.join(src, "link_to_hello"))
    os.symlink("/vendor/lib64", os.path.join(src, "abs_link"))
    print("symlink: OS SUPPORTS (created via os.symlink)")
except Exception as e:
    link_ok = False
    print("symlink: NOT AVAILABLE ->", type(e).__name__, e)
try:
    os.link(os.path.join(src, "hello.txt"), os.path.join(src, "hardlink_hello"))
    print("hardlink: created")
except Exception as e:
    print("hardlink: FAILED ->", type(e).__name__, e)

for dirpath, dirnames, filenames in os.walk(src):
    for fn in filenames:
        p = os.path.join(dirpath, fn)
        print("   %-42s %9d" % (os.path.relpath(p, src), os.path.getsize(p)))
print("symlink_ok=%s" % link_ok)

# ---------------------------------------------------------------- codec matrix
section("mkfs/fsck round trip across codecs")
CASES = [
    ("plain", []),
    ("lz4", ["-zlz4"]),
    ("lz4hc9", ["-zlz4hc,9"]),
    ("lzma", ["-zlzma,9"]),
    ("zstd", ["-zzstd,9"]),
    ("deflate", ["-zdeflate,9"]),
    ("lz4_chunk64k", ["-zlz4", "-C65536"]),
    ("lz4_frag", ["-zlz4", "-Efragments"]),
    ("lz4_dedup", ["-zlz4", "-Ededupe"]),
]
results = []
for name, opts in CASES:
    img = os.path.join(WORK, "img_%s.img" % name)
    out = os.path.join(WORK, "out_%s" % name)
    shutil.rmtree(out, ignore_errors=True)
    rc, so, se, dt = run([exe("mkfs.erofs")] + opts + ["-T", "1700000000", W(img), W(src)])
    if rc != 0:
        line = "%-14s MKFS-FAIL rc=%s %s" % (name, rc, (se or so).strip().replace("\n", " ")[:150])
        print(line)
        results.append((name, "mkfs-fail", 0, 0, 0))
        continue
    size = os.path.getsize(img)
    rc2, so2, se2, dt2 = run([exe("fsck.erofs"), "--extract=" + W(out), W(img)])
    if rc2 != 0:
        print("%-14s FSCK-FAIL rc=%s %s" % (name, rc2, (se2 or so2).strip().replace("\n", " ")[:150]))
        results.append((name, "fsck-fail", size, dt, dt2))
        continue
    # compare
    bad = []
    nfile = 0
    for dirpath, dirnames, filenames in os.walk(src):
        for fn in filenames:
            sp = os.path.join(dirpath, fn)
            rel = os.path.relpath(sp, src)
            dp = os.path.join(out, rel)
            if os.path.islink(sp):
                if not os.path.islink(dp) or os.readlink(sp) != os.readlink(dp):
                    bad.append("symlink:" + rel)
                else:
                    nfile += 1
                continue
            nfile += 1
            if not os.path.exists(dp):
                bad.append("missing:" + rel)
            elif sha(sp) != sha(dp):
                bad.append("mismatch:" + rel)
    print("%-14s OK  img=%8d  nfiles=%d  mkfs=%.2fs  fsck=%.2fs  bad=%s" % (
        name, size, nfile, dt, dt2, bad if bad else "none"))
    results.append((name, "ok" if not bad else "bad", size, dt, dt2))

# ---------------------------------------------------------------- error cases
section("error handling on non-EROFS input")
junk = os.path.join(WORK, "junk.img")
with open(junk, "wb") as f:
    f.write(os.urandom(64 * 1024))
rc, so, se, _ = run([exe("fsck.erofs"), "--extract=" + W(os.path.join(WORK, "out_junk")), W(junk)])
print("junk rc=%s\n out=%s\n err=%s" % (rc, so.strip()[:400], se.strip()[:400]))

# android sparse magic
sparse = os.path.join(WORK, "fake_sparse.img")
with open(sparse, "wb") as f:
    f.write((0xED26FF3A).to_bytes(4, "little") + b"\0" * 4092)
rc, so, se, _ = run([exe("fsck.erofs"), W(sparse)])
print("sparse-magic rc=%s\n out=%s\n err=%s" % (rc, so.strip()[:300], se.strip()[:300]))

section("SUMMARY")
for r in results:
    print("   %-14s %-10s size=%-9s" % r[:3])
print("\nDONE")
