"""Constructor fidelity against a real Roblox client (2026-11-27 probe).

Ground truth was captured from the connected Steal a Brainrot client for
BrickColor.new/palette, Font.new, Instance.new, Axes.new, Vector2.new and
Vector3.new. Instance.new and the vector constructors already matched; the
cases below cover the observed differences that were fixed in the runtime.
"""
import unittest
import test_motion_math as motion


@unittest.skipUnless(motion.RUST_HOST.is_file(), "build the persistent worker first")
class DatatypeFidelityTests(unittest.TestCase):
    setUp = motion.MotionMathTests.setUp
    execute = motion.MotionMathTests.execute

    def test_brickcolor_new_arity_and_rgb_clamping(self):
        result = self.execute("""
-- Real client: no arguments selects "Really black".
assert(BrickColor.new().Number == 1003, tostring(BrickColor.new()))
-- One, two or three RGB components; out-of-range components clamp to [0,1]
-- and extra components are ignored.
assert(BrickColor.new(1, 2).Number == 1009, tostring(BrickColor.new(1, 2)))
assert(BrickColor.new(0.5, 0.25).Number == 365, tostring(BrickColor.new(0.5, 0.25)))
assert(BrickColor.new(1, 2, 3).Number == 1001, tostring(BrickColor.new(1, 2, 3)))
assert(BrickColor.new(1, 2, 3, 4).Number == 1001, tostring(BrickColor.new(1, 2, 3, 4)))
assert(BrickColor.new(-1, 2).Number == 1020, tostring(BrickColor.new(-1, 2)))
assert(BrickColor.new(2, -1).Number == 1004, tostring(BrickColor.new(2, -1)))
assert(BrickColor.new("White", 2).Number == 1020, tostring(BrickColor.new("White", 2)))
return true
""")
        self.assertEqual(result["values"], [True])

    def test_font_new_error_text_family_coercion_and_tostring(self):
        result = self.execute("""
local ok, err = pcall(Font.new)
assert(not ok and tostring(err):find("missing argument #1 to 'new' (string expected)", 1, true), tostring(err))
local ok2, err2 = pcall(Font.new, nil)
assert(not ok2 and tostring(err2):find("missing argument #1 to 'new' (string expected)", 1, true), tostring(err2))
-- Numeric families are coerced to strings by the engine.
assert(tostring(Font.new(1)) == "Font { Family = 1, Weight = Regular, Style = Normal }", tostring(Font.new(1)))
-- Enum arguments must be real EnumItems; raw numbers get the engine error.
local ok3, err3 = pcall(Font.new, "x", 2)
assert(not ok3 and tostring(err3):find("Invalid value for enum 'FontWeight'", 1, true), tostring(err3))
local ok4, err4 = pcall(Font.new, "x", Enum.FontWeight.Regular, 2)
assert(not ok4 and tostring(err4):find("Invalid value for enum 'FontStyle'", 1, true), tostring(err4))
-- tostring renders enum names, not their numeric values.
assert(tostring(Font.new("x")) == "Font { Family = x, Weight = Regular, Style = Normal }", tostring(Font.new("x")))
assert(tostring(Font.new("x", Enum.FontWeight.Bold, Enum.FontStyle.Italic))
    == "Font { Family = x, Weight = Bold, Style = Italic }")
return true
""")
        self.assertEqual(result["values"], [True])

    def test_axes_new_ignores_unsupported_and_extra_arguments(self):
        result = self.execute("""
assert(tostring(Axes.new(1)) == "", tostring(Axes.new(1)))
assert(tostring(Axes.new("x")) == "", tostring(Axes.new("x")))
assert(tostring(Axes.new(true)) == "", tostring(Axes.new(true)))
assert(tostring(Axes.new(Enum.Axis.X, 0, Enum.Axis.Y)) == "X, Y",
    tostring(Axes.new(Enum.Axis.X, 0, Enum.Axis.Y)))
local many = {}
for i = 1, 8 do many[i] = Enum.Axis.X end
assert(tostring(Axes.new(table.unpack(many))) == "X", tostring(Axes.new(table.unpack(many))))
return true
""")
        self.assertEqual(result["values"], [True])


if __name__ == "__main__":
    unittest.main()
