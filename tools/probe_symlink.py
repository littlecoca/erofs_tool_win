# -*- coding: utf-8 -*-
# SPDX-License-Identifier: 0BSD
"""探测 Cygwin 符号链接的落盘形态，决定工具该怎么后处理。

比较 4 种 CYGWIN=winsymlinks:* 设置下 fsck.erofs 解压出来的符号链接：
能不能被 Windows 读、内容是什么、能不能当符号链接用。
顺带验证 --overwrite 行为、junction 可行性。
"""

import ctypes
import os
import shutil
import struct
import subprocess
import sys
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from imgtool import core  # noqa: E402

FX = os.path.join(ROOT, "test", "e2e", "fixtures", "fixture_lz4.img")
WORK = os.path.join(ROOT, "test", "symprobe")
if not os.path.exists(FX):
    print("缺少 %s，先跑 tests/make_fixtures.py" % FX)
    sys.exit(1)

CASES = [
    ("default", None),
    ("sys", "winsymlinks:sys"),
    ("native", "winsymlinks:native"),
    ("nativestrict", "winsymlinks:nativestrict"),
    ("sys_all", "winsymlinks:sys,error_start:WinALT"),
]

RELPATHS = [
    "system/bin/sh_link",
    "system/bin/mksh_abs",
    "vendor/lib64/libfoo.so.1",
    "broken_link",
    "\u4e2d\u6587\u94fe\u63a5",
]

FILE_ATTRIBUTE_REPARSE_POINT = 0x400
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
GENERIC_READ = 0x80000000
OPEN_EXISTING = 3

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateFileW.restype = wintypes.HANDLE
_k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                             ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]


def raw_read(path, n=256):
    """用 OPEN_REPARSE_POINT 打开，绕过重解析点直接读文件数据。"""
    h = _k32.CreateFileW(path, GENERIC_READ, 7, None, OPEN_EXISTING,
                         FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS, None)
    if h == -1 or h == 0xFFFFFFFFFFFFFFFF:
        return None, "CreateFile 失败 err=%d" % ctypes.get_last_error()
    buf = ctypes.create_string_buffer(n)
    read = wintypes.DWORD()
    ok = _k32.ReadFile(h, buf, n, ctypes.byref(read), None)
    _k32.CloseHandle(h)
    if not ok:
        return None, "ReadFile 失败 err=%d" % ctypes.get_last_error()
    return buf.raw[:read.value], None


def describe(path):
    out = {}
    try:
        st = os.lstat(path)
        out["attr"] = st.st_file_attributes
        out["reparse"] = bool(st.st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT)
        out["size"] = st.st_size
    except OSError as e:
        out["stat_err"] = "err=%s" % e.winerror
    try:
        with open(path, "rb") as f:
            out["readable"] = f.read(120)
    except OSError as e:
        out["readable"] = "READ FAIL err=%s" % e.winerror
    data, err = raw_read(path)
    out["raw"] = data if data is not None else ("RAW FAIL " + str(err))
    try:
        out["islink"] = os.path.islink(path)
        if out["islink"]:
            out["target"] = os.readlink(path)
    except OSError:
        pass
    return out


def main():
    print("=" * 78)
    print("Cygwin 符号链接落盘形态探测")
    print("=" * 78)
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)

    for name, cyg in CASES:
        out = os.path.join(WORK, "out_" + name)
        os.makedirs(out)
        env = os.environ.copy()
        env["PATH"] = core.engine_dir() + os.pathsep + env.get("PATH", "")
        env["LC_ALL"] = "C.UTF-8"
        if cyg:
            env["CYGWIN"] = cyg
        else:
            env.pop("CYGWIN", None)
        cmd = [core.tool_path("fsck.erofs"), "--extract=" + out.replace("\\", "/"),
               "-d0", FX.replace("\\", "/")]
        p = subprocess.run(cmd, capture_output=True, env=env, cwd=core.engine_dir())
        print("\n" + "-" * 78)
        print("### CYGWIN=%s   rc=%d" % (cyg or "(未设置)", p.returncode))
        if p.returncode != 0:
            print("   stderr:", (p.stdout + p.stderr).decode("utf-8", "replace")[:300])
        for rel in RELPATHS:
            path = os.path.join(out, *rel.split("/"))
            if not os.path.exists(path) and not os.path.lexists(path):
                print("   %-32s 不存在！" % rel)
                continue
            d = describe(path)
            raw = d.get("raw")
            if isinstance(raw, bytes):
                raw = raw.replace(b"\0", b"")[:60]
            rd = d.get("readable")
            if isinstance(rd, bytes):
                rd = rd.replace(b"\0", b"")[:60]
            print("   %-32s size=%-4s attr=%#x reparse=%s islink=%s" %
                  (rel, d.get("size", d.get("stat_err")), d.get("attr", 0),
                   d.get("reparse"), d.get("islink", False)))
            print("        可读=%r  原始数据=%r  目标=%r" % (rd, raw, d.get("target")))

    # ---- --overwrite 行为 ----
    print("\n" + "=" * 78)
    print("### --overwrite 行为验证")
    out = os.path.join(WORK, "overwrite")
    os.makedirs(out)

    def run_fsck(extra):
        env = os.environ.copy()
        env["PATH"] = core.engine_dir() + os.pathsep + env.get("PATH", "")
        cmd = [core.tool_path("fsck.erofs"), "--extract=" + out.replace("\\", "/")] + extra + [FX.replace("\\", "/")]
        return subprocess.run(cmd, capture_output=True, env=env, cwd=core.engine_dir())

    p1 = run_fsck(["-d0"])
    p2 = run_fsck(["-d0"])                      # 第二次不覆盖
    p3 = run_fsck(["-d0", "--overwrite"])       # 第二次带覆盖
    print("第一次 rc=%d；第二次(无 --overwrite) rc=%d；第三次(--overwrite) rc=%d"
          % (p1.returncode, p2.returncode, p3.returncode))
    print("第二次输出:", (p2.stdout + p2.stderr).decode("utf-8", "replace").strip()[:200])
    print("第三次输出:", (p3.stdout + p3.stderr).decode("utf-8", "replace").strip()[:200])

    # ---- junction 可行性 ----
    print("\n" + "=" * 78)
    print("### 无管理员权限下创建 junction / 符号链接")
    tgt = os.path.join(WORK, "target_dir")
    os.makedirs(tgt, exist_ok=True)
    open(os.path.join(tgt, "x.txt"), "w").write("x")
    junc = os.path.join(WORK, "my_junction")
    r = subprocess.run(["cmd", "/c", "mklink", "/J", junc, tgt], capture_output=True)
    print("mklink /J ->", (r.stdout + r.stderr).decode("gbk", "replace").strip()[:120],
          "| 存在:", os.path.isdir(junc))
    link = os.path.join(WORK, "my_symlink.txt")
    try:
        os.symlink("target_dir/x.txt", link)
        print("os.symlink 文件链接 -> 成功")
    except OSError as e:
        print("os.symlink 文件链接 -> 失败 err=%s %s" % (e.winerror, e.strerror))

    print("\n完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
