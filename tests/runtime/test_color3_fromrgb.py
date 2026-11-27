"""Color3.fromRGB argument handling must match the real Roblox client."""
import unittest
import test_motion_math as motion


@unittest.skipUnless(motion.RUST_HOST.is_file(), "build the persistent worker first")
class Color3FromRgbTests(unittest.TestCase):
    setUp = motion.MotionMathTests.setUp
    execute = motion.MotionMathTests.execute

    def test_fromrgb_accepts_one_or_two_components(self):
        # Ground truth from a live Roblox client (2026-11-27):
        #   fromRGB(1)     -> 0.00392157, 0, 0
        #   fromRGB(1, 2)  -> 0.00392157, 0.00784314, 0
        result = self.execute("""
local one = Color3.fromRGB(1)
local two = Color3.fromRGB(1, 2)
assert(math.abs(one.R - 1/255) < 1e-6, tostring(one))
assert(one.G == 0 and one.B == 0, tostring(one))
assert(math.abs(two.R - 1/255) < 1e-6, tostring(two))
assert(math.abs(two.G - 2/255) < 1e-6, tostring(two))
assert(two.B == 0, tostring(two))
local three = Color3.fromRGB(1, 2, 3)
assert(math.abs(three.B - 3/255) < 1e-6, tostring(three))
local none = Color3.fromRGB()
assert(none.R == 0 and none.G == 0 and none.B == 0, tostring(none))
return true
""")
        self.assertEqual(result["values"], [True])


if __name__ == "__main__":
    unittest.main()
