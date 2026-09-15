# -*- coding: utf-8 -*-
# SPDX-License-Identifier: 0BSD
"""Fetch the Cygwin x86_64 erofs-utils build (fsck.erofs + mkfs.erofs) for Windows."""
import json
import os
import sys
import urllib.request
import zipfile

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) img-tool"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "engine")


def jget(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def download(url, path):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r, open(path, "wb") as f:
        total = 0
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            total += len(chunk)
    return total


rel = jget("https://api.github.com/repos/sekaiacg/erofs-tools/releases/latest")
print("latest tag:", rel.get("tag_name"), "published:", rel.get("published_at"))
assets = {a["name"]: a for a in rel.get("assets", [])}
pick = None
for name, a in assets.items():
    if "Cygwin_x86_64" in name:
        pick = a
        break
if not pick:
    print("no cygwin asset! available:", list(assets))
    sys.exit(1)

os.makedirs(DEST, exist_ok=True)
zpath = os.path.join(DEST, pick["name"])
if os.path.exists(zpath) and os.path.getsize(zpath) == pick["size"]:
    print("already downloaded:", zpath)
else:
    n = download(pick["browser_download_url"], zpath)
    print("downloaded %s -> %s bytes" % (pick["name"], n))

with zipfile.ZipFile(zpath) as z:
    print("zip members:")
    for i in z.infolist():
        print("   %-40s %10d  %s" % (i.filename, i.file_size, oct(i.external_attr >> 16)))
    z.extractall(DEST)

print("\nextracted tree:")
for dirpath, dirnames, filenames in os.walk(DEST):
    for fn in filenames:
        p = os.path.join(dirpath, fn)
        print("   %-70s %10d" % (os.path.relpath(p, ROOT), os.path.getsize(p)))
