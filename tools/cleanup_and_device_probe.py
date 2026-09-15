# -*- coding: utf-8 -*-
# SPDX-License-Identifier: 0BSD
"""收尾诊断：清掉探测残留的 LX_SYMLINK 顽固文件 + 看设备节点在镜像里/解压后分别是什么。"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from imgtool import core  # noqa: E402

print("=" * 70)
print("1) 清理 test\\symprobe（里面是 Cygwin 默认模式造的 WSL LX_SYMLINK 重解析点）")
p = os.path.join(ROOT, "test", "symprobe")
print("   safe_rmtree ->", core.safe_rmtree(p), " 仍存在:", os.path.lexists(p))
if os.path.lexists(p):
    r = subprocess.run(["cmd", "/c", "rd", "/s", "/q", p], capture_output=True)
    print("   rd /s /q ->", r.returncode, (r.stdout + r.stderr).decode("gbk", "replace").strip()[:200])
    print("   仍存在:", os.path.lexists(p))

print()
print("=" * 70)
print("2) 设备节点：镜像里是什么、解压后变成什么")
img = os.path.join(ROOT, "test", "e2e", "fixtures", "fixture_torture.img")
if os.path.exists(img):
    info = core.image_info(img)
    nid = info.get("filesystem_root_nid", "").split()[0] if info.get("filesystem_root_nid") else ""
    print("   镜像 root nid = %r" % nid)
    if nid:
        env = os.environ.copy()
        env["PATH"] = core.engine_dir() + os.pathsep + env.get("PATH", "")
        env["CYGWIN"] = "winsymlinks:sys"
        for args in (["--ls", "--nid=" + nid, img.replace("\\", "/")],
                     ["--ls", "--path=/dev", img.replace("\\", "/")]):
            r = subprocess.run([core.tool_path("dump.erofs")] + args,
                               capture_output=True, env=env, cwd=core.engine_dir())
            out = (r.stdout + r.stderr).decode("utf-8", "replace").strip()
            print("   $ dump.erofs %s\n     rc=%d %s" % (" ".join(args[:-1]), r.returncode,
                                                         out.replace("\n", "\n     ")[:600]))
else:
    print("   [跳过] 还没有 torture 镜像")

dev = os.path.join(ROOT, "test", "e2e", "torture", "out", "dev")
if os.path.isdir(dev):
    print("   解压出来的 dev/ 内容：")
    for fn in sorted(os.listdir(dev)):
        fp = os.path.join(dev, fn)
        st = os.lstat(fp)
        try:
            with open(fp, "rb") as f:
                head = f.read(40)
        except OSError as e:
            head = "读不了: %s" % e
        print("     %-16s mode=%o attr=%#x size=%d head=%r" % (fn, st.st_mode, st.st_file_attributes,
                                                              st.st_size, head))
else:
    print("   [跳过] 还没有解压结果")

print()
print("=" * 70)
print("3) 引擎版本")
print("   fsck.erofs:", core.engine_version())
