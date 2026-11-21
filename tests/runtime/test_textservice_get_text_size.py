"""TextService:GetTextSize returns a Vector2, as in a real client."""
import unittest

import test_motion_math as motion


@unittest.skipUnless(motion.RUST_HOST.is_file(), 'build the persistent worker first')
class GetTextSizeTests(unittest.TestCase):
    setUp = motion.MotionMathTests.setUp
    execute = motion.MotionMathTests.execute

    def test_get_text_size_returns_vector2(self):
        self.execute('''
local size = game:GetService("TextService"):GetTextSize("hello", 16, Enum.Font.Legacy, Vector2.new(100, 100))
assert(typeof(size) == "Vector2", typeof(size))
assert(size.X > 0 and size.Y > 0, tostring(size))
''')

    def test_get_text_size_handles_multiline_and_empty(self):
        self.execute('''
local svc = game:GetService("TextService")
local empty = svc:GetTextSize("", 16, Enum.Font.Legacy, Vector2.new(100, 100))
assert(empty.X == 0 and empty.Y == 0, tostring(empty))
local two = svc:GetTextSize("a\\nb", 16, Enum.Font.Legacy, Vector2.new(100, 100))
assert(two.Y > empty.Y, tostring(two))
''')


if __name__ == '__main__':
    unittest.main()
