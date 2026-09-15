# -*- coding: utf-8 -*-
# SPDX-License-Identifier: 0BSD
"""端到端测试：自造 EROFS 镜像 -> 用 imgtool 解压 -> 逐文件比对。

跑法（引擎是 Cygwin 程序，在 DSH 沙箱里需要放宽权限）：
    python tests/e2e_test.py [--quick]

覆盖：
  1. 各种压缩算法/布局（plain/lz4/lz4hc/lzma/zstd/deflate/chunk/fragments/dedupe/...）
  2. 默认输出目录 = 镜像同目录下的同名文件夹（核心需求）
  3. 输出目录已存在时的三种策略
  4. Android sparse 镜像自动展开
  5. EROFS 在非 0 偏移处（--offset 自动识别）
  6. 中文/空格路径（镜像路径与输出路径都带中文）
  7. 错误处理（垃圾文件、空文件、不存在、ext4/f2fs 镜像）
  8. 取消正在进行的解压
"""

import argparse
import hashlib
import io
import os
import shutil
import struct
import subprocess
import sys
import tarfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from imgtool import core, sparse                      # noqa: E402
from tests import make_fixtures                       # noqa: E402

OUT = os.path.join(ROOT, "test", "e2e")
PASS, FAIL = [], []


def ok(name, detail=""):
    PASS.append(name)
    print("  [PASS] %-46s %s" % (name, detail))


def bad(name, detail=""):
    FAIL.append((name, detail))
    print("  [FAIL] %-46s %s" % (name, detail))


def check(name, cond, detail=""):
    (ok if cond else bad)(name, detail)
    return cond


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def _norm(p):
    """规范化路径：去掉 junction 读出来的 \\\\?\\ 前缀，再统一大小写与分隔符。"""
    if not p:
        return ""
    p = p.replace("\\\\?\\", "").replace("\\??\\", "")
    return os.path.normcase(os.path.normpath(p))


def link_state(path, root):
    """判断解压出来的符号链接是什么形态。

    返回 (kind, detail)：
      symlink  —— 真正的 Windows 符号链接
      junction —— 目录联接（免权限方案）
      magic    —— Cygwin 的 "!<symlink>目标" 文件（Windows 读得到目标，但本身不是链接）
      missing / other
    """
    if not os.path.lexists(path):
        return "missing", ""
    try:
        st = os.lstat(path)
    except OSError as e:
        return "other", "lstat 失败 %s" % e
    if os.path.islink(path):
        return "symlink", os.readlink(path)
    if st.st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT:
        try:
            return "junction", os.readlink(path)
        except OSError:
            return "junction", ""
    tgt = core.read_cygwin_symlink(path)
    if tgt is not None:
        return "magic", tgt
    return "other", ""


def verify_tar_vs_dir(tar_path, out_dir, label, symlink_mode="native"):
    """把 tar 里的每个条目跟解压出来的目录逐一比对。"""
    missing, mismatch, nfile, nlink, ndir = [], [], 0, 0, 0
    perm_info = []
    link_kinds = {}
    with tarfile.open(tar_path) as tf:
        for m in tf.getmembers():
            dst = os.path.join(out_dir, *m.name.split("/"))
            if m.isdir():
                ndir += 1
                if not os.path.isdir(dst):
                    missing.append("dir:" + m.name)
                continue
            if m.issym():
                nlink += 1
                kind, detail = link_state(dst, out_dir)
                link_kinds[kind] = link_kinds.get(kind, 0) + 1
                if kind == "missing":
                    missing.append("symlink:" + m.name)
                elif kind == "other":
                    if symlink_mode == "copy":
                        # copy 模式下链接文件被替换成目标内容，属于预期行为
                        want = core._resolve_target(out_dir, dst, m.linkname)
                        if os.path.isfile(want) and os.path.isfile(dst) and sha_file(want) == sha_file(dst):
                            link_kinds["copied"] = link_kinds.get("copied", 0) + 1
                        else:
                            mismatch.append("copy %s: 内容与目标不符" % m.name)
                    else:
                        mismatch.append("symlink %s: %s" % (m.name, detail))
                elif kind in ("symlink", "magic"):
                    if detail != m.linkname:
                        mismatch.append("symlink %s: %r != %r" % (m.name, detail, m.linkname))
                elif kind == "junction":
                    want = _norm(core._resolve_target(out_dir, dst, m.linkname))
                    if _norm(detail) != want:
                        mismatch.append("junction %s: %r != %r" % (m.name, detail, want))
                    elif not os.path.isdir(dst):
                        mismatch.append("junction 打不开: %s" % m.name)
                continue
            if m.islnk():
                nlink += 1
                src = os.path.join(out_dir, *m.linkname.split("/"))
                if not os.path.exists(dst):
                    missing.append("hardlink:" + m.name)
                elif sha_file(src) != sha_file(dst):
                    mismatch.append("hardlink content:" + m.name)
                else:
                    try:
                        st1, st2 = os.stat(src), os.stat(dst)
                        if st1.st_ino != st2.st_ino:
                            perm_info.append("硬链接未真正共享 inode: %s" % m.name)
                    except OSError:
                        pass
                continue
            if not m.isfile():
                continue                      # 设备节点等特殊文件单独统计
            nfile += 1
            if not os.path.isfile(dst):
                missing.append("file:" + m.name)
                continue
            data = tf.extractfile(m).read()
            if hashlib.sha256(data).hexdigest() != sha_file(dst):
                mismatch.append("content:" + m.name)
            if os.path.getsize(dst) != m.size:
                mismatch.append("size:" + m.name)
            # 只读文件的权限位（Cygwin 在 NTFS 上用只读属性模拟）
            if m.mode & 0o200 == 0 and os.access(dst, os.W_OK):
                perm_info.append("只读位未生效: %s (mode=%o)" % (m.name, m.mode))
    detail = "文件 %d / 链接 %d / 目录 %d" % (nfile, nlink, ndir)
    if link_kinds:
        detail += "；链接形态 " + "、".join("%s×%d" % (k, v) for k, v in sorted(link_kinds.items()))
    if perm_info:
        detail += "；备注：" + "；".join(perm_info[:2])
    check(label, not missing and not mismatch,
          detail + ("" if not (missing or mismatch) else " 缺失=%s 不一致=%s" % (missing[:4], mismatch[:4])))
    return link_kinds


def fresh(path):
    """清空并重建目录；用 core.safe_rmtree 以免跟进上次解压出来的目录联接。"""
    if os.path.lexists(path):
        core.safe_rmtree(path)
    if os.path.lexists(path):
        # 极端情况下（被杀软/资源管理器占用）退一步用系统的 rd
        subprocess.run(["cmd", "/c", "rd", "/s", "/q", path], capture_output=True)
    os.makedirs(path)
    return path


def verify_dir_vs_dir(src_dir, out_dir, label):
    """普通目录源 vs 解压结果，逐文件比对。"""
    missing, mismatch, n = [], [], 0
    for dirpath, dirnames, filenames in os.walk(src_dir):
        rel = os.path.relpath(dirpath, src_dir)
        for d in dirnames:
            nd = os.path.join(out_dir, d) if rel == "." else os.path.join(out_dir, rel, d)
            if not os.path.isdir(nd):
                missing.append("dir:" + os.path.join(rel, d))
        for fn in filenames:
            n += 1
            sp = os.path.join(dirpath, fn)
            dp = os.path.join(out_dir, fn) if rel == "." else os.path.join(out_dir, rel, fn)
            if not os.path.isfile(dp):
                missing.append("file:" + os.path.join(rel, fn))
            elif sha_file(sp) != sha_file(dp):
                mismatch.append("content:" + os.path.join(rel, fn))
    check(label, not missing and not mismatch,
          "文件 %d" % n + ("" if not (missing or mismatch)
                          else " 缺失=%s 不一致=%s" % (missing[:3], mismatch[:3])))


# ------------------------------------------------------------------ 测试
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()

    print("=" * 78)
    print("imgtool 端到端测试")
    print("引擎：fsck.erofs %s @ %s" % (core.engine_version(), core.engine_dir()))
    print("=" * 78)

    fresh(OUT)

    # ---------------------------------------------------- 1. 造镜像
    print("\n[1] 生成测试镜像（mkfs.erofs 压缩自造 tar）")
    fixtures = make_fixtures.make_all(os.path.join(OUT, "fixtures"), quick=args.quick)
    check("生成测试镜像", len(fixtures) >= 3, "共 %d 个" % len(fixtures))
    if not fixtures:
        return 1
    default_variant = None
    for v in fixtures:
        if v[0] == "lz4":
            default_variant = v
    default_variant = default_variant or fixtures[0]
    _, base_img, base_tar, _ = default_variant

    # ---------------------------------------------------- 2. 每种算法解压
    print("\n[2] 各压缩算法/布局解压并逐文件校验")
    for name, img, tar, _man in fixtures:
        out = os.path.join(OUT, "codec_" + name)
        core.safe_rmtree(out)
        try:
            t0 = time.time()
            res = core.extract_image(img, dest=out, policy="overwrite")
            dt = time.time() - t0
            verify_tar_vs_dir(tar, out, "解压 %s" % name)
            info = core.sniff(img)
            print("         %s -> %d 个文件 %.1f MB %.1fs（%.1f MB/s）"
                  % (info.label, res.files, res.size / 1048576.0, dt,
                     (res.size / 1048576.0) / max(dt, 0.001)))
        except Exception as e:
            bad("解压 %s" % name, "%s: %s" % (type(e).__name__, e))

    # ---------------------------------------------------- 2b. 高级布局
    print("\n[2b] 高级布局（fragments / 元数据压缩 / 目录压缩，用普通目录当源）")
    layouts = make_fixtures.make_layout_fixtures(os.path.join(OUT, "fixtures"))
    if not layouts:
        print("         [跳过] 三个布局的 mkfs 都没成功（不影响解压主流程）")
    for name, img, src in layouts:
        out = os.path.join(OUT, "layout_" + name)
        core.safe_rmtree(out)
        try:
            core.extract_image(img, dest=out, policy="overwrite")
            verify_dir_vs_dir(src, out, "解压 %s" % name)
        except Exception as e:
            bad("解压 %s" % name, "%s: %s" % (type(e).__name__, str(e)[:140]))

    # ---------------------------------------------------- 3. 默认目录名
    print("\n[3] 默认输出目录 = 镜像同目录下的同名文件夹")
    d = fresh(os.path.join(OUT, "default_dest"))
    img = os.path.join(d, "system.img")
    shutil.copyfile(base_img, img)
    res = core.extract_image(img)
    check("输出目录叫 system", os.path.isdir(os.path.join(d, "system")), res.dest)
    verify_tar_vs_dir(base_tar, os.path.join(d, "system"), "默认目录内容")
    check("返回值指向该目录", os.path.normcase(res.dest) == os.path.normcase(os.path.join(d, "system")))

    # ---------------------------------------------------- 4. 冲突策略
    print("\n[4] 输出目录已存在的两种策略")
    res2 = core.extract_image(img, policy="auto")
    check("auto -> 自动加序号", os.path.isdir(os.path.join(d, "system (2)")), os.path.basename(res2.dest))
    res3 = core.extract_image(img, policy="auto")
    check("auto -> 继续加序号", os.path.isdir(os.path.join(d, "system (3)")), os.path.basename(res3.dest))
    # 覆盖前先塞一个垃圾文件，验证"删除后重建"真的清干净了
    with open(os.path.join(d, "system", "STALE_FILE.txt"), "w") as f:
        f.write("should be gone\n")
    res4 = core.extract_image(img, policy="overwrite")
    check("overwrite -> 复用原目录", os.path.normcase(res4.dest) == os.path.normcase(os.path.join(d, "system")))
    check("overwrite -> 旧文件已被清掉",
          not os.path.exists(os.path.join(d, "system", "STALE_FILE.txt")))
    verify_tar_vs_dir(base_tar, os.path.join(d, "system"), "覆盖后内容仍正确")

    # ---------------------------------------------------- 4b. 符号链接处理
    print("\n[4b] 符号链接的三种处理方式")
    d = fresh(os.path.join(OUT, "links"))
    for mode in ("native", "copy", "keep"):
        out = os.path.join(d, mode)
        core.safe_rmtree(out)
        try:
            r = core.extract_image(base_img, dest=out, policy="overwrite",
                                   symlinks=mode, link_manifest=(mode == "native"))
            kinds = verify_tar_vs_dir(base_tar, out, "符号链接模式 %s" % mode, symlink_mode=mode)
            print("         统计：%s" % r.links)
            for k in ("symlink", "junction", "copy", "kept"):
                if r.links.get(k):
                    print("         %s=%d（形态：%s）" % (k, r.links[k], kinds))
            if mode in ("native", "copy"):
                check("native/copy 模式下不应残留未处理的链接文件",
                      r.links.get("kept", 0) == 0 or r.links.get("kept", 0) == r.links.get("broken", 0),
                      "kept=%d" % r.links.get("kept", 0))
            if mode == "native":
                man = os.path.join(out, core.SYMLINK_MANIFEST)
                check("写了符号链接清单", os.path.isfile(man),
                      open(man, encoding="utf-8").read().strip().splitlines()[-1][:70]
                      if os.path.isfile(man) else "缺失")
        except Exception as e:
            bad("符号链接模式 %s" % mode, "%s: %s" % (type(e).__name__, str(e)[:140]))

    # ---------------------------------------------------- 5. sparse
    print("\n[5] Android sparse 镜像（先展开成 raw 再解压）")
    d = fresh(os.path.join(OUT, "sparse"))
    sp = os.path.join(d, "system_sparse.img")
    t0 = time.time()
    sparse.raw_to_sparse(base_img, sp)
    raw_size = sparse.raw_size(sp)
    check("生成的 sparse 文件头合法", sparse.is_sparse(sp),
          "%.1f MB -> %.1f MB, %.1fs" % (os.path.getsize(base_img) / 1048576.0,
                                         os.path.getsize(sp) / 1048576.0, time.time() - t0))
    info = core.sniff(sp)
    check("识别为 android-sparse", info.kind == "android-sparse",
          "展开后 %.1f MB" % (info.raw_size / 1048576.0))
    res = core.extract_image(sp)
    check("解压出 system_sparse 目录", os.path.isdir(os.path.join(d, "system_sparse")))
    verify_tar_vs_dir(base_tar, os.path.join(d, "system_sparse"), "sparse 解压内容")
    leftover = [f for f in os.listdir(d) if f.endswith(".rawtmp")]
    check("临时 raw 文件已清理", not leftover, str(leftover))

    # ---------------------------------------------------- 6. offset
    print("\n[6] EROFS 位于非 0 偏移（例如被包在别的容器里）")
    d = fresh(os.path.join(OUT, "offset"))
    off_img = os.path.join(d, "boot_like.img")
    with open(off_img, "wb") as f:
        f.write(b"\x41" * 4096)                     # 前面塞 4KB 别的数据
        with open(base_img, "rb") as g:
            shutil.copyfileobj(g, f)
    info = core.sniff(off_img)
    check("自动识别出 offset=4096", info.kind == "erofs" and info.offset == 4096,
          "kind=%s offset=%d" % (info.kind, info.offset))
    res = core.extract_image(off_img)
    verify_tar_vs_dir(base_tar, res.dest, "带偏移镜像解压内容")

    # ---------------------------------------------------- 7. 中文/空格路径
    print("\n[7] 中文 / 空格路径")
    d = fresh(os.path.join(OUT, "cn"))
    cn_dir = os.path.join(d, "\u4e2d\u6587 \u76ee\u5f55")
    os.makedirs(cn_dir)
    cn_img = os.path.join(cn_dir, "\u7cfb\u7edf\u955c\u50cf.img")
    shutil.copyfile(base_img, cn_img)
    res = core.extract_image(cn_img)
    expect = os.path.join(cn_dir, "\u7cfb\u7edf\u955c\u50cf")
    check("输出到中文同名目录", os.path.isdir(expect), res.dest)
    verify_tar_vs_dir(base_tar, expect, "中文路径下内容")
    check("中文文件名还原正确",
          os.path.isfile(os.path.join(expect, "\u4e2d\u6587\u76ee\u5f55", "\u4e2d\u6587\u6587\u4ef6.txt")))

    # ---------------------------------------------------- 8. 错误处理
    print("\n[8] 错误处理")
    d = fresh(os.path.join(OUT, "errors"))

    junk = os.path.join(d, "junk.img")
    with open(junk, "wb") as f:
        f.write(os.urandom(64 * 1024))
    try:
        core.extract_image(junk)
        bad("垃圾文件被拒绝", "居然没报错")
    except core.ExtractError as e:
        ok("垃圾文件被拒绝", str(e)[:70])

    empty = os.path.join(d, "empty.img")
    open(empty, "wb").close()
    try:
        core.extract_image(empty)
        bad("空文件被拒绝", "居然没报错")
    except core.ExtractError as e:
        ok("空文件被拒绝", str(e)[:70])

    try:
        core.extract_image(os.path.join(d, "nope.img"))
        bad("不存在的文件被拒绝", "居然没报错")
    except core.ExtractError as e:
        ok("不存在的文件被拒绝", str(e)[:70])

    ext4 = os.path.join(d, "ext4.img")
    with open(ext4, "wb") as f:
        f.write(b"\0" * 0x438 + b"\x53\xef" + b"\0" * 1024)
    info = core.sniff(ext4)
    check("ext4 镜像被识别", info.kind.startswith("ext"), info.label)
    try:
        core.extract_image(ext4)
        bad("ext4 镜像给出友好提示", "居然没报错")
    except core.ExtractError as e:
        ok("ext4 镜像给出友好提示", str(e)[:70])

    f2fs = os.path.join(d, "f2fs.img")
    with open(f2fs, "wb") as f:
        f.write(b"\0" * 0x400 + b"\x10\x20\xf5\xf2" + b"\0" * 1024)
    check("f2fs 镜像被识别", core.sniff(f2fs).kind == "f2fs", core.sniff(f2fs).label)

    # ---------------------------------------------------- 9. 取消
    print("\n[9] 取消正在进行的解压")
    big = [f for f in fixtures if f[0] == "big"]
    if big:
        _, bimg, btar, _ = big[0]
        d = fresh(os.path.join(OUT, "cancel"))
        dst = os.path.join(d, "out")
        flag = threading.Event()
        state = {"ticks": 0}

        def on_prog(files, size, elapsed):
            # 一看到进度回调就请求取消，避免"解压太快，还没来得及取消就完成了"
            state["ticks"] += 1
            flag.set()

        def worker():
            try:
                core.extract_image(bimg, dest=dst, policy="overwrite",
                                   cancel=flag.is_set, on_progress=on_prog)
                state["result"] = "completed"
            except Exception as e:
                state["result"] = "%s: %s" % (type(e).__name__, str(e)[:80])

        th = threading.Thread(target=worker)
        th.start()
        th.join(timeout=60)
        print("         进度回调次数=%d，结果=%s" % (state["ticks"], str(state.get("result"))[:70]))
        check("取消后线程及时退出", not th.is_alive(), str(state.get("result"))[:90])
        check("取消被正确报告", str(state.get("result", "")).startswith("ExtractError"),
              str(state.get("result"))[:90])
    else:
        print("  [跳过] 没有 big 镜像")

    # ---------------------------------------------------- 10. 特殊文件
    print("\n[10] 特殊文件（设备节点 / FIFO）—— 真实镜像里可能有")
    fxdir = os.path.dirname(base_img)
    torture_img = os.path.join(fxdir, "fixture_torture.img")
    torture_tar = os.path.join(fxdir, "torture_src.tar")
    rc, _ = make_fixtures.mkfs_from_tar(torture_img, torture_tar, ["-zlz4"], log=False)
    if rc == 0:
        d = fresh(os.path.join(OUT, "torture"))
        outdir = os.path.join(d, "out")
        try:
            core.extract_image(torture_img, dest=outdir, policy="overwrite")
            dev = os.path.join(outdir, "dev")
            got = sorted(os.listdir(dev)) if os.path.isdir(dev) else []
            print("         解压出的 dev/ 内容：%s" % (got or "(空)"))
            check("含设备节点的镜像整盘解压不中断",
                  os.path.isfile(os.path.join(outdir, "normal.txt")))
        except core.ExtractError as e:
            print("         [注意] 含设备节点的镜像解压报错：%s" % str(e)[:200])
            bad("含设备节点的镜像整盘解压不中断", str(e)[:120])
    else:
        print("         [跳过] torture 镜像生成失败")

    # ---------------------------------------------------- 汇总
    print("\n" + "=" * 78)
    print("结果：%d 项通过，%d 项失败" % (len(PASS), len(FAIL)))
    for name, detail in FAIL:
        print("   FAIL %s  %s" % (name, detail))
    print("=" * 78)

    # 收尾：删掉又大又没保留价值的测试产物（小镜像留着当演示素材）
    fxdir = os.path.join(OUT, "fixtures")
    if os.path.isdir(fxdir):
        for fn in os.listdir(fxdir):
            fp = os.path.join(fxdir, fn)
            try:
                if os.path.isfile(fp) and os.path.getsize(fp) > (32 << 20):
                    os.remove(fp)
                    print("   （已清理大文件 %s）" % fn)
            except OSError:
                pass
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
