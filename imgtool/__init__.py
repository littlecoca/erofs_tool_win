# -*- coding: utf-8 -*-
# SPDX-License-Identifier: 0BSD
"""imgtool —— Windows 原生 EROFS/IMG 解压工具。

引擎：erofs-utils 的 Cygwin x86_64 构建（fsck.erofs / mkfs.erofs / dump.erofs），
随包放在 ../engine 下，不需要 WSL、不需要管理员权限、不需要安装任何东西。

对外主要接口：
    from imgtool import core
    info = core.sniff(r"D:\\system.img")
    res  = core.extract_image(r"D:\\system.img")
"""

__version__ = "0.1.0"
