"""ContentProvider:PreloadAsync is callable and reports asset status."""
import unittest

import test_motion_math as motion


@unittest.skipUnless(motion.RUST_HOST.is_file(), 'build the persistent worker first')
class ContentProviderTests(unittest.TestCase):
    setUp = motion.MotionMathTests.setUp
    execute = motion.MotionMathTests.execute

    def test_preload_async_calls_status_callback(self):
        self.execute('''
local seen = {}
game:GetService("ContentProvider"):PreloadAsync({"rbxassetid://1", "rbxassetid://2"},
  function(asset, status) seen[#seen+1] = asset .. "=" .. tostring(status) end)
assert(#seen == 2)
''')


if __name__ == '__main__':
    unittest.main()
