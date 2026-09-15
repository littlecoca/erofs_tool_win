# -*- coding: utf-8 -*-
# SPDX-License-Identifier: 0BSD
"""复现"偶发的 fsck.erofs 返回 1 且零输出"。

用法：python tools\\probe_flake.py [轮数]
"""

import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from imgtool import core  # noqa: E402

FX = os.path.join(ROOT, "test", "finalcheck", "fixtures")
WORK = os.path.join(ROOT, "test", "finalcheck", "out")


def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    print("=" * 70)
    print("复现测试：连续解压 %d 次，看是否偶发 rc=1 且零输出" % rounds)
    print("=" * 70)

    # 准备镜像（复用现有 fixtures，没有就现场造）
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    from tests import make_fixtures as mf
    if not os.path.isdir(FX):
        mf.make_all(FX, quick=True)
    imgs = [f for f in sorted(os.listdir(FX)) if f.endswith(".img")]
    if not imgs:
        print("没有测试镜像")
        return 1
    print("可用镜像：%s" % ", ".join(imgs))

    fails = 0
    t0 = time.time()
    for i in range(rounds):
        name = imgs[i % len(imgs)]
        img = os.path.join(FX, name)
        out = os.path.join(WORK, "r%02d" % i)
        core.safe_rmtree(out)
        size = os.path.getsize(img)
        try:
            res = core.extract_image(img, dest=out, policy="overwrite", symlinks="keep")
            status = "ok %d 个文件" % res.files
        except Exception as e:
            fails += 1
            status = "FAIL %s | %s" % (type(e).__name__, str(e)[:160])
        print("  #%02d %-26s size=%-9d %s" % (i, name, size, status))
        core.safe_rmtree(out)

    print("-" * 70)
    print("共 %d 轮，失败 %d 次，用时 %.1fs" % (rounds, fails, time.time() - t0))

    # 顺带做一次"裸调引擎"对照：完全绕过 core.py，看是不是引擎本身的问题
    print("\n裸调引擎对照（直接 Popen 同一个镜像 5 次）：")
    img = os.path.join(FX, imgs[0])
    out = os.path.join(WORK, "raw")
    env = os.environ.copy()
    env["PATH"] = core.engine_dir() + os.pathsep + env.get("PATH", "")
    env["LC_ALL"] = "C.UTF-8"
    env["CYGWIN"] = "winsymlinks:sys"
    for i in range(5):
        core.safe_rmtree(out)
        os.makedirs(out)
        argv = [core.tool_path("fsck.erofs"), "--extract=" + out.replace("\\", "/"),
                "-d2", img.replace("\\", "/")]
        p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           env=env, cwd=core.engine_dir())
        print("  #%d rc=%d 输出=%r" % (i, p.returncode, p.stdout[:120]))
    core.safe_rmtree(out)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
