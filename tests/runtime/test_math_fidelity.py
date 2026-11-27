"""math.fmod/pow/ldexp argument error order must match real Roblox."""
import unittest
import test_motion_math as motion


@unittest.skipUnless(motion.RUST_HOST.is_file(), "build the persistent worker first")
class MathFidelityTests(unittest.TestCase):
    setUp = motion.MotionMathTests.setUp
    execute = motion.MotionMathTests.execute

    def test_first_argument_error_is_reported_first(self):
        # Real client: fmod() -> "missing argument #1 to 'fmod' (number expected)"
        # Rove previously reported #2 due to C++ argument evaluation order.
        result = self.execute("""
local cases = {
  {'fmod', function() return math.fmod() end},
  {'pow', function() return math.pow() end},
  {'ldexp', function() return math.ldexp() end},
  {'fmod-str', function() return math.fmod('x') end},
  {'pow-str', function() return math.pow('x') end},
  {'ldexp-str', function() return math.ldexp('x') end},
}
for _, c in ipairs(cases) do
  local ok, err = pcall(c[2])
  assert(not ok, c[1] .. ' expected error')
  local s = tostring(err)
  assert(s:find('missing argument #1', 1, true) or s:find('invalid argument #1', 1, true),
         c[1] .. ' wrong arg: ' .. s)
end
return true
""")
        self.assertEqual(result["values"], [True])


if __name__ == "__main__":
    unittest.main()
