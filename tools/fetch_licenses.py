# -*- coding: utf-8 -*-
# SPDX-License-Identifier: 0BSD
"""下载第三方许可证全文到 LICENSES\\ 目录（GPL-2.0 / GPL-3.0 / LGPL-3.0）。

engine\\ 里分发的是 GPL-2.0-or-later 的二进制和 LGPL-3.0-or-later 的运行库，
按许可证要求必须随分发物附上全文，所以这里把官方文本抓下来入库。

用法：python tools\\fetch_licenses.py
"""

import os
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 img-tool-license-fetch"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "LICENSES")

SOURCES = [
    ("GPL-2.0.txt", "https://www.gnu.org/licenses/old-licenses/gpl-2.0.txt"),
    ("GPL-3.0.txt", "https://www.gnu.org/licenses/gpl-3.0.txt"),
    ("LGPL-3.0.txt", "https://www.gnu.org/licenses/lgpl-3.0.txt"),
]

HEADER = {
    "GPL-2.0.txt": "engine/fsck.erofs.exe、mkfs.erofs.exe、dump.erofs.exe、extract.erofs.exe",
    "GPL-3.0.txt": "LGPL-3.0 是建立在 GPL-3.0 之上的附加许可，读 LGPL-3.0 需要同时读本文件",
    "LGPL-3.0.txt": "engine/cygwin1.dll（Cygwin 运行库，含链接例外）",
}


def main():
    os.makedirs(DEST, exist_ok=True)
    for name, url in SOURCES:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode("utf-8", "replace")
        # 头部加一段"谁用这个许可证"，方便读者对上号；正文保持原样
        banner = (
            "本文件是许可证原始文本，随本仓库分发以履行下述组件的许可证义务。\n"
            "适用组件：%s\n"
            "来源：%s\n"
            "----------------------------------------------------------------------\n\n"
            % (HEADER[name], url)
        )
        path = os.path.join(DEST, name)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(banner + text)
        print("  %-14s %7d 字节  <- %s" % (name, os.path.getsize(path), url))
    print("\n已写入 %s" % DEST)
    return 0


if __name__ == "__main__":
    sys.exit(main())
