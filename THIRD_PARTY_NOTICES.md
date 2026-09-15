# 第三方组件声明（Third-Party Notices）

本仓库的 `imgtool/`、`tests/`、`tools/`、启动脚本与文档均为本项目原创，采用 **0BSD**
（BSD Zero Clause License，SPDX: `0BSD`）——不需要署名、不需要保留版权声明、没有任何附加条件，
且与 GPL 兼容。许可证全文见 [LICENSE](LICENSE)。

`engine/` 目录下的可执行文件**不是**本项目的代码，而是独立第三方程序，随本仓库一并分发。
清单、来源与许可证如下。

---

## 1. erofs-utils（fsck.erofs / mkfs.erofs / dump.erofs）

| 项目 | 内容 |
| --- | --- |
| 组件 | `engine\fsck.erofs.exe`、`engine\mkfs.erofs.exe`、`engine\dump.erofs.exe` |
| 上游项目 | <https://github.com/erofs/erofs-utils> |
| 版本 | **1.8.10**（构建标识 `gee46dd74`） |
| 构建来源 | <https://github.com/sekaiacg/erofs-tools>，release `v1.8.10-251217`，资产 `erofs-utils-v1.8.10-gee46dd74-251217-Cygwin_x86_64.zip` |
| 构建方式 | Cygwin x86_64 交叉/原生构建（Windows 可执行文件） |
| 许可证 | **GPL-2.0**（GNU General Public License v2.0） |
| 许可证全文 | <https://www.gnu.org/licenses/old-licenses/gpl-2.0.html> |
| 对应源码 | <https://github.com/erofs/erofs-utils>（版本 1.8.10 / 提交 `gee46dd74`） |

### 校验值

```
erofs-utils-v1.8.10-gee46dd74-251217-Cygwin_x86_64.zip
  bytes  5146583
  sha256 b6a24de0cfe49a95283cf306db1d158bdb63850e0687c8a8b0f4c4a540ba35ba

fsck.erofs.exe   1965568  81890a95aa6e9dd710119b22c674d089a311cd48474d270923873fbc37c05afa
mkfs.erofs.exe   2073600  e2bd628cefd10cc3abca747a65f344b21fc6ce2ae0ec36e5cfb9bc64d521202c
dump.erofs.exe   1964544  85456613664605b40e752fc22eb2a6a24e2966a5c4029af442a52adf7b4286cb
```

---

## 2. extract.erofs（第三方增强工具）

| 项目 | 内容 |
| --- | --- |
| 组件 | `engine\extract.erofs.exe` |
| 来源 | <https://github.com/sekaiacg/erofs-tools>（基于上游 erofs-utils 的衍生工具） |
| 许可证 | **GPL-2.0**（衍生自 GPL-2.0 的 erofs-utils） |
| 对应源码 | 同上仓库的 `src/` 目录 |
| 校验值 | `3077632` 字节，sha256 `d7378ddb500c4338c4ef02f0da7601693a16807faafa453c1dc5750baf3b0dca` |
| 本项目是否使用 | **当前未使用**（保留备用：它支持按路径提取并导出 `fs_config` / `file_contexts`） |

---

## 3. Cygwin 运行库

| 项目 | 内容 |
| --- | --- |
| 组件 | `engine\cygwin1.dll` |
| 上游项目 | <https://cygwin.com/> |
| 许可证 | **LGPL-3.0**（GNU Lesser General Public License v3.0），另有部分组件采用其他兼容许可证 |
| 许可证全文 | <https://www.gnu.org/licenses/lgpl-3.0.html> |
| 对应源码 | <https://cygwin.com/sources.html>（Cygwin 源码发布页） |
| 校验值 | `3012149` 字节，sha256 `ab77212a71c2e2e8b870452d2c32bc72a6708d6e963dd3ebe2ac1a946cffc242` |

> `cygwin1.dll` 必须与上述 exe 位于同一目录，Cygwin 程序才能启动。

---

## 4. 分发者需要做什么

本项目只是**通过命令行调用**上述独立程序（GPL 术语中的"聚合"），不修改也不链接它们。
如果你要分发本仓库（包括把它打包成单文件 exe 发布），请：

1. **保留本文件与 `engine/README.md`**，不要删除来源、版本与许可证信息；
2. **随分发物附上 GPL-2.0 与 LGPL-3.0 许可证全文**（可直接从上面的链接获取）；
3. **提供对应源码的获取方式**：写明上游仓库地址 + 版本号（1.8.10 / `gee46dd74`）即可满足
   GPL-2.0 第 3 节对"非商业分发"的要求；商业分发建议同时提供书面要约或镜像源码；
4. **不要声称这些二进制由本项目授权**，也不要给它们换许可证；
5. 若修改了 erofs-utils 源码再分发，则修改后的二进制同样受 GPL-2.0 约束，必须一并提供源码。

### 想完全避开这些义务？

仓库里已经提供了引擎获取脚本：

```powershell
python tools\fetch_engine.py     # 自动下载并解包最新 Cygwin 版 erofs-utils 到 engine\
```

你也可以在 `.gitignore` 中取消注释 `/engine/*.exe` 与 `/engine/*.dll`，
让仓库**只包含源码**，由使用者自行下载引擎——这样仓库分发物中不含任何第三方二进制。
