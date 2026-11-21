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
