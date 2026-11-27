"""Constructor fidelity for off-path datatypes against a real Roblox client.

Ground truth was captured on 2026-11-27 from the connected Steal a Brainrot
client with the shared 8-argument-set probe ({} {1} {1,2} {-1} {100}
{0.5,0.25} {"x"} {Vector3.new(1,2,3)}). Each assertion below mirrors an
observed real-client result; the runtime fixes make Rove match them exactly.
"""
import unittest

import test_motion_math as motion


@unittest.skipUnless(motion.RUST_HOST.is_file(), 'build the persistent worker first')
class ConstructorFidelity2Tests(unittest.TestCase):
    setUp = motion.MotionMathTests.setUp
    execute = motion.MotionMathTests.execute

    def test_tween_info_accepts_negatives_and_truncates_numeric_enums(self):
        result = self.execute('''
local function text(...) return tostring(TweenInfo.new(...)) end
-- Real client accepts negative Time/DelayTime and coerces raw numbers into
-- enum values by truncation (0.5 -> Linear, 2 -> Back, -1 -> Quad default).
assert(text(-1):find("Time:-1 ", 1, true), text(-1))
assert(text(1, 0.5):find("EasingStyle:Linear", 1, true), text(1, 0.5))
assert(text(1, 2):find("EasingStyle:Back", 1, true), text(1, 2))
assert(text(1, Enum.EasingStyle.Quad):find("EasingStyle:Quad", 1, true))
assert(text(1, Enum.EasingStyle.Quad, Enum.EasingDirection.Out, 0, false, -1)
    :find("DelayTime:-1 ", 1, true))
-- Engine error text for wrong argument types.
local ok, err = pcall(function() return TweenInfo.new("x") end)
assert(not ok and tostring(err):find("TweenInfo.new first argument expects a number for time.", 1, true), tostring(err))
local ok2, err2 = pcall(function() return TweenInfo.new(1, "x") end)
assert(not ok2 and tostring(err2):find("TweenInfo.new second argument expects Enum.EasingStyle input", 1, true), tostring(err2))
local ok3, err3 = pcall(function() return TweenInfo.new(1, Enum.EasingStyle.Spring) end)
assert(not ok3 and tostring(err3):find("does not support Enum.EasingStyle.Spring", 1, true), tostring(err3))
local ok4, err4 = pcall(function() return TweenInfo.new(1, Enum.EasingStyle.Quad, Enum.EasingDirection.Out, "x") end)
assert(not ok4 and tostring(err4):find("TweenInfo.new fourth arg should be a number for RepeatCount.", 1, true), tostring(err4))
local ok5, err5 = pcall(function() return TweenInfo.new(1, Enum.EasingStyle.Quad, Enum.EasingDirection.Out, 0, "x") end)
assert(not ok5 and tostring(err5):find("TweenInfo.new fifth arg should be a boolean for Reverses.", 1, true), tostring(err5))
local ok6, err6 = pcall(function() return TweenInfo.new(1, Enum.EasingStyle.Quad, Enum.EasingDirection.Out, 0, false, "x") end)
assert(not ok6 and tostring(err6):find("TweenInfo.new sixth arg should be a number for DelayTime.", 1, true), tostring(err6))
return true
''')
        self.assertEqual(result['values'], [True])

    def test_number_range_missing_argument_and_invalid_range(self):
        result = self.execute('''
local ok, err = pcall(NumberRange.new)
assert(not ok and tostring(err):find("missing argument #1 to 'new' (number expected)", 1, true), tostring(err))
assert(tostring(NumberRange.new(1)) == "1 1 ", tostring(NumberRange.new(1)))
assert(tostring(NumberRange.new(1, 2)) == "1 2 ", tostring(NumberRange.new(1, 2)))
local ok2, err2 = pcall(function() return NumberRange.new(0.5, 0.25) end)
assert(not ok2 and tostring(err2):find("NumberRange: invalid range", 1, true), tostring(err2))
return true
''')
        self.assertEqual(result['values'], [True])

    def test_color3_from_hsv_arity_error_text(self):
        result = self.execute('''
for _, args in ipairs({{}, {1}, {1,2}, {0.5,0.25}, {"x"}, {Vector3.new(1,2,3)}}) do
    local ok, err = pcall(function() return Color3.fromHSV(table.unpack(args)) end)
    assert(not ok and tostring(err):find("Color3.fromHSV requires three arguments", 1, true),
        tostring(err))
end
return true
''')
        self.assertEqual(result['values'], [True])

    def test_color_sequence_rejects_non_keypoint_arguments(self):
        result = self.execute('''
for _, args in ipairs({{}, {1}, {1,2}, {-1}, {100}, {0.5,0.25}, {"x"}, {Vector3.new(1,2,3)}}) do
    local ok, err = pcall(function() return ColorSequence.new(table.unpack(args)) end)
    assert(not ok and tostring(err):find("ColorSequence.new(): table expected.", 1, true),
        tostring(err))
end
return true
''')
        self.assertEqual(result['values'], [True])

    def test_number_sequence_argument_errors_and_numeric_sequence(self):
        result = self.execute('''
local ok, err = pcall(NumberSequence.new)
assert(not ok and tostring(err):find("NumberSequence.new(): table of NumberSequenceKeypoints expected.", 1, true), tostring(err))
assert(tostring(NumberSequence.new(1)) == "0 1 0 1 1 0 ", tostring(NumberSequence.new(1)))
assert(tostring(NumberSequence.new(0.5, 0.25)) == "0 0.5 0 1 0.25 0 ", tostring(NumberSequence.new(0.5, 0.25)))
for _, args in ipairs({{"x"}, {Vector3.new(1,2,3)}}) do
    local ok2, err2 = pcall(function() return NumberSequence.new(table.unpack(args)) end)
    assert(not ok2 and tostring(err2):find("NumberSequence.new(): table of NumberSequenceKeypoints expected.", 1, true), tostring(err2))
end
return true
''')
        self.assertEqual(result['values'], [True])

    def test_physical_properties_single_argument_default_and_arity(self):
        result = self.execute('''
-- Any single non-material value yields the all-zero "default" value.
assert(tostring(PhysicalProperties.new(1)) == "default", tostring(PhysicalProperties.new(1)))
assert(tostring(PhysicalProperties.new("x")) == "default", tostring(PhysicalProperties.new("x")))
assert(tostring(PhysicalProperties.new(Vector3.new(1,2,3))) == "default")
-- A real Enum.Material selects that material's engineered defaults.
local plastic = PhysicalProperties.new(Enum.Material.Plastic)
assert(math.abs(plastic.Density - 0.7) < 1e-6, tostring(plastic))
assert(math.abs(plastic.Friction - 0.3) < 1e-6, tostring(plastic))
-- Zero and two arguments keep the engine's long arity message.
for _, args in ipairs({{}, {1,2}, {0.5,0.25}}) do
    local ok, err = pcall(function() return PhysicalProperties.new(table.unpack(args)) end)
    assert(not ok and tostring(err):find("Invalid number of arguments:", 1, true), tostring(err))
end
return true
''')
        self.assertEqual(result['values'], [True])

    def test_ray_defaults_absent_components_to_zero_and_errors_on_bad_values(self):
        result = self.execute('''
assert(tostring(Ray.new()) == "{0, 0, 0}, {0, 0, 0}", tostring(Ray.new()))
assert(tostring(Ray.new(Vector3.new(1,2,3))) == "{1, 2, 3}, {0, 0, 0}",
    tostring(Ray.new(Vector3.new(1,2,3))))
local ok, err = pcall(function() return Ray.new(1, 2) end)
assert(not ok and tostring(err):find("invalid argument #1 to 'new' (Vector3 expected, got number)", 1, true), tostring(err))
local ok2, err2 = pcall(function() return Ray.new("x") end)
assert(not ok2 and tostring(err2):find("invalid argument #1 to 'new' (Vector3 expected, got string)", 1, true), tostring(err2))
return true
''')
        self.assertEqual(result['values'], [True])

    def test_rect_arity_and_vector2_argument_errors(self):
        result = self.execute('''
assert(tostring(Rect.new()) == "0, 0, 0, 0", tostring(Rect.new()))
local ok, err = pcall(function() return Rect.new(1,2) end)
assert(not ok and tostring(err):find("invalid argument #1 to 'new' (Vector2 expected, got number)", 1, true), tostring(err))
local ok2, err2 = pcall(function() return Rect.new(1) end)
assert(not ok2 and tostring(err2):find("Invalid number of arguments: 1", 1, true), tostring(err2))
return true
''')
        self.assertEqual(result['values'], [True])

    def test_axes_ignores_non_enum_arguments(self):
        result = self.execute('''
for _, args in ipairs({{}, {1}, {1,2}, {-1}, {100}, {0.5,0.25}, {"x"}, {Vector3.new(1,2,3)}}) do
    assert(tostring(Axes.new(table.unpack(args))) == "", tostring(Axes.new(table.unpack(args))))
end
assert(tostring(Axes.new(Enum.Axis.X)) == "X", tostring(Axes.new(Enum.Axis.X)))
assert(tostring(Axes.new(Enum.Axis.X, Enum.Axis.Y, Enum.Axis.Z)) == "X, Y, Z")
return true
''')
        self.assertEqual(result['values'], [True])


if __name__ == '__main__':
    unittest.main()
