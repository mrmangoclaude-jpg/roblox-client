"""Argument-error text for wrong calls matches the real Roblox client.

Luraph mixes exact error-message text into its stage keys, so the presence or
absence of a function name in `invalid argument #N (...)` is observable.
"""
import unittest

import test_motion_math as motion


@unittest.skipUnless(motion.RUST_HOST.is_file(), 'build the persistent worker first')
class ErrorTextParityTests(unittest.TestCase):
    setUp = motion.MotionMathTests.setUp
    execute = motion.MotionMathTests.execute

    def test_debug_info_without_arguments_omits_function_name(self):
        self.execute('''
local ok, message = pcall(debug.info)
assert(not ok, tostring(message))
assert(message:find("invalid argument #1 (function or level expected)", 1, true), message)
assert(not message:find("to 'info'", 1, true), message)
''')

    def test_random_shuffle_on_frozen_table_uses_engine_message(self):
        self.execute('''
local t = table.freeze({1, 2, 3})
local ok, message = pcall(function() return Random.new(1):Shuffle(t) end)
assert(not ok, tostring(message))
assert(message:find("attempt to modify a readonly table", 1, true), tostring(message))
''')

    def test_invalid_datatype_members_use_engine_message(self):
        self.execute('''
local values = {
    {Vector3.new(1,2,3), "Vector3"}, {Vector2.new(1,2), "Vector2"},
    {CFrame.new(), "CFrame"}, {UDim2.new(0,1,0,2), "UDim2"},
    {UDim.new(0,1), "UDim"}, {Color3.new(), "Color3"},
    {Rect.new(0,0,1,1), "Rect"}, {NumberRange.new(1,2), "NumberRange"},
    {TweenInfo.new(1), "TweenInfo"},
}
for _, pair in ipairs(values) do
    local ok, message = pcall(function() return pair[1].NoSuchMember end)
    assert(not ok, pair[2] .. ": " .. tostring(message))
    assert(message:find("NoSuchMember is not a valid member of " .. pair[2], 1, true),
        pair[2] .. ": " .. tostring(message))
end
''')

    def test_constructors_coerce_bad_arguments_to_zero(self):
        self.execute('''
assert(tostring(Vector3.new("x",1,1)) == "0, 1, 1")
assert(tostring(UDim.new("x",1)) == "0, 1")
assert(tostring(UDim2.new("x",1,1,1)) == "{0, 1}, {1, 1}")
assert(tostring(Color3.new("x",1,1)) == "0, 1, 1")
assert(tostring(Rect.new("x",1,1,1)) == "0, 1, 1, 1")
''')

    def test_immutable_datatype_members_use_engine_message(self):
        self.execute('''
local values = {
    {Vector3.new(1,2,3), "X", "X cannot be assigned to"},
    {Vector2.new(1,2), "X", "X member of Vector2 is read-only and cannot be assigned to"},
    {CFrame.new(), "X", "X member of CFrame is read-only and cannot be assigned to"},
    {UDim2.new(0,1,0,2), "X", "X member of UDim2 is read-only and cannot be assigned to"},
    {Color3.new(), "R", "R member of Color3 is read-only and cannot be assigned to"},
    {NumberRange.new(1,2), "Min", "Min member of NumberRange is read-only and cannot be assigned to"},
    {TweenInfo.new(1), "Time", "Time member of TweenInfo is read-only and cannot be assigned to"},
}
for _, entry in ipairs(values) do
    local ok, message = pcall(function() entry[1][entry[2]] = 5 end)
    assert(not ok, entry[3] .. ": ok")
    assert(message:find(entry[3], 1, true), entry[3] .. ": " .. tostring(message))
end
''')

    def test_vector3_nil_key_omits_function_name(self):
        self.execute('''
local v = Vector3.new(1, 2, 3)
local ok, message = pcall(function() return v[nil] end)
assert(not ok, tostring(message))
assert(message:find("invalid argument #2 (string expected, got nil)", 1, true), message)
assert(not message:find("Vector3.__index", 1, true), message)
''')


if __name__ == '__main__':
    unittest.main()
