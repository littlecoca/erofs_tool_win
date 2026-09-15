# -*- coding: utf-8 -*-
# SPDX-License-Identifier: 0BSD
"""给源码文件补上 SPDX 许可证标识（幂等，可重复运行）。

* .py/.pyw：插在 shebang / PEP 263 coding 行之后（不能插到 coding 行前面，否则编码声明失效）
* .bat/.cmd：插在 @echo off 之后（保持纯 ASCII 与 CRLF 行尾）

用法：python tools\\add_spdx.py [--check]
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARK = "SPDX-License-Identifier: 0BSD"
SKIP_DIRS = {"test", "\u793a\u4f8b\u955c\u50cf", "__pycache__", "engine", ".git"}


def targets():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in sorted(filenames):
            if fn.endswith((".py", ".pyw", ".bat", ".cmd")):
                yield os.path.join(dirpath, fn)


def patch(path, check_only=False):
    raw = open(path, "rb").read()
    if MARK.encode("ascii") in raw:
        return "already"
    nl = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8")

    if path.endswith((".bat", ".cmd")):
        prefix, comment = "rem ", MARK
    else:
        prefix, comment = "# ", MARK

    lines = text.split(nl)
    insert_at = 0
    if lines and lines[0].startswith("#!"):
        insert_at = 1
    if len(lines) > insert_at and "coding" in lines[insert_at] and lines[insert_at].lstrip().startswith("#"):
        insert_at += 1
    if path.endswith((".bat", ".cmd")):
        for i, line in enumerate(lines[:6]):
            if line.strip().lower().startswith("@echo off"):
                insert_at = i + 1
                break

    if check_only:
        return "missing"
    lines.insert(insert_at, prefix + comment)
    open(path, "wb").write(nl.join(lines).encode("utf-8"))
    return "patched"


def main():
    check_only = "--check" in sys.argv
    stats = {"patched": [], "already": [], "missing": []}
    for path in targets():
        rel = os.path.relpath(path, ROOT)
        stats[patch(path, check_only)].append(rel)
    print("已打标 %d 个，已有 %d 个" % (len(stats["patched"]), len(stats["already"])))
    for r in stats["patched"]:
        print("   + " + r)
    if check_only and stats["missing"]:
        print("缺少 SPDX 标识 %d 个：" % len(stats["missing"]))
        for r in stats["missing"]:
            print("   - " + r)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
