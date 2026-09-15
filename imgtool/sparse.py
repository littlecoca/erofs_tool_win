# -*- coding: utf-8 -*-
# SPDX-License-Identifier: 0BSD
"""Android sparse image（sparse ext4/EROFS 镜像）识别与转换。

很多 Android 官方 IMG（system.img / vendor.img 等）不是原始的 EROFS，
而是外层套了一层 Android Sparse Image 格式（magic 0xED26FF3A）。
fsck.erofs 只认裸 EROFS，所以这种镜像要先在本地展开成 raw。

sparse 结构（全部小端）::

    header (28 字节)
        u32 magic = 0xED26FF3A
        u16 major_version = 1
        u16 minor_version = 0
        u16 file_hdr_sz = 28
        u16 chunk_hdr_sz = 12
        u32 blk_sz
        u32 total_blks
        u32 total_chunks
        u32 image_checksum
    chunk header (12 字节) + 数据
        u16 chunk_type: 0xCAC1 raw / 0xCAC2 fill / 0xCAC3 don't care / 0xCAC4 crc32
        u16 reserved
        u32 chunk_sz    (占多少个 blk)
        u32 total_sz    (含 chunk header 的总字节数)
"""

import os
import struct
import zlib

SPARSE_MAGIC = 0xED26FF3A
_CHUNK_RAW = 0xCAC1
_CHUNK_FILL = 0xCAC2
_CHUNK_DONT_CARE = 0xCAC3
_CHUNK_CRC32 = 0xCAC4
_HEADER_FMT = "<IHHHHIIII"
_CHUNK_FMT = "<HHII"


def is_sparse(path, read_size=4):
    """只看头 4 字节判断是不是 sparse image。"""
    try:
        with open(path, "rb") as f:
            return struct.unpack("<I", f.read(read_size))[0] == SPARSE_MAGIC
    except Exception:
        return False


def read_header(path):
    """返回 (blk_sz, total_blks, total_chunks, raw_size)。"""
    with open(path, "rb") as f:
        raw = f.read(struct.calcsize(_HEADER_FMT))
    magic, major, minor, file_hdr_sz, chunk_hdr_sz, blk_sz, total_blks, total_chunks, csum = \
        struct.unpack(_HEADER_FMT, raw)
    if magic != SPARSE_MAGIC:
        raise ValueError("不是 Android sparse image（magic=%#x）" % magic)
    if major != 1:
        raise ValueError("不支持的 sparse 主版本 %d" % major)
    return blk_sz, total_blks, total_chunks, blk_sz * total_blks


def raw_size(path):
    """展开后的大小（字节）。"""
    return read_header(path)[3]


def to_raw(path, out_path, on_progress=None, cancel=None, buf_blk=4096):
    """把 sparse image 展开成 raw 文件。

    on_progress(done_blocks, total_blocks) 会被定期调用；
    cancel() 返回 True 时中断并抛出 InterruptedError。
    返回写出的字节数。
    """
    blk_sz, total_blks, total_chunks, out_size = read_header(path)

    done_blks = 0
    written = 0
    with open(path, "rb") as fin, open(out_path, "wb") as fout:
        fin.seek(struct.calcsize(_HEADER_FMT))
        zero_blk = b"\0" * blk_sz
        for _ in range(total_chunks):
            head = fin.read(struct.calcsize(_CHUNK_FMT))
            if len(head) < struct.calcsize(_CHUNK_FMT):
                raise IOError("sparse 文件被截断（chunk header 不完整）")
            ctype, _reserved, chunk_sz, total_sz = struct.unpack(_CHUNK_FMT, head)
            payload = total_sz - struct.calcsize(_CHUNK_FMT)
            if ctype == _CHUNK_RAW:
                left = chunk_sz * blk_sz
                if left != payload:
                    raise IOError("sparse raw chunk 长度异常: %d != %d" % (left, payload))
                while left:
                    piece = fin.read(min(left, 4 << 20))
                    if not piece:
                        raise IOError("sparse 文件被截断（raw 数据不足）")
                    fout.write(piece)
                    left -= len(piece)
                    written += len(piece)
            elif ctype == _CHUNK_FILL:
                fill = fin.read(4)
                if len(fill) < 4:
                    raise IOError("sparse 文件被截断（fill 数据不足）")
                n = chunk_sz * blk_sz
                pad = fill * (blk_sz // 4)
                while n > 0:
                    k = min(n, len(pad))
                    fout.write(pad[:k])
                    n -= k
                    written += k
            elif ctype == _CHUNK_DONT_CARE:
                n = chunk_sz * blk_sz
                while n > 0:
                    k = min(n, len(zero_blk))
                    fout.write(zero_blk[:k])
                    n -= k
                    written += k
            elif ctype == _CHUNK_CRC32:
                fin.seek(payload, os.SEEK_CUR)
            else:
                raise IOError("未知 sparse chunk 类型 %#x" % ctype)

            done_blks += chunk_sz
            if on_progress and (done_blks % 256 == 0 or done_blks >= total_blks):
                on_progress(done_blks, total_blks)
            if cancel and cancel():
                raise InterruptedError("用户取消")

    return written


def raw_to_sparse(src_path, dst_path, blk_sz=4096, on_progress=None, cancel=None):
    """把 raw 文件打包成 Android sparse image（仅用于测试与自检）。"""
    src_size = os.path.getsize(src_path)
    total_blks = (src_size + blk_sz - 1) // blk_sz
    chunks = []          # [(type, chunk_sz, payload_bytes_or_fill)]
    with open(src_path, "rb") as f:
        blk_index = 0
        while blk_index < total_blks:
            data = f.read(blk_sz)
            if len(data) < blk_sz:
                data = data + b"\0" * (blk_sz - len(data))
            # 连续相同 block 归到 fill / don't care
            if data == b"\0" * blk_sz:
                n = 1
                while blk_index + n < total_blks and n < 4096:
                    nxt = f.read(blk_sz)
                    if nxt != b"\0" * blk_sz:
                        f.seek(-len(nxt), os.SEEK_CUR)
                        break
                    n += 1
                chunks.append((_CHUNK_DONT_CARE, n, b""))
                blk_index += n
                continue
            if len(set(data)) == 1 and len(data) % 4 == 0:
                n = 1
                while blk_index + n < total_blks and n < 4096:
                    nxt = f.read(blk_sz)
                    if len(set(nxt)) != 1 or nxt[0] != data[0]:
                        f.seek(-len(nxt), os.SEEK_CUR)
                        break
                    n += 1
                chunks.append((_CHUNK_FILL, n, data[:4]))
                blk_index += n
                continue
            chunks.append((_CHUNK_RAW, 1, data))
            blk_index += 1
            if on_progress and blk_index % 512 == 0:
                on_progress(blk_index, total_blks)
            if cancel and cancel():
                raise InterruptedError("用户取消")

    with open(dst_path, "wb") as f:
        f.write(struct.pack(_HEADER_FMT, SPARSE_MAGIC, 1, 0,
                            struct.calcsize(_HEADER_FMT), struct.calcsize(_CHUNK_FMT),
                            blk_sz, total_blks, len(chunks), 0))
        for ctype, csz, payload in chunks:
            if ctype == _CHUNK_RAW:
                total_sz = struct.calcsize(_CHUNK_FMT) + len(payload)
            elif ctype == _CHUNK_FILL:
                total_sz = struct.calcsize(_CHUNK_FMT) + 4
            else:
                total_sz = struct.calcsize(_CHUNK_FMT)
            f.write(struct.pack(_CHUNK_FMT, ctype, 0, csz, total_sz))
            if payload:
                f.write(payload)
    return dst_path


def crc32_of_raw(path, buf=1 << 20):
    c = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(buf), b""):
            c = zlib.crc32(chunk, c)
    return c & 0xFFFFFFFF
