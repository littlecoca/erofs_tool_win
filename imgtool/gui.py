# -*- coding: utf-8 -*-
# SPDX-License-Identifier: 0BSD
"""imgtool 图形界面：把 IMG 拖进来 -> 解压到同名文件夹。

* 原生拖放（ctypes 实现，不需要 tkinterdnd2）
* 后台线程解压，界面不卡；可取消
* 支持一次拖多个文件、支持拖文件夹（自动找里面的 .img）
"""

import os
import queue
import re
import sys
import threading
import time
import traceback

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from . import core
from . import dnd

APP_TITLE = "IMG 解压工具 · EROFS"
COL_BG = "#f5f6f8"
COL_CARD = "#ffffff"
COL_ACCENT = "#2d6cdf"
COL_OK = "#1a7f37"
COL_ERR = "#c0392b"
COL_MUTED = "#6b7280"


class Task(object):
    def __init__(self, path):
        self.path = path
        self.status = "等待中"
        self.dest = ""
        self.size = 0
        self.error = None


class App(object):
    def __init__(self, root):
        self.root = root
        self.tasks = []
        self.queue = queue.Queue()
        self.cancel_flag = threading.Event()
        self.worker = None
        self.drop_target = None
        self.current = None

        self._build_ui()
        self._install_dnd()
        self.root.after(80, self._pump)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        try:
            ver = core.engine_version()
        except Exception as e:
            ver = "未找到引擎（%s）" % e
        self.engine_label.config(text="引擎：fsck.erofs %s" % ver)
        self._exts_hint = "、".join(core.IMAGE_EXTS)

    # ------------------------------------------------------------- 界面
    def _build_ui(self):
        r = self.root
        r.title(APP_TITLE)
        r.geometry("820x660")
        r.minsize(680, 560)
        r.configure(bg=COL_BG)

        style = ttk.Style()
        try:
            style.theme_use("vista")
        except Exception:
            pass
        style.configure("TFrame", background=COL_BG)
        style.configure("TLabel", background=COL_BG, foreground="#111827")
        style.configure("Muted.TLabel", background=COL_BG, foreground=COL_MUTED)
        style.configure("Card.TFrame", background=COL_CARD, relief="flat")
        style.configure("TButton", padding=(10, 4))
        style.configure("Go.TButton", padding=(16, 6))
        style.configure("Treeview", rowheight=24)

        # 顶部标题
        head = ttk.Frame(r)
        head.pack(fill="x", padx=16, pady=(14, 6))
        ttk.Label(head, text=APP_TITLE, font=("Microsoft YaHei UI", 15, "bold")).pack(side="left")
        self.engine_label = ttk.Label(head, text="引擎：检查中…", style="Muted.TLabel")
        self.engine_label.pack(side="right")

        # 拖放区
        self.zone = tk.Canvas(r, height=132, bg=COL_CARD, highlightthickness=0, cursor="hand2")
        self.zone.pack(fill="x", padx=16, pady=(6, 0))
        self.zone.bind("<Configure>", self._draw_zone)
        self.zone.bind("<Button-1>", lambda e: self.choose_files())
        self._zone_text1 = "把 IMG 文件拖到这里"
        self._zone_text2 = "支持 .img / .bin / .erofs，Android sparse 镜像也行；也可以拖一个文件夹进来"
        self._draw_zone()

        # 选项
        opt = ttk.Frame(r)
        opt.pack(fill="x", padx=16, pady=(10, 0))

        ttk.Label(opt, text="输出位置：").grid(row=0, column=0, sticky="w")
        self.var_dest_mode = tk.StringVar(value="same")
        ttk.Radiobutton(opt, text="镜像同目录 · 同名文件夹", value="same",
                        variable=self.var_dest_mode, command=self._sync_dest).grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(opt, text="自定义目录", value="custom",
                        variable=self.var_dest_mode, command=self._sync_dest).grid(row=0, column=2, sticky="w", padx=(12, 4))
        self.var_custom = tk.StringVar(value="")
        self.entry_custom = ttk.Entry(opt, textvariable=self.var_custom, width=34, state="disabled")
        self.entry_custom.grid(row=0, column=3, sticky="we", padx=(0, 4))
        self.btn_browse = ttk.Button(opt, text="浏览…", command=self.choose_dir, state="disabled")
        self.btn_browse.grid(row=0, column=4, sticky="w")

        ttk.Label(opt, text="目录已存在：").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.var_policy = tk.StringVar(value="auto")
        pol = ttk.Combobox(opt, textvariable=self.var_policy, state="readonly", width=22,
                           values=["自动改名（加序号）", "覆盖（删除后重建）"])
        pol.grid(row=1, column=1, columnspan=2, sticky="w", pady=(6, 0))
        self._policy_map = {"自动改名（加序号）": "auto", "覆盖（删除后重建）": "overwrite"}
        pol.current(0)

        ttk.Label(opt, text="符号链接：").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.var_symlinks = tk.StringVar(value="native")
        sym = ttk.Combobox(opt, textvariable=self.var_symlinks, state="readonly", width=22,
                           values=["尽量还原成 Windows 链接",
                                   "还原不了就复制目标内容",
                                   "保留原样（不处理）"])
        sym.grid(row=2, column=1, columnspan=2, sticky="w", pady=(6, 0))
        self._symlink_map = {"尽量还原成 Windows 链接": "native",
                             "还原不了就复制目标内容": "copy",
                             "保留原样（不处理）": "keep"}
        sym.current(0)

        self.var_open_after = tk.BooleanVar(value=True)
        self.var_linklist = tk.BooleanVar(value=False)
        self.var_auto_start = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="完成后打开输出目录", variable=self.var_open_after)\
            .grid(row=1, column=3, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Checkbutton(opt, text="解压后同时列出符号链接清单", variable=self.var_linklist)\
            .grid(row=2, column=3, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Checkbutton(opt, text="拖进来就自动开始解压", variable=self.var_auto_start)\
            .grid(row=3, column=1, columnspan=2, sticky="w", pady=(6, 0))
        opt.columnconfigure(3, weight=1)

        # 任务列表
        mid = ttk.Frame(r)
        mid.pack(fill="both", expand=True, padx=16, pady=(12, 0))
        cols = ("file", "status", "dest")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", height=5)
        self.tree.heading("file", text="镜像文件")
        self.tree.heading("status", text="状态")
        self.tree.heading("dest", text="输出目录")
        self.tree.column("file", width=240, anchor="w")
        self.tree.column("status", width=110, anchor="w")
        self.tree.column("dest", width=400, anchor="w")
        vs = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        self.tree.tag_configure("ok", foreground=COL_OK)
        self.tree.tag_configure("err", foreground=COL_ERR)
        self.tree.tag_configure("run", foreground=COL_ACCENT)
        self.tree.bind("<Double-1>", self._open_row_dir)

        # 进度 + 按钮
        bottom = ttk.Frame(r)
        bottom.pack(fill="x", padx=16, pady=(10, 0))
        self.var_progress = tk.DoubleVar(value=0.0)
        self.bar = ttk.Progressbar(bottom, variable=self.var_progress, maximum=100.0)
        self.bar.pack(fill="x")
        row = ttk.Frame(r)
        row.pack(fill="x", padx=16, pady=(6, 0))
        self.status = ttk.Label(row, text="就绪：把 IMG 拖进来，或点上面的区域选文件", style="Muted.TLabel")
        self.status.pack(side="left")
        self.btn_cancel = ttk.Button(row, text="取消", command=self.cancel, state="disabled")
        self.btn_cancel.pack(side="right")
        self.btn_clear = ttk.Button(row, text="清空列表", command=self.clear_tasks)
        self.btn_clear.pack(side="right", padx=(0, 6))
        self.btn_go = ttk.Button(row, text="开始解压", style="Go.TButton",
                                 command=self.start, state="disabled")
        self.btn_go.pack(side="right", padx=(0, 6))

        # 日志
        logf = ttk.Frame(r)
        logf.pack(fill="both", expand=True, padx=16, pady=(10, 14))
        ttk.Label(logf, text="日志", style="Muted.TLabel").pack(anchor="w")
        self.log = tk.Text(logf, height=8, wrap="none", bg="#0f172a", fg="#d7e3ff",
                           insertbackground="#d7e3ff", relief="flat", font=("Consolas", 9))
        ls = ttk.Scrollbar(logf, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=ls.set, state="disabled")
        self.log.pack(side="left", fill="both", expand=True)
        ls.pack(side="right", fill="y")

    def _draw_zone(self, _evt=None):
        c = self.zone
        c.delete("all")
        w = max(c.winfo_width(), 10)
        h = max(c.winfo_height(), 10)
        c.create_rectangle(6, 6, w - 6, h - 6, outline="#b9c2d0", width=2, dash=(7, 5))
        c.create_text(w / 2, h / 2 - 16, text=self._zone_text1,
                      font=("Microsoft YaHei UI", 14, "bold"), fill="#1f2937")
        c.create_text(w / 2, h / 2 + 14, text=self._zone_text2,
                      font=("Microsoft YaHei UI", 9), fill=COL_MUTED)
        c.create_text(w / 2, h / 2 + 38, text="（点这里选文件）",
                      font=("Microsoft YaHei UI", 9), fill=COL_ACCENT)

    def _sync_dest(self):
        custom = self.var_dest_mode.get() == "custom"
        self.entry_custom.configure(state="normal" if custom else "disabled")
        self.btn_browse.configure(state="normal" if custom else "disabled")

    # ------------------------------------------------------------- 拖放
    def _install_dnd(self):
        def on_err(e):
            self._log("[拖放不可用] %s" % e)

        # 窗口过程里只入队，真正的处理放到 _pump（主线程）里做
        self.drop_target = dnd.DropTarget(self.root, None, on_err)
        if not self.drop_target.available:
            self._zone_text2 = "拖放初始化失败，请用「选择文件」按钮（或把文件拖到 拖放解压.cmd 上）"
            self._draw_zone()

    def add_paths(self, paths):
        added = []
        for p in paths:
            if os.path.isdir(p):
                for fn in sorted(os.listdir(p)):
                    fp = os.path.join(p, fn)
                    if core.is_image_file(fp):
                        added.append(fp)
                continue
            if os.path.isfile(p):
                added.append(p)
            else:
                self._log("[忽略] 不是文件：%s" % p)
        if not added:
            self._log("[提示] 没有可解压的镜像文件（支持 %s）" % self._exts_hint)
            return
        for p in added:
            if any(os.path.normcase(t.path) == os.path.normcase(p) for t in self.tasks):
                continue
            t = Task(p)
            try:
                t.size = os.path.getsize(p)
            except OSError:
                t.size = 0
            self.tasks.append(t)
            self.tree.insert("", "end", iid=str(len(self.tasks) - 1),
                             values=(os.path.basename(p), t.status, ""))
            self._log("[加入] %s（%s）" % (p, core.human_size(t.size)))
        self.btn_go.configure(state="normal")
        if not self.worker:
            self.status.config(text="已加入 %d 个文件，点「开始解压」（或直接回车）" % len(added))

    # ------------------------------------------------------------- 操作
    def choose_files(self):
        paths = filedialog.askopenfilenames(
            title="选择 IMG 镜像",
            filetypes=[("镜像文件", "*.img *.image *.bin *.erofs *.raw"), ("所有文件", "*.*")])
        if paths:
            self.add_paths(list(paths))

    def choose_dir(self):
        d = filedialog.askdirectory(title="选择输出目录")
        if d:
            self.var_custom.set(d)

    def clear_tasks(self):
        if self.worker:
            return
        self.tasks = []
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.btn_go.configure(state="disabled")
        self.var_progress.set(0)

    def cancel(self):
        if self.worker:
            self.cancel_flag.set()
            self.status.config(text="正在取消…")
            self._log("[取消] 已请求停止，等待当前镜像退出")

    def _open_row_dir(self, _evt):
        sel = self.tree.selection()
        if not sel:
            return
        t = self.tasks[int(sel[0])]
        if t.dest and os.path.isdir(t.dest):
            os.startfile(t.dest)

    def start(self):
        if self.worker:
            return
        pending = [t for t in self.tasks if t.error is None and t.status != "完成"]
        if not pending:
            messagebox.showinfo(APP_TITLE, "没有待处理的镜像")
            return
        self.cancel_flag.clear()
        self.btn_go.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.btn_clear.configure(state="disabled")
        dest_mode = self.var_dest_mode.get()
        custom = self.var_custom.get().strip()
        policy = self._policy_map.get(self.var_policy.get(), "auto")
        symlinks = self._symlink_map.get(self.var_symlinks.get(), "native")
        link_manifest = bool(self.var_linklist.get())
        self.worker = threading.Thread(target=self._work,
                                       args=(pending, dest_mode, custom, policy, symlinks, link_manifest))
        self.worker.daemon = True
        self.worker.start()

    # ------------------------------------------------------------- 后台
    def _work(self, tasks, dest_mode, custom, policy, symlinks="native", link_manifest=False):
        q = self.queue
        cur = None
        try:
            for i, t in enumerate(tasks):
                cur = t
                if self.cancel_flag.is_set():
                    q.put(("row", t, "已取消", "", "err"))
                    cur = None
                    continue
                q.put(("row", t, "解压中…", "", "run"))
                q.put(("log", "[%d/%d] %s" % (i + 1, len(tasks), t.path)))

                def on_log(line):
                    q.put(("log", "    " + line))

                q.put(("status", "正在解析 %s …" % os.path.basename(t.path)))
                info = core.sniff(t.path)
                q.put(("log", "    类型：%s" % info.label))
                if info.kind not in ("erofs", "android-sparse"):
                    raise core.ExtractError("不支持的格式：%s" % info.label)

                total_inodes = 0
                m = re.search(r"(\d+)", str(info.extra.get("filesystem_inode_count", "")))
                if m:
                    total_inodes = int(m.group(1))
                hint = ("已解压 0 个条目 / 共 %d" % total_inodes) if total_inodes else "解压中…"
                q.put(("progress", 0.0, hint))

                dest = None
                if dest_mode == "custom" and custom:
                    dest = os.path.join(custom, os.path.splitext(os.path.basename(t.path))[0])

                def on_progress(files, size, elapsed, _total=total_inodes):
                    if _total:
                        pct = min(99.0, files * 100.0 / _total)
                    else:
                        pct = min(95.0, elapsed * 3.0)
                    q.put(("progress", pct, "已解压 %d 个条目 · %s · %.1fs"
                           % (files, core.human_size(size), elapsed)))

                res = core.extract_image(t.path, dest=dest, policy=policy,
                                         on_log=on_log, on_progress=on_progress,
                                         cancel=self.cancel_flag.is_set,
                                         symlinks=symlinks, link_manifest=link_manifest)
                t.dest = res.dest
                q.put(("row", t, "完成", res.dest, "ok"))
                q.put(("log", "    " + res.summary()))
                q.put(("progress", 100.0, res.summary()))
                cur = None
                if self.var_open_after.get():
                    try:
                        os.startfile(res.dest)
                    except Exception:
                        pass
        except core.ExtractError as e:
            q.put(("log", "[错误] %s" % e))
            q.put(("err_task", (cur, str(e))))
        except Exception:
            q.put(("log", "[异常]\n" + traceback.format_exc()))
            q.put(("err_task", (cur, "内部错误，详见日志")))
        finally:
            q.put(("done", None))

    # ------------------------------------------------------------- UI 泵
    def _pump(self):
        # 先处理拖放进来的文件（窗口过程只入队，这里在主线程安全处理）
        if self.drop_target:
            for paths in self.drop_target.take_pending():
                try:
                    self.add_paths(paths)
                    if self.var_auto_start.get() and not self.worker:
                        self.start()          # 拖进来就解压
                except Exception:
                    self._log("[拖放处理失败]\n" + traceback.format_exc())
        try:
            while True:
                item = self.queue.get_nowait()
                kind = item[0]
                if kind == "log":
                    self._log(item[1])
                elif kind == "row":
                    _, t, status, dest, tag = item
                    t.status = status
                    iid = str(self.tasks.index(t))
                    if self.tree.exists(iid):
                        self.tree.item(iid, values=(os.path.basename(t.path), status, dest), tags=(tag,))
                elif kind == "progress":
                    self.var_progress.set(item[1])
                    self.status.config(text=item[2])
                elif kind == "status":
                    self.status.config(text=item[1])
                elif kind == "err_task":
                    t, msg = item[1]
                    if t is None:
                        for cand in self.tasks:
                            if cand.status == "解压中…":
                                t = cand
                                break
                    if t is not None:
                        t.status = "失败"
                        t.error = msg
                        iid = str(self.tasks.index(t))
                        if self.tree.exists(iid):
                            self.tree.item(iid, values=(os.path.basename(t.path), "失败", t.dest),
                                           tags=("err",))
                elif kind == "done":
                    self.worker = None
                    self.btn_go.configure(state="normal")
                    self.btn_cancel.configure(state="disabled")
                    self.btn_clear.configure(state="normal")
                    ok = sum(1 for t in self.tasks if t.status == "完成")
                    bad = sum(1 for t in self.tasks if t.status == "失败")
                    self.status.config(text="本次完成 %d 个，失败 %d 个" % (ok, bad))
                    if bad:
                        self.var_progress.set(0)
        except queue.Empty:
            pass
        self.root.after(80, self._pump)

    def _log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", time.strftime("[%H:%M:%S] ") + str(text) + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _on_close(self):
        if self.worker:
            if not messagebox.askyesno(APP_TITLE, "正在解压，确定要退出吗？"):
                return
            self.cancel_flag.set()
        if self.drop_target:
            self.drop_target.close()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = App(root)
    root.bind("<Return>", lambda e: app.start())
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
