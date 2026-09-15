# engine —— 解压引擎（erofs-utils 的 Windows/Cygwin 构建）

本目录里的可执行文件**不是**本项目的代码，而是官方 EROFS 用户态工具集
[erofs-utils](https://github.com/erofs/erofs-utils) 的 Windows(Cygwin x86_64) 构建，
来自 [sekaiacg/erofs-tools](https://github.com/sekaiacg/erofs-tools) 的预编译发布版
（上游 erofs-utils v1.8.10）。

| 文件 | 作用 |
| --- | --- |
| `fsck.erofs.exe` | **解压主力**：校验并解压 EROFS 镜像（`--extract=<目录>`） |
| `mkfs.erofs.exe` | 造镜像（本项目用它生成测试镜像，也可留给用户自己打包） |
| `dump.erofs.exe` | 打印超级块/目录/inode 信息（识别镜像类型时用） |
| `extract.erofs.exe` | sekaiacg 增强版解包工具（可额外导出 `fs_config` / `file_contexts`，本工具暂未使用） |
| `cygwin1.dll` | Cygwin 运行库，必须和 exe 放在同一目录 |

许可证：erofs-utils 采用 **GPL-2.0**（`fsck.erofs`/`mkfs.erofs`/`dump.erofs`）；
Cygwin 运行库为 **LGPL-3.0**。本项目的 Python 代码调用这些程序，属于 GPL 意义上的
"聚合"使用；如果你要分发这套目录，请一并遵守上述许可证（附上许可证文本与源码链接）。

重新获取/升级引擎：

```powershell
python tools\fetch_engine.py      # 自动下载最新 Cygwin x86_64 版本并解包到本目录
```

* 为什么是 Cygwin 版：Windows 上没有官方 erofs-utils 构建，Cygwin 版是真正跑
  `fsck.erofs` 本体的最轻量方式 —— 不需要 WSL、不需要虚拟机、不需要管理员权限，
  只要一个 `cygwin1.dll`。
* 已验证：`lz4 / lz4hc / lzma / deflate / zstd`、`-C` 分簇、fragments、dedupe、
  目录压缩、元数据压缩、chunk 化等布局都能正常解压（见 `tests/e2e_test.py`）。
