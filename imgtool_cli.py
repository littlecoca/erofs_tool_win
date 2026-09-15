# -*- coding: utf-8 -*-
# SPDX-License-Identifier: 0BSD
"""命令行启动入口（供 拖放解压.cmd / imgtool.bat 调用）。

    python imgtool_cli.py <镜像> [更多镜像...] [选项]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from imgtool import cli  # noqa: E402

if __name__ == "__main__":
    sys.exit(cli.main())
