# -*- coding: utf-8 -*-
# SPDX-License-Identifier: 0BSD
"""最小复现：WM_DROPFILES 回调里"碰 Tk" vs "只入队"，看哪个会崩。

纯 Tk，不需要引擎，也不用放宽沙箱。
"""
import sys
import time
import tkinter as tk

sys.path.insert(0, r"D:\project_practice\img_tool")
from imgtool import dnd  # noqa: E402

MODE = sys.argv[1] if len(sys.argv) > 1 else "touch"
FAKE = r"D:\project_practice\img_tool\test\gui\dropped.img"

root = tk.Tk()
root.geometry("320x160")
root.title("dnd probe: " + MODE)
label = tk.Label(root, text="等待拖放…")
label.pack()
received = []


def on_drop(paths):
    received.append(list(paths))
    if MODE == "touch":
        # 危险动作：在 WndProc 回调里直接操作 Tk 控件
        label.config(text="收到 %d 个" % len(paths))


dt = dnd.DropTarget(root, on_drop)
root.update()
print("available =", dt.available, "hwnd =", dt.hwnd)
dnd.post_drop(dt.hwnd, [FAKE])
print("消息已投递，开始泵事件…")
deadline = time.time() + 8
while time.time() < deadline and not received:
    root.update()
    time.sleep(0.05)
print("结果：received =", received)
if received and MODE == "touch":
    label.config(text="最终 %d 个" % len(received[0]))
    root.update()
dt.close()
root.destroy()
print("MODE=%s -> OK" % MODE)
