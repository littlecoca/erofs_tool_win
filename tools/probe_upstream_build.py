# -*- coding: utf-8 -*-
# SPDX-License-Identifier: 0BSD
"""补齐写文档要用的事实：上游 erofs-utils 自己的编译方式、Cygwin 补丁内容、CI 环境包。"""

import json
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 imgtool-provenance"}


def get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


RAW_UP = "https://raw.githubusercontent.com/erofs/erofs-utils/v1.8.10/"
RAW_TOOLS = "https://raw.githubusercontent.com/sekaiacg/erofs-tools/v1.8.10-251217/"

print("=" * 74)
print("A) 上游 README 里的编译说明")
try:
    t = get(RAW_UP + "README")
    lines = t.splitlines()
    start = next((i for i, l in enumerate(lines) if "How to build" in l or "build" in l.lower()
                  and "configure" in l.lower()), None)
    for l in lines[:70]:
        print("   " + l[:110])
except Exception as e:
    print("  ", e)

print()
print("=" * 74)
print("B) configure.ac 里的编译开关")
try:
    t = get(RAW_UP + "configure.ac")
    for l in t.splitlines():
        if "AC_ARG_ENABLE" in l or "AC_ARG_WITH" in l:
            print("   " + l.strip()[:110])
except Exception as e:
    print("  ", e)

print()
print("=" * 74)
print("C) 4 个 Cygwin 补丁分别改了什么")
tree = json.loads(get("https://api.github.com/repos/sekaiacg/erofs-tools/git/trees/"
                      "7274417816e3adfe0cd6d4a8ff194ec5f41268f4?recursive=1"))["tree"]
for t in tree:
    p = t["path"]
    if p.endswith(".patch"):
        print("  --- %s ---" % p)
        try:
            txt = get(RAW_TOOLS + p)
            body = [l for l in txt.splitlines()
                    if l.startswith(("+++", "---", "@@", "+", "-")) and not l.startswith(("+++", "---"))]
            for l in body[:12]:
                print("      " + l[:104])
        except Exception as e:
            print("      ", e)

print()
print("=" * 74)
print("D) CI 里 cygwin job 的完整步骤")
wf = get(RAW_TOOLS + ".github/workflows/build-erofs-utils.yml")
lines = wf.splitlines()
inside = False
for i, l in enumerate(lines):
    if l.strip().startswith("Build-cygwin:"):
        inside = True
    elif inside and l and not l.startswith(" ") and not l.startswith("-"):
        break
    if inside:
        print("   %s" % l[:112])
