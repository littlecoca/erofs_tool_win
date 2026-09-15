# -*- coding: utf-8 -*-
# SPDX-License-Identifier: 0BSD
"""imgtool 核心：镜像识别 + 调用 erofs-utils（Cygwin 构建）解压。

设计要点
--------
* 引擎是官方 erofs-utils 的 Windows(Cygwin) 构建，命令行参数与 Linux 版一致：
  ``fsck.erofs --extract=<目录> [--overwrite] [--offset=N] <镜像>``
* 给引擎传路径时统一转成 "D:/a/b" 这种正斜杠 Windows 路径，Cygwin 认得，
  同时避免了反斜杠被当成转义。
* 不依赖 WSL / 管理员权限 / 任何第三方安装。
"""

import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time

from . import sparse

# ---------------------------------------------------------------- 常量

EROFS_MAGIC = 0xE0F5E1E2
EROFS_SUPER_OFFSET = 1024          # EROFS 超级块固定在偏移 1024
IMAGE_EXTS = (".img", ".image", ".bin", ".erofs", ".raw")

# 常见镜像特征，用于给出人话提示
_MAGICS = (
    (b"\x53\xef", 0x438, "ext2/ext3/ext4", "ext4 镜像（不是 EROFS）"),
    (b"\x10\x20\xf5\xf2", 0x400, "f2fs", "f2fs 镜像（不是 EROFS）"),
    (b"hsqs", 0, "squashfs", "squashfs 镜像（不是 EROFS）"),
    (b"\x45\x3d\xcd\x28", 0, "cramfs", "cramfs 镜像（不是 EROFS）"),
    (b"ANDROID!", 0, "android-boot", "Android boot/recovery 镜像"),
    (b"\x1f\x8b", 0, "gzip", "gzip 压缩包"),
    (b"\xfd7zXZ", 0, "xz", "xz 压缩包"),
    (b"PK\x03\x04", 0, "zip", "zip 压缩包"),
    (b"BZh", 0, "bzip2", "bzip2 压缩包"),
)


class ExtractError(RuntimeError):
    """解压失败，message 已经是可以直接给用户看的中文提示。"""


# Cygwin 在 winsymlinks:sys 模式下把符号链接写成的小文件：
#   "!<symlink>" + UTF-16LE BOM + 目标路径(UTF-16LE) + NUL
CYGWIN_SYMLINK_MAGIC = b"!<symlink>"
SYMLINK_MODES = ("native", "copy", "keep")
SYMLINK_MANIFEST = "_imgtool_symlinks.txt"


class ImageInfo(object):
    def __init__(self, path, kind, offset=0, label="", raw_size=0, extra=None):
        self.path = path
        self.kind = kind            # erofs / android-sparse / ext4 / ...
        self.offset = offset        # EROFS 超级块所在偏移（>0 时需 --offset）
        self.label = label
        self.raw_size = raw_size
        self.extra = extra or {}
        self.inode_count = 0        # 解压进度估算用

    def __repr__(self):
        return "<ImageInfo %s kind=%s offset=%d>" % (os.path.basename(self.path), self.kind, self.offset)


# ---------------------------------------------------------------- 引擎定位

def engine_dir():
    """引擎目录：环境变量 IMGTOOL_ENGINE 优先，否则用包旁边的 engine/。"""
    env = os.environ.get("IMGTOOL_ENGINE")
    if env and os.path.isdir(env):
        return os.path.abspath(env)
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(os.path.dirname(here), "engine"),
                 os.path.join(here, "engine")):
        if os.path.isdir(cand):
            return cand
    raise ExtractError("找不到 engine 目录（fsck.erofs.exe）。请确认 engine\\ 与 imgtool\\ 在同一层，"
                       "或设置环境变量 IMGTOOL_ENGINE 指向它。")


def tool_path(name):
    p = os.path.join(engine_dir(), name + ".exe")
    if not os.path.isfile(p):
        raise ExtractError("缺少引擎文件：%s" % p)
    return p


def engine_version():
    try:
        p = subprocess.run([tool_path("fsck.erofs"), "-V"], capture_output=True, timeout=30)
        text = p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")
        m = re.search(r"fsck\.erofs\s+([\w.\-+]+)", text)
        if m:
            return m.group(1)
        m = re.search(r"(\d+\.\d+\.\d+[\w.\-+]*)", text)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "unknown"


def _cyg(path):
    """Windows 路径 -> Cygwin 友好的正斜杠路径。"""
    return os.path.abspath(path).replace("\\", "/")


# ---------------------------------------------------------------- 镜像识别

def _read_head(path, n=8192):
    with open(path, "rb") as f:
        return f.read(n)


def _find_erofs_offset(path, scan_limit=64 << 20):
    """在前 scan_limit 字节里找 EROFS 超级块位置（magic 位于偏移 1024 处）。

    返回超级块偏移（0 表示紧跟文件开头），找不到返回 None。
    """
    needle = struct.pack("<I", EROFS_MAGIC)
    size = os.path.getsize(path)
    limit = min(size, scan_limit)
    pos = 0
    first_candidate = None
    with open(path, "rb") as f:
        while pos < limit:
            chunk = f.read(min(4 << 20, limit - pos))
            if not chunk:
                break
            start = 0
            while True:
                i = chunk.find(needle, start)
                if i < 0:
                    break
                abs_off = pos + i - EROFS_SUPER_OFFSET
                if abs_off >= 0 and abs_off % 512 == 0:
                    if first_candidate is None:
                        first_candidate = abs_off
                    if _looks_like_erofs_sb(path, abs_off):
                        return abs_off
                start = i + 1
            pos += len(chunk)
    # 超级块校验没过，但确实扫到了 magic：还是交给 fsck.erofs 去判定
    return first_candidate


def _looks_like_erofs_sb(path, offset):
    """粗略校验超级块：块大小是 2 的幂且 >= 1024，根 nid 合理。

    struct erofs_super_block 前 16 字节：
        __le32 magic; __le32 checksum; __le32 feature_compat;
        __u8 blkszbits; __u8 sb_extslots; __le16 root_nid;
    """
    try:
        with open(path, "rb") as f:
            f.seek(offset + EROFS_SUPER_OFFSET)
            sb = f.read(32)
    except Exception:
        return False
    if len(sb) < 16:
        return False
    magic, _checksum, _feature_compat, blkszbits, _extslots, root_nid = \
        struct.unpack("<IIIBBH", sb[:16])
    if magic != EROFS_MAGIC:
        return False
    blk = 1 << blkszbits
    return 1024 <= blk <= (1 << 20) and 0 < root_nid < (1 << 24)


def sniff(path):
    """识别镜像类型。"""
    if not os.path.isfile(path):
        raise ExtractError("文件不存在：%s" % path)
    size = os.path.getsize(path)
    if size == 0:
        raise ExtractError("文件是空的：%s" % path)

    if sparse.is_sparse(path):
        try:
            blk, total, chunks, raw = sparse.read_header(path)
            extra = {"blk_sz": blk, "total_blks": total, "chunks": chunks}
        except Exception as e:
            raise ExtractError("Android sparse 头部损坏：%s" % e)
        return ImageInfo(path, "android-sparse", raw_size=raw, extra=extra,
                         label="Android sparse image（展开后 %.1f MB）" % (raw / 1048576.0))

    off = _find_erofs_offset(path)
    if off is not None:
        info = ImageInfo(path, "erofs", offset=off)
        info.extra = image_info(path, offset=off)
        m = re.search(r"(\d+)", str(info.extra.get("filesystem_inode_count", "")))
        if m:
            info.inode_count = int(m.group(1))
        info.label = _erofs_label(info.extra)
        return info

    head = _read_head(path, 0x1000)
    for magic, at, kind, label in _MAGICS:
        if len(head) >= at + len(magic) and head[at:at + len(magic)] == magic:
            return ImageInfo(path, kind, label=label)

    if _looks_like_android_super(path):
        return ImageInfo(path, "android-super",
                         label="Android 动态分区 super.img（内含多个子分区，本工具暂不处理）")

    return ImageInfo(path, "unknown", label="无法识别的镜像格式")


def _looks_like_android_super(path):
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
        return head[:4] == b"\x30\x50\x4c\x41" or b"LP_METADATA" in head[:2048]
    except Exception:
        return False


def _erofs_label(d):
    if not d:
        return "EROFS 镜像"
    parts = []
    if d.get("blocksize"):
        parts.append("块大小 %d" % d["blocksize"])
    if d.get("inode_count"):
        parts.append("%d 个 inode" % d["inode_count"])
    if d.get("uuid"):
        parts.append("UUID %s" % d["uuid"])
    return "EROFS 镜像" + ("（%s）" % "，".join(parts) if parts else "")


# ---------------------------------------------------------------- 引擎调用

def image_info(path, offset=0):
    """用 dump.erofs -s 取超级块信息，返回 dict（失败返回空 dict）。"""
    args = []
    if offset:
        args.append("--offset=%d" % offset)
    args.append(_cyg(path))
    try:
        p = subprocess.run([tool_path("dump.erofs"), "-s"] + args,
                           capture_output=True, timeout=120)
    except Exception:
        return {}
    text = p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")
    out = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        key = k.strip().lower().replace(" ", "_")
        out[key] = v.strip()
    out["_raw"] = text.strip()
    return out


class _Runner(object):
    """跑引擎进程，同时把输出转给回调、支持取消、支持外部轮询进度。"""

    def __init__(self, argv, on_log=None, cancel=None):
        self.argv = argv
        self.on_log = on_log
        self.cancel = cancel
        self.proc = None
        self.lines = []
        self._cancelled = False
        self._lock = threading.Lock()

    def _reader(self, pipe):
        for raw in iter(pipe.readline, b""):
            text = raw.decode("utf-8", "replace").rstrip("\r\n")
            with self._lock:
                self.lines.append(text)
            if self.on_log:
                self.on_log(text)
        try:
            pipe.close()
        except Exception:
            pass

    def run(self, on_tick=None, tick=0.05):
        env = os.environ.copy()
        env["PATH"] = engine_dir() + os.pathsep + env.get("PATH", "")
        env.setdefault("LC_ALL", "C.UTF-8")     # 保证中文文件名按 UTF-8 走
        env.setdefault("LANG", "C.UTF-8")
        # 关键：不加这个的话，Cygwin 会把符号链接写成 Windows 打不开的
        # 0 字节重解析点；设成 sys 后写成 "!<symlink>目标" 的普通文件，
        # 我们就能读出来再还原成 Windows 符号链接 / 目录联接。
        env["CYGWIN"] = "winsymlinks:sys"
        creationflags = 0
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = subprocess.CREATE_NO_WINDOW
        self.proc = subprocess.Popen(
            self.argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=engine_dir(), env=env, creationflags=creationflags)
        th = threading.Thread(target=self._reader, args=(self.proc.stdout,))
        th.daemon = True
        th.start()

        t0 = time.time()
        while True:
            rc = self.proc.poll()
            if rc is not None:
                break
            if self.cancel and self.cancel():
                self._cancelled = True
                try:
                    self.proc.kill()
                except Exception:
                    pass
                self.proc.wait()
                break
            if on_tick:
                on_tick(time.time() - t0)
            time.sleep(tick)
        th.join(timeout=5)
        return self.proc.returncode, "\n".join(self.lines), time.time() - t0, self._cancelled


# ---------------------------------------------------------------- 目录删除

FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def is_reparse_point(path):
    """是不是符号链接/目录联接等重解析点（Windows 上 os.path.islink 认不出联接）。"""
    try:
        return bool(os.lstat(path).st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT)
    except (OSError, AttributeError):
        return False


def _force_remove(path):
    """删掉单个条目（文件 / 符号链接 / 目录联接），必要时清掉只读属性。"""
    for _ in range(2):
        try:
            try:
                os.remove(path)
            except OSError:
                os.rmdir(path)      # 目录联接、指向目录的符号链接走这里
            return True
        except OSError:
            try:
                os.chmod(path, 0o700)
            except OSError:
                pass
    return False


def safe_rmtree(path):
    """安全删除目录树。

    与 shutil.rmtree 的区别：碰到重解析点（符号链接 / 目录联接）只删除链接本身，
    绝不跟进链接目标去删别人的文件 —— Python 3.8 的 rmtree 会跟进去，很危险。
    """
    path = os.path.abspath(path)
    if not os.path.lexists(path):
        return True
    if is_reparse_point(path) or os.path.isfile(path):
        return _force_remove(path)
    try:
        entries = list(os.scandir(path))
    except OSError:
        return _force_remove(path)
    for entry in entries:
        try:
            is_dir = entry.is_dir(follow_symlinks=False) and not is_reparse_point(entry.path)
        except OSError:
            is_dir = False
        if is_dir:
            safe_rmtree(entry.path)
        else:
            _force_remove(entry.path)
    try:
        os.rmdir(path)
        return True
    except OSError:
        return _force_remove(path)


# ---------------------------------------------------------------- 解压

def default_dest(image_path):
    """默认输出目录：镜像同目录下、与镜像同名的文件夹。"""
    d = os.path.dirname(os.path.abspath(image_path))
    stem = os.path.splitext(os.path.basename(image_path))[0]
    if not stem:
        stem = "extracted"
    return os.path.join(d, stem)


def resolve_dest(image_path, dest=None, policy="auto"):
    """按冲突策略算出真正可用的输出目录。

    policy:
        auto      —— 目录已存在就加序号（默认，最安全）
        overwrite —— 用原目录（调用方会先删掉重建）
    """
    dest = dest or default_dest(image_path)
    dest = os.path.abspath(dest)
    if policy == "overwrite" or not os.path.exists(dest):
        return dest
    n = 2
    while True:
        cand = "%s (%d)" % (dest, n)
        if not os.path.exists(cand):
            return cand
        n += 1


def _dir_stats(path):
    """统计目录里的文件数与总字节数；不跟进符号链接/目录联接，避免重复计数。"""
    files = 0
    size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [d for d in dirnames
                           if not is_reparse_point(os.path.join(dirpath, d))]
            for fn in filenames:
                fp = os.path.join(dirpath, fn)
                files += 1
                try:
                    st = os.lstat(fp)
                    if not (st.st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT):
                        size += st.st_size
                except (OSError, AttributeError):
                    pass
    except Exception:
        pass
    return files, size


class ExtractResult(object):
    def __init__(self, dest, kind, files, size, seconds, converted_from=None, offset=0,
                 links=None):
        self.dest = dest
        self.kind = kind
        self.files = files
        self.size = size
        self.seconds = seconds
        self.converted_from = converted_from    # sparse 转换用的临时 raw 路径
        self.offset = offset
        self.links = links or {}                # 符号链接后处理统计

    def summary(self):
        text = "解压完成：%d 个文件，%.1f MB，用时 %.1f 秒 -> %s" % (
            self.files, self.size / 1048576.0, self.seconds, self.dest)
        lk = self.links
        if lk and lk.get("total"):
            text += "；符号链接 %d 条" % lk["total"]
            if lk.get("symlink") or lk.get("junction") or lk.get("copy"):
                text += "（还原 %d / 目录联接 %d / 复制 %d）" % (
                    lk.get("symlink", 0), lk.get("junction", 0), lk.get("copy", 0))
            if lk.get("kept"):
                text += "，还有 %d 条保留了链接目标文件" % lk["kept"]
        return text


def extract_image(image_path, dest=None, policy="auto", overwrite=None, offset=None,
                  on_log=None, on_progress=None, cancel=None, keep_temp=False,
                  verbose=2, extra_args=None, symlinks="native", link_manifest=False):
    """把 IMG 解压到目录。

    参数
    ----
    dest      输出目录，默认 = 镜像同目录下的同名文件夹
    policy    auto=目录已存在就自动加序号（默认）；overwrite=先删掉旧目录再解压
    symlinks  符号链接处理方式：
              native=尽量还原成 Windows 符号链接（目录用联接兜底）(默认)
              copy  =还原不了就复制目标内容
              keep  =不处理，保留 Cygwin 的链接目标文件
    on_progress(files, bytes, elapsed) 约 20 次/秒回调，用于界面显示进度。
    cancel()  返回 True 时中断解压。
    """
    image_path = os.path.abspath(image_path)
    info = sniff(image_path)
    if info.kind not in ("erofs", "android-sparse"):
        raise ExtractError("%s：%s。本项目基于 fsck.erofs，只支持 EROFS 镜像"
                           "（含 Android sparse 包装的 EROFS）。" % (os.path.basename(image_path), info.label))

    dest_dir = resolve_dest(image_path, dest, policy)
    if policy == "overwrite" and os.path.isdir(dest_dir):
        if on_log:
            on_log("[imgtool] 覆盖模式：先删除已存在的目录 %s" % dest_dir)
        safe_rmtree(dest_dir)
    if not os.path.isdir(dest_dir):
        os.makedirs(dest_dir)

    src = image_path
    tmp_raw = None
    offset = info.offset if offset is None else offset
    converted = None

    try:
        if info.kind == "android-sparse":
            raw_total = info.raw_size
            if on_log:
                on_log("[imgtool] 检测到 Android sparse image，先展开成 raw（约 %.1f MB），"
                       "这一步需要同盘临时空间…" % (raw_total / 1048576.0))
            fd, tmp_raw = tempfile.mkstemp(prefix=os.path.basename(image_path) + ".",
                                           suffix=".rawtmp", dir=os.path.dirname(image_path))
            os.close(fd)

            def _sp(done, total):
                if on_progress:
                    on_progress(0, int(raw_total * done / float(total or 1)), 0.0)

            sparse.to_raw(image_path, tmp_raw, on_progress=_sp, cancel=cancel)
            src = tmp_raw
            converted = tmp_raw
            offset = 0
            if on_log:
                on_log("[imgtool] sparse 展开完成：%s" % tmp_raw)

        args = ["--extract=%s" % _cyg(dest_dir)]
        if offset:
            args.append("--offset=%d" % offset)
        if verbose:
            args.append("-d%d" % verbose)
        if extra_args:
            args.extend(extra_args)
        args.append(_cyg(src))

        argv = [tool_path("fsck.erofs")] + args
        if on_log:
            on_log("[imgtool] %s" % " ".join(argv))

        runner = _Runner(argv, on_log=on_log, cancel=cancel)
        t0 = time.time()

        def tick(elapsed):
            if on_progress:
                f, s = _dir_stats(dest_dir)
                on_progress(f, s, elapsed)

        rc, out, elapsed, cancelled = runner.run(on_tick=tick)

        if cancelled:
            raise ExtractError("已取消（已解压的内容保留在 %s）" % dest_dir)
        if rc != 0:
            raise ExtractError(_explain_failure(rc, out, info, argv))

        # 符号链接后处理：Windows 上还原成能用的链接
        links = fix_symlinks(dest_dir, mode=symlinks, on_log=on_log, cancel=cancel,
                             write_manifest=link_manifest)

        files, size = _dir_stats(dest_dir)
        if on_progress:
            on_progress(files, size, time.time() - t0)
        return ExtractResult(dest_dir, info.kind, files, size, time.time() - t0,
                             converted_from=converted, offset=offset, links=links)
    finally:
        if tmp_raw and not keep_temp:
            try:
                os.remove(tmp_raw)
            except OSError:
                pass


def _explain_failure(rc, out, info, argv=None):
    low = out.lower()
    tail = "\n命令：%s" % " ".join(argv) if argv else ""
    if not out.strip():
        # 引擎一句话都没说就退出（极少见），把命令行一起带上，便于事后排查
        return ("解压失败：fsck.erofs 返回 %d 且没有任何输出"
                "（可能被安全软件拦截，或进程启动异常）%s" % (rc, tail))
    if "magic" in low or "not an erofs" in low or "failed to read superblock" in low:
        return "不是有效的 EROFS 镜像（引擎返回 %d）：%s" % (rc, out.strip()[:300])
    if "no space left" in low or "not enough space" in low:
        return "磁盘空间不足：%s" % out.strip()[:300]
    if "permission denied" in low:
        return "没有权限写入目标目录：%s" % out.strip()[:300]
    if "(file exists)" in low:
        return ("目标目录里已有同名文件（fsck.erofs 的 --overwrite 不处理硬链接）。"
                "请用「覆盖」策略重建目录，或换个输出目录：%s" % out.strip()[:200])
    return "解压失败（fsck.erofs 返回 %d）：%s%s" % (rc, out.strip()[:400], tail)


# ---------------------------------------------------------------- 符号链接还原

def read_cygwin_symlink(path):
    """识别 Cygwin 的符号链接文件，返回目标字符串；不是链接则返回 None。

    格式："!<symlink>" + UTF-16LE BOM + 目标(UTF-16LE) + NUL
    """
    try:
        if os.path.getsize(path) > 8192:
            return None
        with open(path, "rb") as f:
            data = f.read(8192)
    except OSError:
        return None
    if not data.startswith(CYGWIN_SYMLINK_MAGIC):
        return None
    rest = data[len(CYGWIN_SYMLINK_MAGIC):]
    if rest.startswith(b"\xff\xfe"):
        body = rest[2:]
        try:
            text = body.decode("utf-16-le", "replace")
        except Exception:
            return None
    else:
        try:
            text = rest.decode("utf-8", "replace")
        except Exception:
            return None
    return text.split("\0")[0]


def _resolve_target(root, link_path, target):
    """把链接目标换算成 Windows 绝对路径（用于判断是不是目录 / 做联接）。

    镜像里的 "/system/bin/sh" 这种绝对路径，对应解压目录下的 system/bin/sh。
    """
    if target.startswith("/"):
        rel = target.lstrip("/").replace("/", os.sep)
        return os.path.join(root, rel)
    base = os.path.dirname(link_path)
    return os.path.normpath(os.path.join(base, target.replace("/", os.sep)))


def _make_junction(link_path, target_abs):
    """用 mklink /J 造目录联接（普通用户权限即可，不需要开发者模式）。"""
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        p = subprocess.run(["cmd", "/c", "mklink", "/J", link_path, target_abs],
                           capture_output=True, creationflags=creationflags, timeout=60)
        return p.returncode == 0 and os.path.isdir(link_path)
    except Exception:
        return False


def fix_symlinks(root, mode="native", on_log=None, cancel=None, write_manifest=False):
    """把 Cygwin 写出的 "!<symlink>" 文件尽量还原成 Windows 能用的东西。

    mode:
        native —— 先试真正的符号链接（需要开发者模式/管理员），
                  不行的话目录用联接（免权限），再不行保留链接目标文件
        copy   —— 同 native，最后一步改成复制目标内容
        keep   —— 不动，保留链接目标文件
    write_manifest: 为 True 时无论成败都写一份链接清单到输出目录。
    """
    stats = {"total": 0, "symlink": 0, "junction": 0, "copy": 0, "kept": 0, "broken": 0}
    if mode not in SYMLINK_MODES:
        mode = "native"

    records = []
    for dirpath, _dirnames, filenames in os.walk(root):
        if cancel and cancel():
            break
        for fn in filenames:
            path = os.path.join(dirpath, fn)
            if fn == SYMLINK_MANIFEST:
                continue
            target = read_cygwin_symlink(path)
            if target is None:
                continue
            stats["total"] += 1
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            if mode == "keep":
                records.append((rel, target, "未处理"))
                stats["kept"] += 1
                continue
            action = _restore_one(root, path, target, mode, stats)
            records.append((rel, target, action))

    if records and (write_manifest or stats["kept"]):
        manifest = os.path.join(root, SYMLINK_MANIFEST)
        try:
            with open(manifest, "w", encoding="utf-8") as f:
                f.write("# imgtool 符号链接清单（源自 EROFS 镜像）\n")
                f.write("# 格式：链接路径 -> 目标路径    [处理方式]\n")
                for rel, target, action in records:
                    f.write("%s -> %s    [%s]\n" % (rel, target, action))
            if on_log:
                on_log("[imgtool] 符号链接清单：%s" % manifest)
        except OSError:
            pass

    if on_log and stats["total"]:
        on_log("[imgtool] 符号链接：共 %d 条 — 还原成链接 %d、目录联接 %d、复制内容 %d、保留目标文件 %d"
               % (stats["total"], stats["symlink"], stats["junction"],
                  stats["copy"], stats["kept"]))
        if stats["kept"]:
            on_log("[imgtool] 提示：想拿到真正的符号链接，请开启 Windows「开发者模式」后重新解压")
    return stats


def _restore_one(root, path, target, mode, stats):
    """处理单条链接，返回处理方式的说明文字。"""
    with open(path, "rb") as f:
        raw = f.read()
    resolved = _resolve_target(root, path, target)

    # 1) 真正的 Windows 符号链接（开发者模式或管理员权限下可用）
    try:
        os.remove(path)
        os.symlink(target, path)
        stats["symlink"] += 1
        return "已还原为符号链接"
    except OSError:
        pass

    # 2) 目标是目录 -> 目录联接（普通权限即可）
    if os.path.isdir(resolved):
        try:
            if os.path.exists(path):
                os.remove(path)
            if _make_junction(path, resolved):
                stats["junction"] += 1
                return "目录联接"
        except OSError:
            pass

    # 3) 复制目标内容 / 保留链接目标文件
    if mode == "copy" and os.path.isfile(resolved):
        try:
            if os.path.exists(path):
                os.remove(path)
            shutil.copyfile(resolved, path)
            stats["copy"] += 1
            return "已复制目标内容"
        except OSError:
            pass

    try:
        with open(path, "wb") as f:      # 原样写回链接目标文件，避免丢信息
            f.write(raw)
    except OSError:
        pass
    return "保留链接目标文件（无权限）"


# ---------------------------------------------------------------- 小工具

def extract_to_same_name(image_path, **kw):
    """拖拽场景的最简入口：解压到镜像同目录的同名文件夹。"""
    return extract_image(image_path, dest=None, **kw)


def is_image_file(path):
    return os.path.isfile(path) and path.lower().endswith(IMAGE_EXTS)


def human_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return "%.1f %s" % (n, unit) if unit != "B" else "%d B" % n
        n /= 1024.0


def free_space(path):
    try:
        return shutil.disk_usage(path).free
    except Exception:
        return -1
