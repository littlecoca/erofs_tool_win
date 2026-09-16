# -*- coding: utf-8 -*-
# SPDX-License-Identifier: 0BSD
"""拆开 engine\\ 里的 PE 文件，看 CMake 到底编出了个什么东西。

读 PE 头 / 节表 / 导入表，并抓编译器和 CRT 的指纹，用来解释"交叉编译是怎么落到 .exe 上的"。

用法：python tools\\probe_pe.py [文件...]
"""

import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = ["engine/fsck.erofs.exe", "engine/cygwin1.dll"]

MACHINE = {0x014C: "i386 (x86)", 0x8664: "AMD64 (x86_64)", 0xAA64: "ARM64"}
SUBSYSTEM = {2: "WINDOWS_GUI", 3: "WINDOWS_CUI（控制台程序）"}
CHARACTERISTICS = [(0x0002, "EXECUTABLE_IMAGE"), (0x0020, "LARGE_ADDRESS_AWARE"),
                   (0x0100, "32BIT_MACHINE"), (0x2000, "DLL")]
DLLCHARACTERISTICS = [(0x0040, "DYNAMIC_BASE (ASLR)"), (0x0100, "NX_COMPAT"),
                      (0x4000, "GUARD_CF"), (0x8000, "TERMINAL_SERVER_AWARE")]


class PE(object):
    def __init__(self, path):
        self.path = path
        self.data = open(path, "rb").read()

    def u16(self, off):
        return struct.unpack_from("<H", self.data, off)[0]

    def u32(self, off):
        return struct.unpack_from("<I", self.data, off)[0]

    def parse(self):
        d = self.data
        assert d[:2] == b"MZ", "不是 PE 文件"
        pe = self.u32(0x3C)
        assert d[pe:pe + 4] == b"PE\0\0", "PE 签名不对"
        coff = pe + 4
        self.machine = self.u16(coff)
        self.nsec = self.u16(coff + 2)
        self.timestamp = self.u32(coff + 4)
        self.opt_size = self.u16(coff + 16)
        self.characteristics = self.u16(coff + 18)
        self.symtab_ptr = self.u32(coff + 8)
        self.symtab_num = self.u32(coff + 12)
        self.opt = coff + 20
        self.magic = self.u16(self.opt)
        self.pe32plus = (self.magic == 0x20B)
        self.subsystem = self.u16(self.opt + 68)
        self.dllchar = self.u16(self.opt + 70)
        # 数据目录起始偏移
        self.dd = self.opt + (112 if self.pe32plus else 96)
        # 节表
        self.sections = []
        sec = self.opt + self.opt_size
        for i in range(self.nsec):
            base = sec + i * 40
            name = d[base:base + 8].rstrip(b"\0").decode("latin-1")
            vsize, vaddr, rawsize, rawptr = struct.unpack_from("<IIII", d, base + 8)
            chars = self.u32(base + 36)
            self.sections.append((name, vaddr, vsize, rawptr, rawsize, chars))

    def rva2off(self, rva):
        for _n, vaddr, vsize, rawptr, rawsize, _c in self.sections:
            if vaddr <= rva < vaddr + max(vsize, rawsize):
                return rawptr + (rva - vaddr)
        return None

    def cstr(self, rva):
        off = self.rva2off(rva)
        if off is None:
            return "?"
        end = self.data.find(b"\0", off)
        return self.data[off:end].decode("latin-1", "replace")

    def imports(self):
        """返回 {DLL 名: [函数名或序号, ...]}"""
        out = {}
        imp_rva, imp_size = struct.unpack_from("<II", self.data, self.dd + 8)  # 目录项 1
        if not imp_rva:
            return out
        off = self.rva2off(imp_rva)
        idx = 0
        while True:
            base = off + idx * 20
            oft, _ts, _fc, name_rva, ft = struct.unpack_from("<IIIII", self.data, base)
            if oft == 0 and name_rva == 0 and ft == 0:
                break
            dll = self.cstr(name_rva)
            funcs = []
            thunk_rva = oft or ft
            toff = self.rva2off(thunk_rva)
            step = 8 if self.pe32plus else 4
            j = 0
            while True:
                val = (struct.unpack_from("<Q", self.data, toff + j * step)[0]
                       if self.pe32plus else
                       struct.unpack_from("<I", self.data, toff + j * step)[0])
                if val == 0:
                    break
                if val & (1 << (63 if self.pe32plus else 31)):
                    funcs.append("ordinal#%d" % (val & 0xFFFF))
                else:
                    funcs.append(self.cstr(val + 2))     # 跳过 2 字节 hint
                j += 1
            out[dll] = funcs
            idx += 1
        return out

    def raw_sections_size(self):
        return sum(s[4] for s in self.sections)


def as_date(ts):
    import datetime
    try:
        return datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return "?"


def fingerprint(data):
    """在二进制里找编译器 / 运行库指纹字符串。"""
    hits = {}
    for key in (b"clang version", b"GCC: (", b"LLVM", b"cygwin", b"gcc version",
                b"liberofs", b"erofs-utils"):
        pos = data.find(key)
        if pos >= 0:
            end = data.find(b"\0", pos)
            frag = data[pos:min(end, pos + 90)].decode("latin-1", "replace")
            hits[key.decode()] = frag.split("\n")[0][:90]
    return hits


def main():
    files = sys.argv[1:] or DEFAULT
    for rel in files:
        path = rel if os.path.isabs(rel) else os.path.join(ROOT, rel.replace("/", os.sep))
        if not os.path.isfile(path):
            print("跳过（不存在）:", rel)
            continue
        pe = PE(path)
        pe.parse()
        print("=" * 76)
        print("%s   （%d 字节）" % (os.path.relpath(path, ROOT), os.path.getsize(path)))
        print("=" * 76)
        print("  PE 格式    : %s，可选头 magic=%#x" % ("PE32+（64 位）" if pe.pe32plus else "PE32（32 位）", pe.magic))
        print("  机器类型   : %#06x  %s" % (pe.machine, MACHINE.get(pe.machine, "?")))
        print("  子系统     : %d  %s" % (pe.subsystem, SUBSYSTEM.get(pe.subsystem, "?")))
        print("  节数       : %d，节表总大小 %d 字节" % (pe.nsec, pe.raw_sections_size()))
        print("  文件属性   : %s" % ", ".join(n for b, n in CHARACTERISTICS if pe.characteristics & b))
        print("  映像属性   : %s" % (", ".join(n for b, n in DLLCHARACTERISTICS if pe.dllchar & b) or "（无）"))
        print("  链接时间戳 : %d  =  %s" % (pe.timestamp, as_date(pe.timestamp)))
        stripped = (pe.symtab_ptr == 0 and pe.symtab_num == 0)
        print("  COFF 符号表: %s" % ("已去掉（-Wl,-s 生效，无法反查函数名）" if stripped
                                     else "存在 %d 个符号" % pe.symtab_num))
        dbg_rva, dbg_size = struct.unpack_from("<II", pe.data, pe.dd + 6 * 8)
        print("  调试信息   : %s" % ("无（Release 构建未带 -g）" if dbg_rva == 0
                                     else "有，%d 字节" % dbg_size))
        print("  节区       : %s" % ", ".join(s[0] for s in pe.sections))
        imps = pe.imports()
        print("  导入 DLL   : %d 个" % len(imps))
        for dll, funcs in sorted(imps.items(), key=lambda kv: -len(kv[1])):
            print("     %-22s %4d 个函数   例如：%s"
                  % (dll, len(funcs), ", ".join(funcs[:6])))
        fp = fingerprint(pe.data)
        print("  编译器指纹 :")
        for k, v in fp.items():
            print("     %-14s %s" % (k, v))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
