# -*- coding: utf-8 -*-
# SPDX-License-Identifier: 0BSD
"""文档自检：README 里的锚点链接、相对链接、提到的文件路径是否都真实存在。

用法：python tools\check_docs.py
"""

import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = ["README.md", "CHANGELOG.md", "THIRD_PARTY_NOTICES.md", "LICENSE"]


def github_slug(text):
    """按 GitHub 的规则把标题转成锚点。"""
    s = text.strip().lower()
    out = []
    for ch in s:
        if ch in " \t":
            out.append("-")
        elif ch == "-" or ch == "_":
            out.append(ch)
        elif ch.isalnum():
            out.append(ch)
        # 其它（标点、全角括号、·、/、. 等）一律丢弃
    slug = "".join(out)
    return slug


def main():
    problems = []
    docs = [os.path.join(ROOT, f) for f in ("README.md", "CHANGELOG.md",
                                            "THIRD_PARTY_NOTICES.md", "LICENSE",
                                            os.path.join("engine", "README.md"))]
    docs_dir = os.path.join(ROOT, "docs")
    if os.path.isdir(docs_dir):
        docs += [os.path.join(docs_dir, f) for f in sorted(os.listdir(docs_dir))
                 if f.endswith(".md")]
    docs = [d for d in docs if os.path.isfile(d)]

    total = 0
    for doc in docs:
        rel_name = os.path.relpath(doc, ROOT)
        text = open(doc, encoding="utf-8").read()
        base = os.path.dirname(doc)

        # 1) 收集标题锚点（含重名去重后缀）
        slugs = {}
        for m in re.finditer(r"^(#{1,6})\s+(.*?)\s*$", text, re.M):
            s = github_slug(m.group(2))
            n = slugs.get(s, 0)
            slugs[s] = n + 1
            if n:
                slugs["%s-%d" % (s, n)] = 1

        # 2) 检查站内链接
        internal = re.findall(r"\]\(#([^)]+)\)", text)
        bad = sorted({a for a in internal if a not in slugs})
        for a in bad:
            problems.append("%s: 锚点不存在 #%s" % (rel_name, a))

        # 3) 检查相对文件链接（相对该文档所在目录）
        links = sorted(set(re.findall(r"\]\((?!https?:|#)([^)]+)\)", text)))
        for target in links:
            path = os.path.normpath(os.path.join(base, target.replace("/", os.sep)))
            if not os.path.exists(path):
                problems.append("%s: 相对链接指向的文件不存在: %s" % (rel_name, target))

        # 4) 检查正文里提到的反引号路径（只看像项目文件的）
        checked = check_paths(text, base, rel_name, problems)
        total += checked
        print("%-34s 锚点 %-4d 站内链接 %-4d 相对链接 %-3d 路径引用 %d"
              % (rel_name, len(slugs), len(internal), len(links), checked))

    # 5) 其它文档是否存在
    for d in DOCS:
        if not os.path.exists(os.path.join(ROOT, d)):
            problems.append("缺少文档: %s" % d)

    print()
    if problems:
        print("发现 %d 个问题：" % len(problems))
        for p in problems:
            print("  - " + p)
        return 1
    print("文档自检通过 ✔（%d 个文档，%d 处路径引用）" % (len(docs), total))
    return 0


def check_paths(text, base, rel_name, problems):
    """正文反引号里提到的项目文件是否存在。"""
    cand = set(re.findall(r"`([^`\n]+)`", text))
    skip = {"tkinter", "ctypes", "subprocess", "struct", "tarfile", "cmd.exe",
            "shell32.dll", "user32.dll", "python", "pythonw", "python.exe",
            "pythonw.exe", "fsck.erofs", "mkfs.erofs", "dump.erofs",
            "extract.erofs", "cygwin1.dll", "raw_size", "blk_sz", "total_blks",
            "imgtool", "engine", "tests", "tools", "test", "docs", "\u793a\u4f8b\u955c\u50cf",
            "x86_64-pc-cygwin-clang", "x86_64-pc-cygwin-clang++",
            "GPL-2.0-or-later", "LGPL-3.0-or-later", "GPL-2.0+", "0BSD", "liberofs"}
    checked = 0
    for c in sorted(cand):
        if c in skip or " " in c or len(c) > 90:
            continue
        if any(t in c for t in ("*", "\u2192", "<", ">", "$", "|", "(", ")")):
            continue
        if re.match(r"^[A-Za-z]:[\\/]", c) and not os.path.normcase(c).startswith(os.path.normcase(ROOT)):
            continue                      # 形如 D:\rom\system.img 的举例路径
        if c.startswith("/"):
            continue                      # 形如 /usr/x86_64-pc-cygwin/bin/cygwin1.dll 的系统路径
        if "\\" not in c and "/" not in c:
            continue                      # 光秃秃的文件名不按路径校验
        if not re.search(r"\.(py|pyw|md|bat|cmd|ps1|img|exe|dll|txt|json|zip|tar)$", c):
            continue
        rel = c.replace("\\", os.sep).replace("/", os.sep)
        if rel.startswith(".."):
            continue
        checked += 1
        if not (os.path.exists(os.path.join(ROOT, rel))
                or os.path.exists(os.path.join(base, rel))):
            problems.append("%s: 正文提到的文件不存在: %s" % (rel_name, c))
    return checked


if __name__ == "__main__":
    sys.exit(main())
