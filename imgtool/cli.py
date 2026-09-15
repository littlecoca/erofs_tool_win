# -*- coding: utf-8 -*-
# SPDX-License-Identifier: 0BSD
"""命令行入口：python -m imgtool.cli  [选项] 镜像...

也支持把 IMG 文件直接拖到 拖放解压.cmd / imgtool.bat 上（等价于命令行传参）。
"""

import argparse
import os
import sys

from . import core


def _log(msg):
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("--gui", "-g"):
        from . import gui
        return gui.main()

    ap = argparse.ArgumentParser(
        prog="imgtool",
        description="EROFS/IMG 解压工具（Windows 原生，基于 erofs-utils 的 fsck.erofs）")
    ap.add_argument("images", nargs="*", help="要解压的 IMG 文件（可多个）")
    ap.add_argument("-o", "--out", help="输出目录（默认：镜像同目录下的同名文件夹）")
    ap.add_argument("--policy", choices=["auto", "overwrite"], default="auto",
                    help="输出目录已存在时：auto=自动改名(默认) overwrite=删除后重建")
    ap.add_argument("--overwrite", action="store_true", help="等价于 --policy overwrite")
    ap.add_argument("--symlinks", choices=list(core.SYMLINK_MODES), default="native",
                    help="符号链接处理：native=还原成 Windows 链接(默认) copy=复制目标内容 keep=保留原样")
    ap.add_argument("--offset", type=lambda v: int(v, 0), default=None,
                    help="EROFS 超级块偏移（一般自动识别）")
    ap.add_argument("--keep-temp", action="store_true", help="保留 sparse 展开的临时 raw 文件")
    ap.add_argument("--info", action="store_true", help="只打印镜像信息，不解压")
    ap.add_argument("--gui", action="store_true", help="启动图形界面")
    ap.add_argument("--version", action="store_true", help="打印引擎与工具版本")
    args = ap.parse_args(argv)

    if args.version:
        print("imgtool 引擎：fsck.erofs %s (%s)" % (core.engine_version(), core.engine_dir()))
        return 0
    if not args.images:
        ap.print_help()
        return 2

    policy = "overwrite" if args.overwrite else args.policy
    rc_all = 0
    for img in args.images:
        try:
            info = core.sniff(img)
            print("=" * 66)
            print("%s\n  %s%s" % (os.path.basename(img), info.label,
                                  ("，offset=%d" % info.offset) if info.offset else ""))
            if args.info:
                if info.extra.get("_raw"):
                    print(info.extra["_raw"])
                continue
            res = core.extract_image(img, dest=args.out, policy=policy, offset=args.offset,
                                     on_log=_log, keep_temp=args.keep_temp,
                                     symlinks=args.symlinks)
            print(res.summary())
        except core.ExtractError as e:
            print("[错误] %s" % e)
            rc_all = 1
        except KeyboardInterrupt:
            print("[中断] 已取消")
            return 130
    return rc_all


if __name__ == "__main__":
    sys.exit(main())
