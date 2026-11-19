"""Container tests use locally authored and compiler-produced fixtures only."""
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

import zstandard

from bytecode_container import MAX_BYTES, _inspector, standardize_opcodes, unpack_container
from local_runtime import HOST, run_bytecode
from login_packets import ticket_hash


def container_fixture(data, declared_size=None, extra=b'', compressed=True):
    size = (len(data) if compressed else 0) if declared_size is None else declared_size
    raw = b'RSB1' + struct.pack('<I', size)
    raw += (zstandard.ZstdCompressor().compress(data) if compressed else data) + extra
    key = ticket_hash(raw, 42).to_bytes(4, 'little')
    return bytes(value ^ ((key[i % 4] + i * 41) & 255) for i, value in enumerate(raw))


class ContainerTests(unittest.TestCase):
    def test_container_roundtrip_and_exact_compressed_length(self):
        data = b'owned local data' * 10
        self.assertEqual(unpack_container(container_fixture(data)), data)
        self.assertEqual(unpack_container(container_fixture(data, compressed=False)), data)
        with self.assertRaises(ValueError):
            unpack_container(container_fixture(data, extra=b'garbage'))

    def test_modules_larger_than_128_kib_unpack(self):
        data = bytes(range(256)) * 1600
        self.assertGreater(len(data), 128 * 1024)
        self.assertEqual(unpack_container(container_fixture(data)), data)
        stored = container_fixture(data[:200 * 1024], compressed=False)
        self.assertGreater(len(stored), 128 * 1024)
        self.assertEqual(unpack_container(stored), data[:200 * 1024])

    def test_checksum_truncation_and_expansion_limits(self):
        encoded = container_fixture(b'owned local fixture')
        for cut in range(len(encoded)):
            with self.subTest(cut=cut), self.assertRaises(ValueError):
                unpack_container(encoded[:cut])
        damaged = bytearray(encoded)
        damaged[-1] ^= 1
        for bad in (bytes(damaged), b'x' * (MAX_BYTES + 1),
                    container_fixture(b'a', MAX_BYTES + 1),
                    container_fixture(b'a', 2)):
            with self.assertRaises(ValueError):
                unpack_container(bad)

    @unittest.skipUnless((HOST.parent / 'luau-source-to-bytecode').is_file(),
                         'build the local fixture compiler')
    def test_only_opcode_header_bytes_change_and_opaque_suffix_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'fixture.luau'
            target = Path(folder) / 'fixture.luac'
            source.write_text('''local a,b=...; local t={sum=a+b}
if a<b then t.sum+=1 end
local function calc(x) return bit32.bxor(x,0x1234) end
return calc(t.sum)''')
            subprocess.run([str(HOST.parent / 'luau-source-to-bytecode'), str(source), str(target)],
                           check=True, capture_output=True, timeout=5)
            trusted = target.read_bytes()
        module, _ = _inspector().inspect(trusted, '1')
        encoded = bytearray(trusted)
        positions = []
        for proto in module['prototypes']:
            for instruction in proto['instructions']:
                pos = proto['code_offset'] + instruction['pc'] * 4
                positions.append(pos)
                encoded[pos] = (instruction['opcode'] * 227) & 255
        # This is a synthetic suffix, preserved but never authenticated/executed.
        suffix = bytes([0xa5]) * 24
        converted, info = standardize_opcodes(bytes(encoded) + suffix, '203')
        self.assertEqual(converted, trusted + suffix)
        self.assertEqual(info['trailer_bytes'], 24)
        self.assertFalse(info['authentication_validated'])
        self.assertFalse(info['execution_safety_verified'])
        converted, _ = standardize_opcodes(unpack_container(container_fixture(bytes(encoded))), '203')
        self.assertEqual(converted, trusted)
        # Execute only this known compiler-produced fixture, without any suffix.
        result = run_bytecode(converted, [2, 5])
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['values'], [8 ^ 0x1234])


if __name__ == '__main__':
    unittest.main()
