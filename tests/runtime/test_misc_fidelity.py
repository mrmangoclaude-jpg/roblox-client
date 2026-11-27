"""Off-path constructor/global fidelity against the real Roblox client.

Ground truth was captured on 2026-11-27 from the connected Steal a Brainrot
client with the same normalized per-argument probe used against Rove's
probe_session.exe. Every expectation below is an engine behavior measured on
that client, not a game-specific stub.

Verified matching digests (13 argument sets each):
    BrickColor.new     927308192
    BrickColor.palette 890541123
"""
import unittest

import test_motion_math as motion


@unittest.skipUnless(motion.RUST_HOST.is_file(), "build the persistent worker first")
class MiscFidelityTests(unittest.TestCase):
    setUp = motion.MotionMathTests.setUp
    execute = motion.MotionMathTests.execute

    def test_brickcolor_new_color3_type_errors_use_engine_names(self):
        result = self.execute("""
local cases = {
  {BrickColor.new, Vector2.new(1,2), "Vector2"},
  {BrickColor.new, UDim2.new(1,0,2,0), "UDim2"},
  {BrickColor.new, CFrame.new(1,2,3), "CFrame"},
}
for _, c in ipairs(cases) do
  local ok, err = pcall(c[1], c[2])
  assert(not ok, tostring(c[2]))
  local expected = "invalid argument #1 to 'new' (Color3 expected, got "..c[3]..")"
  assert(tostring(err):find(expected, 1, true), tostring(err))
end
return true
""")
        self.assertEqual(result["values"], [True])

    def test_brickcolor_palette_engine_error_text(self):
        result = self.execute("""
local function check(fn, expected)
  local ok, err = pcall(fn)
  assert(not ok, expected)
  assert(tostring(err):find(expected, 1, true), tostring(err).." ~= "..expected)
end
check(function() return BrickColor.palette() end, "Argument 1 missing or nil")
check(function() return BrickColor.palette(nil) end, "Argument 1 missing or nil")
check(function() return BrickColor.palette(-1) end, "palette index out of bounds (-1)")
check(function() return BrickColor.palette("x") end, "Unable to cast string to int")
check(function() return BrickColor.palette(Vector2.new(1,2)) end, "Unable to cast Vector2 to int")
check(function() return BrickColor.palette(Vector3.new(1,2,3)) end, "Unable to cast Vector3 to int")
check(function() return BrickColor.palette(UDim2.new(1,0,2,0)) end, "Unable to cast UDim2 to int")
check(function() return BrickColor.palette(CFrame.new(1,2,3)) end, "Unable to cast CoordinateFrame to int")
-- Real client coerces booleans and numeric strings to palette indices.
assert(tostring(BrickColor.palette(true)) == "Slime green")
assert(tostring(BrickColor.palette(false)) == "Earth green")
assert(tostring(BrickColor.palette("5")) == "Dark blue")
assert(tostring(BrickColor.palette(1.5)) == "Bright bluish green")
return true
""")
        self.assertEqual(result["values"], [True])

    def test_instance_new_argument_errors_are_raw_engine_errors(self):
        result = self.execute("""
local function raw(fn, expected)
  local ok, err = pcall(fn)
  assert(not ok, expected)
  assert(tostring(err):find(expected, 1, true), tostring(err).." ~= "..expected)
end
raw(function() return Instance.new() end, "missing argument #1 to 'new' (string expected)")
raw(function() return Instance.new(1) end, 'Unable to create an Instance of type "1"')
raw(function() return Instance.new("NotAClass") end, 'Unable to create an Instance of type "NotAClass"')
-- Type errors still carry the standard argument-error prefix.
local ok, err = pcall(function() return Instance.new(true) end)
assert(not ok and tostring(err):find("invalid argument #1 to 'new' (string expected, got boolean)", 1, true), tostring(err))
return true
""")
        self.assertEqual(result["values"], [True])

    def test_font_new_argument_errors_and_enum_tostring(self):
        result = self.execute("""
local function raw(fn, expected)
  local ok, err = pcall(fn)
  assert(not ok, expected)
  assert(tostring(err):find(expected, 1, true), tostring(err).." ~= "..expected)
end
raw(function() return Font.new() end, "missing argument #1 to 'new' (string expected)")
raw(function() return Font.new("x", 2) end, "Invalid value for enum 'FontWeight'")
raw(function() return Font.new("x", Enum.FontWeight.Regular, 2) end, "Invalid value for enum 'FontStyle'")
assert(tostring(Font.new(1)) == "Font { Family = 1, Weight = Regular, Style = Normal }")
assert(tostring(Font.new("x", Enum.FontWeight.Bold, Enum.FontStyle.Italic))
  == "Font { Family = x, Weight = Bold, Style = Italic }")
return true
""")
        self.assertEqual(result["values"], [True])


if __name__ == "__main__":
    unittest.main()
