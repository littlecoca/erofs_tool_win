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
    readme = os.path.join(ROOT, "README.md")
    text = open(readme, encoding="utf-8").read()

    # 1) 收集标题锚点（含重名去重后缀）
    slugs = {}
    for m in re.finditer(r"^(#{1,6})\s+(.*?)\s*$", text, re.M):
        s = github_slug(m.group(2))
        n = slugs.get(s, 0)
        slugs[s] = n + 1
        if n:
            slugs["%s-%d" % (s, n)] = 1
    print("README 标题锚点 %d 个" % len(slugs))

    # 2) 检查站内链接
    internal = re.findall(r"\]\(#([^)]+)\)", text)
    bad = sorted({a for a in internal if a not in slugs})
    print("站内链接 %d 个" % len(internal))
    for a in bad:
        problems.append("锚点不存在: #%s" % a)

    # 3) 检查相对文件链接
    for target in sorted(set(re.findall(r"\]\((?!https?:|#)([^)]+)\)", text))):
        path = os.path.join(ROOT, target.replace("/", os.sep))
        if not os.path.exists(path):
            problems.append("相对链接指向的文件不存在: %s" % target)
    print("相对链接检查完毕")

    # 4) 检查正文里提到的反引号路径（只看像项目文件的）
    cand = set(re.findall(r"`([^`\n]+)`", text))
    skip_words = {"tkinter", "ctypes", "subprocess", "struct", "tarfile", "cmd.exe",
                  "shell32.dll", "user32.dll", "python", "pythonw", "python.exe",
                  "pythonw.exe", "fsck.erofs", "mkfs.erofs", "dump.erofs",
                  "extract.erofs", "cygwin1.dll", "raw_size", "blk_sz", "total_blks",
                  "imgtool", "engine", "tests", "tools", "test", "示例镜像"}
    checked = 0
    for c in sorted(cand):
        if c in skip_words or " " in c or len(c) > 90:
            continue
        # 跳过示例路径、通配符、未来计划里的文件、表格里的箭头说明
        if any(t in c for t in ("*", "→", "<", ">", "```")):
            continue
        if re.match(r"^[A-Za-z]:[\\/]", c) and not os.path.normcase(c).startswith(os.path.normcase(ROOT)):
            continue          # 形如 D:\rom\system.img 的举例路径
        looks_like_path = ("\\" in c or "/" in c) and re.search(r"\.(py|pyw|md|bat|cmd|ps1|img|exe|dll|txt|json|zip|tar)$", c)
        if not looks_like_path:
            continue
        rel = c.replace("\\", os.sep).replace("/", os.sep)
        if rel.startswith(".."):
            continue
        checked += 1
        if not os.path.exists(os.path.join(ROOT, rel)):
            problems.append("正文提到的文件不存在: %s" % c)
    print("正文路径引用检查 %d 个" % checked)

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
    print("文档自检通过 ✔")
    return 0


if __name__ == "__main__":
    sys.exit(main())
