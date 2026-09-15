# -*- coding: utf-8 -*-
# SPDX-License-Identifier: 0BSD
"""GUI 启动入口（用 pythonw 运行，不弹黑框）。

    pythonw imgtool_gui.pyw
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from imgtool import gui  # noqa: E402

if __name__ == "__main__":
    sys.exit(gui.main())
