"""CFrame constructor error text must match the real Roblox client."""
import unittest
import test_motion_math as motion


@unittest.skipUnless(motion.RUST_HOST.is_file(), "build the persistent worker first")
class CFrameErrorTextTests(unittest.TestCase):
    setUp = motion.MotionMathTests.setUp
    execute = motion.MotionMathTests.execute

    def test_euler_missing_argument_text(self):
        # Live client: CFrame.fromEulerAnglesXYZ() -> "Argument 1 missing or nil"
        result = self.execute("""
local ok, err = pcall(function() return CFrame.fromEulerAnglesXYZ() end)
assert(not ok, 'expected error')
assert(tostring(err):find('Argument 1 missing or nil', 1, true), tostring(err))
local ok2, err2 = pcall(function() return CFrame.fromEulerAnglesXYZ(1) end)
assert(not ok2, 'expected error')
assert(tostring(err2):find('Argument 2 missing or nil', 1, true), tostring(err2))
return true
""")
        self.assertEqual(result["values"], [True])

    def test_lookat_argument_text(self):
        # Live client: CFrame.lookAt() -> "Argument 1 missing or nil"
        #             CFrame.lookAt(1) -> "Vector3 expected"
        result = self.execute("""
local ok, err = pcall(function() return CFrame.lookAt() end)
assert(not ok, 'expected error')
assert(tostring(err):find('Argument 1 missing or nil', 1, true), tostring(err))
local ok2, err2 = pcall(function() return CFrame.lookAt(1) end)
assert(not ok2, 'expected error')
assert(tostring(err2):find('Vector3 expected', 1, true), tostring(err2))
return true
""")
        self.assertEqual(result["values"], [True])


if __name__ == "__main__":
    unittest.main()
