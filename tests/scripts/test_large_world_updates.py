import json
import struct
import unittest

from game_wire import encode_unsigned
from wire_reader import Reader, WireError
from world_replication import World
from world_snapshot import make_world_delta
from test_world_snapshot import fixture
import test_runtime_background_poll as background


class LegacyReferenceTests(unittest.TestCase):
    def decode(self, data):
        return World({'classes': []}).value(Reader(data), {'type': 60}, [])

    def test_reference_preserves_unsigned_words_and_following_field(self):
        data = struct.pack('<Q', 2**64-1) + encode_unsigned(2**32-1) + struct.pack('<Q', 2**63+9)
        reader = Reader(data + b'\x7f')
        value = World({'classes': []}).value(reader, {'type': 60}, [])
        self.assertEqual(value, {'lr_reference': {'identity': 2**64-1, 'index': 2**32-1, 'type_word': 2**63+9}})
        self.assertEqual(reader.u8(), 127)
        reader.finish()
        for length in range(len(data)):
            with self.subTest(length=length), self.assertRaises(WireError):
                self.decode(data[:length])

    def test_index_overflow_is_rejected(self):
        with self.assertRaises(WireError):
            self.decode(bytes(8) + b'\xff\xff\xff\xff\x10' + bytes(8))


class BoundedDeltaTests(unittest.TestCase):
    def populate(self, count, size=20):
        world, key = fixture()
        start = world.revision
        for i in range(count):
            background.RuntimeBackgroundPollTests.touch_name(world, key, (str(i)+'x'*size).encode())
        return world, start

    def test_chunks_preserve_all_receipts_in_order(self):
        world, start = self.populate(50, 150)
        expected = make_world_delta(world, start)['actions']
        received = []
        cursor = start
        while cursor < world.revision:
            delta = make_world_delta(world, cursor, max_actions=7, max_bytes=1024)
            self.assertLessEqual(len(delta['actions']), 7)
            self.assertLessEqual(len(json.dumps(delta).encode()), 1024)
            self.assertGreater(delta['sequence'], cursor)
            received.extend(delta['actions'])
            cursor = delta['sequence']
        self.assertEqual(received, expected)

    def test_one_oversized_receipt_is_not_dropped(self):
        world, start = self.populate(1, 2000)
        with self.assertRaisesRegex(ValueError, 'One world action'):
            make_world_delta(world, start, max_bytes=1024)

    def test_invalid_budgets(self):
        world, start = self.populate(1)
        for args in ({'max_actions': 0}, {'max_actions': True}, {'max_bytes': 1000}):
            with self.assertRaises(ValueError):
                make_world_delta(world, start, **args)

    def test_foreground_drains_chunks_before_script_and_loaded(self):
        host = background.GatedHost()
        runtime, world, key = background.RuntimeBackgroundPollTests.make_runtime(self, host)
        for i in range(4200):
            background.RuntimeBackgroundPollTests.touch_name(world, key, str(i).encode())
        world.tags.append(13)
        runtime.execute('return 7')
        updates = [call['delta'] for call in host.calls if call['op'] == 'update']
        self.assertEqual([len(d['actions']) for d in updates], [2048, 2048, 104])
        # Tag 13 alone marks the initial replication complete (a streaming server never lets the host catch up first).
        self.assertEqual([d['initial_replication_complete'] for d in updates], [True, True, True])
        self.assertEqual(runtime.revision, world.revision)
        self.assertEqual(host.calls[-1]['op'], 'execute')
        self.assertFalse(runtime._catalog_catchup_needed)

    def test_background_acknowledges_only_first_chunk(self):
        host = background.GatedHost()
        runtime, world, key = background.RuntimeBackgroundPollTests.make_runtime(self, host)
        start = runtime.revision
        for i in range(2200):
            background.RuntimeBackgroundPollTests.touch_name(world, key, str(i).encode())
        runtime.poll_background()
        self.assertTrue(host.finished.wait(2))
        runtime._finish_background(wait=True)
        self.assertEqual(runtime.revision, start+2048)
        self.assertLess(runtime.revision, world.revision)
        runtime.synchronize()
        self.assertEqual(runtime.revision, world.revision)
        updates=[call for call in host.calls if call['op']=='update']
        self.assertEqual([len(call['delta']['actions']) for call in updates], [2048,152])


if __name__ == '__main__':
    unittest.main()
