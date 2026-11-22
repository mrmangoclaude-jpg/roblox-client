"""Actual device-clock behavior and the failing Animate seed expression."""
import time
import unittest

from persistent_runtime import PersistentLuauHost
from test_persistent_runtime import SNAPSHOT


class EngineClockTests(unittest.TestCase):
    def test_tick_uses_device_epoch_time_and_supports_animation_seed(self):
        host = PersistentLuauHost(SNAPSHOT)
        self.addCleanup(host.close)
        before = time.time()
        result = host.call({'op': 'execute', 'source': '''
local now=tick()
math.randomseed(now)
return now, os.time(), type(math.random()), type(tick)
''', 'timeout_ms': 100})
        after = time.time()
        self.assertTrue(result['ok'], result)
        timestamp, epoch, random_type, clock_type = result['values']
        # Roblox's tick() is epoch seconds in LOCAL time (os.time() plus the
        # host timezone offset), unlike os.time() which stays UTC.
        local = time.localtime()
        offset = -(time.altzone if local.tm_isdst else time.timezone)
        self.assertLessEqual(before + offset - 2, timestamp)
        self.assertLessEqual(timestamp, after + offset + 2)
        self.assertLess(abs((timestamp - epoch) - offset), 2)
        self.assertEqual((random_type, clock_type), ('number', 'function'))


if __name__ == '__main__':
    unittest.main()
