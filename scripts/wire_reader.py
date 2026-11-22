"""Bounded little-endian readers for the recovered game protocol."""
import struct
from functools import lru_cache

_NUMBER_FORMATS = {}


@lru_cache(maxsize=32)
def _cache_number_format(fmt):
    code = '<' + fmt
    value = (code, struct.calcsize(code))
    _NUMBER_FORMATS[fmt] = value
    return value


class WireError(ValueError):
    pass


class Reader:
    def __init__(self, data):
        self.data = memoryview(data)
        self.pos = 0

    @property
    def remaining(self):
        return len(self.data) - self.pos

    def take(self, size):
        if size < 0 or size > self.remaining:
            raise WireError("Truncated field at offset %d" % self.pos)
        out = bytes(self.data[self.pos:self.pos + size])
        self.pos += size
        return out

    def number(self, fmt):
        # The hot wire decoder calls this millions of times per session; the
        # format code and size are constant per fmt, and unpack_from avoids a
        # bytes copy of the sliced memoryview.
        code, size = _NUMBER_FORMATS.get(fmt) or _cache_number_format(fmt)
        end = self.pos + size
        if end > len(self.data):
            raise WireError("Truncated field at offset %d" % self.pos)
        value = struct.unpack_from(code, self.data, self.pos)[0]
        self.pos = end
        return value

    def u8(self): return self.number('B')
    def u16(self): return self.number('H')
    def u32(self): return self.number('I')
    def u64(self): return self.number('Q')
    def f32(self): return self.number('f')
    def f64(self): return self.number('d')

    def varuint(self, bits=32):
        value = 0
        for shift in range(0, bits, 7):
            part = self.u8()
            value |= (part & 127) << shift
            if not part & 128:
                if value >= (1 << bits):
                    break
                return value
        raise WireError("Variable integer exceeds width")

    def signed(self, bits=64):
        value = self.varuint(bits)
        return (value >> 1) ^ -(value & 1)

    def count(self, limit=65535):
        value = self.varuint()
        if value > limit:
            raise WireError("Collection exceeds limit")
        return value

    def string(self, limit=1024 * 1024):
        return self.take(self.count(limit)).decode('utf-8')

    def finish(self):
        if self.remaining:
            raise WireError("Unexpected trailing data at offset %d" % self.pos)


def decompress_stream(reader, limit=16 * 1024 * 1024):
    compressed, expanded = reader.u32(), reader.u32()
    if compressed > limit or expanded > limit:
        raise WireError("Compressed stream exceeds limit")
    data = reader.take(compressed)
    return Reader(decompress_bytes(data, expanded, limit))


def decompress_bytes(data, expanded, limit=16 * 1024 * 1024):
    """Decode one exact-size Zstandard frame under the caller's byte budget."""
    import zstandard
    if len(data) > limit or not 0 <= expanded <= limit:
        raise WireError("Compressed stream exceeds limit")
    declared = zstandard.frame_content_size(data)
    if declared not in (expanded, zstandard.CONTENTSIZE_UNKNOWN):
        raise WireError("Compression size header mismatch")
    result = zstandard.ZstdDecompressor(max_window_size=limit // 1024).decompress(
        data, max_output_size=max(expanded, 1), allow_extra_data=False)
    if len(result) != expanded:
        raise WireError("Decompressed length mismatch")
    return result
