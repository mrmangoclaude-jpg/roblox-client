"""The native property-list decoder must agree with the Python decoder on every input it accepts, and must defer on the rest.

Random byte streams go through World.property_list twice, once with the native module disabled (the reference Python decoder) and
once enabled. Both must either produce the same properties, reader position and deferred shared-string keys, or the native run
must fall back to Python and so produce the identical result or error. Skipped when scripts/_wire_native.pyd is not built
(python scripts/build_native_wire.py).
"""
import collections
import copy
import random
import unittest

import world_replication
import world_snapshot
from wire_reader import Reader, WireError
from world_replication import World

NATIVE = world_replication._native

# Property wire types the Python decoder implements (see World.value).
TYPES = [0, 2, 3, 7, 8, 9, 10, 11, 12, 13, 14, 18, 19, 20, 21, 22, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 40, 41, 44,
         46, 47, 48, 49, 51, 52, 54, 55, 56, 57, 60, 61, 65, 66, 67, 68, 69]


def make_schema():
    properties = [{'name': 'P%d' % t, 'type': t} for t in TYPES]
    return {'classes': [{'name': 'Test', 'properties': list(range(len(properties)))}],
            'properties': properties,
            'names': ['Alpha', 'Beta', 'Gamma'] + ['N%d' % i for i in range(130)],
            'strings': ['rbxassetid://', 'rbxasset://', 'https://x/']}


def random_payload(rng):
    mode = rng.random()
    size = rng.choice([0, 1, 2, 3, 4, 5, 8, 12, 16, 24, 40, 70])
    if mode < 0.35:
        return bytes(rng.randrange(256) for _ in range(size))
    if mode < 0.8:  # small values: valid counts, booleans, short varints
        return bytes(rng.choice([0, 0, 1, 1, 2, 3, 4, 5, 7, 127, 128, 129, 255]) for _ in range(size))
    return bytes(rng.randrange(0x80) if rng.random() < 0.7 else rng.randrange(0x80, 0x100) for _ in range(size))


def decode(data, native, shared=None):
    """Returns ('ok', properties repr, position, sorted deferred) or ('error', exception type)."""
    world_replication._native = native
    try:
        world = World(make_schema())
        if shared:
            world.shared.update(shared)
        reader = Reader(data)
        instance = {'class': 0, 'properties': {}}
        deferred = set()
        try:
            world.property_list(reader, instance, deferred, compressed=bool(data and data[0] & 1))
        except (WireError, IndexError, KeyError, ValueError, TypeError) as error:
            return ('error', type(error).__name__)
        return ('ok', repr(instance['properties']), reader.pos, sorted(deferred))
    finally:
        world_replication._native = NATIVE


@unittest.skipUnless(NATIVE is not None, 'build the native decoder first (python scripts/build_native_wire.py)')
class NativeWireTests(unittest.TestCase):
    def check(self, data, shared=None):
        python = decode(data, None, shared)
        native = decode(data, NATIVE, shared)
        self.assertEqual(native, python, data.hex())
        return python

    def test_every_property_type_matches_python_on_random_streams(self):
        rng = random.Random(20261120)
        accepted = {}
        for index, wire_type in enumerate(TYPES):
            for _ in range(2500):
                data = bytes([index]) + random_payload(rng) + b'\xff'
                outcome = self.check(data)
                if outcome[0] == 'ok':
                    accepted[wire_type] = accepted.get(wire_type, 0) + 1
        # The fuzz must really exercise the decoders, not just agree on errors.
        for wire_type in (7, 9, 10, 11, 12, 13, 14, 19, 20, 27, 29, 31, 34, 41, 44, 49, 51, 57, 60, 61, 68):
            self.assertGreater(accepted.get(wire_type, 0), 10, 'type %d rarely decodes' % wire_type)

    def test_multi_property_lists_and_positions(self):
        rng = random.Random(7)
        for _ in range(4000):
            picked = sorted(rng.sample(range(len(TYPES)), rng.randrange(1, 5)))
            data = b''.join(bytes([i]) + random_payload(rng) for i in picked) + b'\xff' + bytes(rng.randrange(256) for _ in range(3))
            self.check(data)

    def test_shared_strings_known_and_unknown(self):
        known = bytes(range(16))
        stream = bytes([TYPES.index(46)]) + known + bytes([TYPES.index(47)]) + bytes(range(16, 32)) + b'\xff'
        python = self.check(stream, shared={known: b'x'})
        self.assertEqual(python[0], 'ok')
        self.assertEqual(python[3], [bytes(range(16, 32))])

    def test_hand_built_values(self):
        import struct
        cases = {
            11: struct.pack('<f', 0.1),
            12: struct.pack('<d', -2.5),
            19: struct.pack('<fff', 1, 2, 3),
            14: struct.pack('<fifi', 1.5, -2, 2.5, 3),
            44: bytes([0x81, 0x01]),
            7: bytes([0xff, 0xff, 0xff, 0xff, 0x0f]),
            34: bytes([0x80, 0x80, 0x01]),
            35: struct.pack('<I6f', 2, 1, 2, 3, 4, 5, 6),
            48: struct.pack('<q', 1793639017123),
            38: struct.pack('<I5f', 1, 1, 2, 3, 4, 5),
        }
        for wire_type, payload in cases.items():
            outcome = self.check(bytes([TYPES.index(wire_type)]) + payload + b'\xff')
            self.assertEqual(outcome[0], 'ok', wire_type)

    def test_deep_variant_nesting_and_limits_defer(self):
        # 29 = list of variants: count 1, element type 29 again, ... past the depth limit of 16.
        data = bytes([TYPES.index(29)]) + (b'\x01\x1d' * 20) + b'\x00' + b'\xff'
        self.check(data)
        self.check(bytes([TYPES.index(2)]) + bytes([0xff, 0xff, 0xff, 0xff, 0x0f]) + b'\xff')  # byte count over the limit

    def test_copy_tree_matches_deepcopy_and_is_independent(self):
        rng = random.Random(99)

        def build(depth):
            kind = rng.randrange(9 if depth < 4 else 5)
            if kind == 0: return rng.randrange(-2**40, 2**40)
            if kind == 1: return rng.choice([0.5, -0.0, float('inf'), float('nan'), 1e300, 3.25])
            if kind == 2: return bytes(rng.randrange(256) for _ in range(rng.randrange(8)))
            if kind == 3: return rng.choice(['', 'abc', 'caf\u00e9', None, True, False])
            if kind == 4: return rng.randrange(4)
            if kind == 5: return [build(depth + 1) for _ in range(rng.randrange(4))]
            if kind == 6: return tuple(build(depth + 1) for _ in range(rng.randrange(4)))
            if kind == 7: return {rng.choice(['a', 'b', b'k', 7, (1, 2)]): build(depth + 1) for _ in range(rng.randrange(4))}
            return {bytes([rng.randrange(256)]) for _ in range(rng.randrange(4))}

        for _ in range(3000):
            value = build(0)
            copied = NATIVE.copy_tree(value)
            self.assertEqual(repr(copied), repr(copy.deepcopy(value)))
            self.assertEqual(type(copied), type(value))
        original = {'properties': {'Size': [1.0, 2.0, 3.0]}, 'keys': {b'x'}}
        copied = NATIVE.copy_tree(original)
        copied['properties']['Size'].append(4.0)
        copied['keys'].add(b'y')
        self.assertEqual(original, {'properties': {'Size': [1.0, 2.0, 3.0]}, 'keys': {b'x'}})

    def test_copy_tree_defers_for_other_types(self):
        for value in (object(), collections.OrderedDict(a=1), frozenset([1]), [object()], {'a': complex(1, 2)}):
            with self.assertRaises(NATIVE.Fallback):
                NATIVE.copy_tree(value)

    def test_encode_matches_python_on_random_values(self):
        rng = random.Random(4242)
        weird = [float('nan'), float('inf'), float('-inf'), -0.0, 1e300, 0.1]

        def scalar():
            kind = rng.randrange(10)
            if kind == 0: return None
            if kind == 1: return rng.choice([True, False])
            if kind == 2: return rng.randrange(-300, 300)
            if kind == 3: return rng.choice(weird + [rng.random() * 100])
            if kind == 4: return rng.choice(['', 'abc', 'caf\u00e9'])
            if kind == 5: return rng.choice([b'', b'abc', b'caf\xc3\xa9', b'\xff\xfe', b'\xc3'])
            if kind == 6: return (rng.randrange(0, 5), rng.randrange(0, 2**32))
            if kind == 7: return rng.randrange(0, 256)
            if kind == 8: return rng.randrange(2**40, 2**41)
            return rng.random()

        def build(depth):
            kind = rng.randrange(12 if depth < 3 else 4)
            if kind < 4: return scalar()
            if kind == 4: return [scalar() for _ in range(rng.choice([2, 3, 4, 5, 3, 3]))]
            if kind == 5: return tuple(scalar() for _ in range(rng.choice([2, 3, 4])))
            if kind == 6: return [build(depth + 1) for _ in range(rng.randrange(4))]
            if kind == 7: return {rng.choice(['a', 'b', 'position', 'rotation_id']): build(depth + 1) for _ in range(rng.randrange(4))}
            if kind == 8: return {'$remote_variant': {'type': rng.choice([30, 31, 27, 11, 99]), 'value': build(depth + 1)}}
            if kind == 9: return {'position': [rng.random() for _ in range(3)], 'rotation_id': rng.randrange(0, 40), 'packed_rotation': None}
            if kind == 10: return {rng.choice([1, b'k', (1, 2)]): scalar()}
            return [[rng.random() for _ in range(rng.choice([3, 5]))] for _ in range(rng.randrange(3))]

        def run(fn, value, type_id):
            try:
                return ('ok', repr(fn(value, type_id)))
            except Exception as error:  # the Python reference raises ValueError/TypeError/IndexError/...; the types must agree
                return ('error', type(error).__name__)

        types = [None, None, 28, 69, 18, 13, 14, 19, 20, 21, 22, 37, 40, 35, 38, 27, 51, 57, 7, 11, 33]
        accepted = 0
        for _ in range(12000):
            value, type_id = build(0), rng.choice(types)
            reference = run(world_snapshot._encode_python, value, type_id)
            native = run(world_snapshot._encode, value, type_id)
            self.assertEqual(native, reference, (value, type_id))
            accepted += reference[0] == 'ok'
        self.assertGreater(accepted, 3000)


if __name__ == '__main__':
    unittest.main()
