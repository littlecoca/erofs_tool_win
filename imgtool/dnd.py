# -*- coding: utf-8 -*-
# SPDX-License-Identifier: 0BSD
"""给 tkinter 窗口加上 Windows 原生"拖文件进来"支持（纯 ctypes，无第三方依赖）。

原理：Shell 的 DragAcceptFiles + 子类化窗口过程，拦截 WM_DROPFILES 消息。
不依赖 tkinterdnd2 / windnd 之类的第三方包，也不需要管理员权限。
"""

import ctypes
import sys
import traceback
from ctypes import wintypes

WM_DROPFILES = 0x0233
WM_COPYGLOBALDATA = 0x0049
GWLP_WNDPROC = -4
GA_ROOT = 2
MSGFLT_ALLOW = 1

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_shell32 = ctypes.WinDLL("shell32", use_last_error=True)

_IS64 = ctypes.sizeof(ctypes.c_void_p) == 8
_LRESULT = ctypes.c_longlong if _IS64 else ctypes.c_long
_WNDPROC = ctypes.WINFUNCTYPE(_LRESULT, wintypes.HWND, ctypes.c_uint,
                              wintypes.WPARAM, wintypes.LPARAM)

_user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
_user32.GetAncestor.restype = wintypes.HWND
_shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
_shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT,
                                    wintypes.LPWSTR, wintypes.UINT]
_shell32.DragQueryFileW.restype = wintypes.UINT
_shell32.DragFinish.argtypes = [wintypes.HANDLE]

if _IS64:
    _set_long = _user32.SetWindowLongPtrW
    _call_proc = _user32.CallWindowProcW
else:
    _set_long = _user32.SetWindowLongW

_set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
_set_long.restype = ctypes.c_void_p
_call_proc.argtypes = [ctypes.c_void_p, wintypes.HWND, ctypes.c_uint,
                       wintypes.WPARAM, wintypes.LPARAM]
_call_proc.restype = _LRESULT


class DropTarget(object):
    """把 tkinter 窗口变成可接收文件拖放的目标。

    用法一（推荐，最稳）：回调里只入队，主线程用 after 轮询取走
        dt = DropTarget(root)
        # 在 after 轮询里: for paths in dt.take_pending(): ...
    用法二：给回调，回调里**不要**做重活（不要操作 Tk 控件、不要扫描文件系统），
    Windows 的窗口过程里做这些容易让 Tcl/CPython 重入出问题。
        dt = DropTarget(root, lambda paths: print(paths))   # 记得保留引用
    """

    def __init__(self, widget, on_drop=None, on_error=None):
        self.widget = widget
        self.on_drop = on_drop
        self.on_error = on_error
        self.available = False
        self.hwnd = None
        self._proc = None
        self._old_proc = None
        self._pending = []          # 只由窗口过程追加，主线程取走
        try:
            self._install()
            self.available = True
        except Exception as e:                      # pragma: no cover
            if on_error:
                on_error(e)

    def take_pending(self):
        """主线程调用：取走待处理的拖放路径（列表的列表）。"""
        pending, self._pending = self._pending, []
        return pending

    # ------------------------------------------------------------ 内部
    def _install(self):
        self.widget.update_idletasks()
        hwnd = wintypes.HWND(self.widget.winfo_id())
        root = _user32.GetAncestor(hwnd, GA_ROOT)
        if root:
            hwnd = root
        self.hwnd = hwnd

        # 允许在更高完整性级别（例如管理员运行）下也能收到拖放消息
        try:
            for msg in (WM_DROPFILES, WM_COPYGLOBALDATA):
                _user32.ChangeWindowMessageFilterEx(hwnd, msg, MSGFLT_ALLOW, None)
        except Exception:
            pass

        _shell32.DragAcceptFiles(hwnd, True)

        def _wndproc(hwnd_, msg, wparam, lparam):
            if msg == WM_DROPFILES:
                paths = []
                try:
                    paths = self._read_drop(wparam)
                except Exception:
                    if self.on_error:
                        try:
                            self.on_error(traceback.format_exc())
                        except Exception:
                            pass
                finally:
                    try:
                        _shell32.DragFinish(wparam)   # 尽快释放，别拖着重活
                    except Exception:
                        pass
                if paths:
                    self._pending.append(paths)       # 回调里只做这一件事
                    if self.on_drop:
                        try:
                            self.on_drop(paths)
                        except Exception:
                            if self.on_error:
                                self.on_error(traceback.format_exc())
                return 0
            return _call_proc(self._old_proc, hwnd_, msg, wparam, lparam)

        self._proc = _WNDPROC(_wndproc)             # 必须留引用，否则被 GC
        self._old_proc = _set_long(hwnd, GWLP_WNDPROC,
                                   ctypes.cast(self._proc, ctypes.c_void_p))

    @staticmethod
    def _read_drop(hdrop):
        count = _shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
        paths = []
        for i in range(count):
            need = _shell32.DragQueryFileW(hdrop, i, None, 0)
            buf = ctypes.create_unicode_buffer(need + 2)
            _shell32.DragQueryFileW(hdrop, i, buf, need + 1)
            if buf.value:
                paths.append(buf.value)
        return paths

    def close(self):
        if self.hwnd:
            try:
                _shell32.DragAcceptFiles(self.hwnd, False)
            except Exception:
                pass
            if self._old_proc:
                try:
                    _set_long(self.hwnd, GWLP_WNDPROC, self._old_proc)
                except Exception:
                    pass
        self.hwnd = None


def post_drop(hwnd, paths):
    """测试用：构造 WM_DROPFILES 消息发给窗口，模拟一次拖放。"""
    import struct

    DROPFILES_FMT = "<IiiII"
    names = b"".join(p.encode("utf-16-le") + b"\0\0" for p in paths) + b"\0\0"
    header = struct.pack(DROPFILES_FMT, 20, 0, 0, 0, 1)   # pFiles=20, fWide=1
    blob = header + names
    GMEM_MOVEABLE = 0x0002
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    _kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    _kernel32.GlobalLock.restype = ctypes.c_void_p
    _kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    _kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    _user32.PostMessageW.argtypes = [wintypes.HWND, ctypes.c_uint,
                                     wintypes.WPARAM, wintypes.LPARAM]
    _user32.PostMessageW.restype = wintypes.BOOL

    h = _kernel32.GlobalAlloc(GMEM_MOVEABLE, len(blob))
    if not h:
        raise OSError("GlobalAlloc failed")
    ptr = _kernel32.GlobalLock(h)
    if not ptr:
        raise OSError("GlobalLock failed")
    ctypes.memmove(ptr, blob, len(blob))
    _kernel32.GlobalUnlock(h)
    if not _user32.PostMessageW(wintypes.HWND(hwnd), WM_DROPFILES, wintypes.WPARAM(h), 0):
        raise OSError("PostMessage failed: %d" % ctypes.get_last_error())
    return True
