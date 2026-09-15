# -*- coding: utf-8 -*-
# SPDX-License-Identifier: 0BSD
"""GUI + 拖放自测。

真的把窗口开出来，然后用 Windows 消息（WM_DROPFILES）模拟一次"把文件拖进窗口"，
验证：拖放回调 -> 任务入列 -> 自动解压 -> 输出目录生成 -> 界面状态变成"完成"。

跑法（需要放宽沙箱，因为要启动 Cygwin 引擎）：
    python tests/gui_test.py
"""

import ctypes
import os
import shutil
import sys
import time
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from imgtool import core, dnd, gui                # noqa: E402
from tests import make_fixtures                   # noqa: E402

OUT = os.path.join(ROOT, "test", "gui")


def main():
    print("=" * 78)
    print("GUI / 拖放自测")
    print("=" * 78)

    # 准备一个测试镜像
    fx = os.path.join(ROOT, "test", "e2e", "fixtures")
    src_img = os.path.join(fx, "fixture_lz4.img")
    if not os.path.exists(src_img):
        print("先生成测试镜像…")
        make_fixtures.make_all(fx, quick=True)
    if not os.path.exists(src_img):
        print("[FAIL] 没有测试镜像，无法继续")
        return 1

    core.safe_rmtree(OUT)
    os.makedirs(OUT)
    img = os.path.join(OUT, "dropped.img")
    shutil.copyfile(src_img, img)

    root = tk.Tk()
    app = gui.App(root)
    root.update()                      # 让窗口真正创建出来

    print("窗口已创建，拖放可用 =", app.drop_target.available if app.drop_target else False)
    if not (app.drop_target and app.drop_target.available):
        print("[FAIL] 拖放初始化失败")
        return 1

    # 关掉"完成后打开目录"以免测试时弹资源管理器
    app.var_open_after.set(False)

    # ---- 模拟真实拖放 ----
    hwnd = app.drop_target.hwnd
    print("向窗口 %s 投递 WM_DROPFILES：%s" % (hwnd, img))
    dnd.post_drop(hwnd, [img])

    deadline = time.time() + 120
    while time.time() < deadline:
        root.update()
        if app.tasks and app.tasks[0].status in ("完成", "失败"):
            break
        time.sleep(0.05)
    root.update()

    ok = True
    if not app.tasks:
        print("[FAIL] 拖放没有产生任务")
        ok = False
    else:
        t = app.tasks[0]
        print("任务状态：%s" % t.status)
        print("输出目录：%s" % t.dest)
        if t.status != "完成":
            print("[FAIL] 解压未完成：%s" % (t.error or t.status))
            ok = False
        expect = os.path.join(OUT, "dropped")
        if os.path.normcase(t.dest) != os.path.normcase(expect):
            print("[FAIL] 输出目录不是同名文件夹：%s != %s" % (t.dest, expect))
            ok = False
        else:
            print("[PASS] 拖放 -> 解压到同名文件夹")
        n = sum(len(f) for _r, _d, f in os.walk(expect)) if os.path.isdir(expect) else 0
        print("解压出 %d 个文件" % n)
        if n == 0:
            print("[FAIL] 目录是空的")
            ok = False

    # 顺带验证界面上的中文文件名显示
    txt = app.status.cget("text")
    print("状态栏：%s" % txt)

    app.drop_target.close()
    root.destroy()
    print("=" * 78)
    print("结果：%s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
