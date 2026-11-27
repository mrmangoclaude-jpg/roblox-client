"""bit32 / buffer argument handling must match the real Roblox client.

Ground truth captured 2026-11-27 from a live Roblox client (place
109983668079237) and diffed against Rove's offline probe:

  * The only genuine bit32/buffer difference was the argument-validation ORDER
    of ``bit32.lshift`` / ``bit32.rshift``. Because the shift amount was checked
    inline as a second argument to ``b_shift``, the compiler was free to
    validate argument #2 before #1, so a missing/bad first argument reported
    "missing/invalid argument #2" instead of "#1". The engine checks #1 first.
  * Every buffer function (create/fromstring/tostring/len, all read*/write*
    variants, copy and fill) matched exactly in argument order, accepted types
    and error text, so no buffer change is warranted here.

These probes guard both facts so a future compiler/order change is caught.
"""
import unittest

import test_motion_math as motion


@unittest.skipUnless(motion.RUST_HOST.is_file(), "build the persistent worker first")
class BitBufferFidelityTests(unittest.TestCase):
    setUp = motion.MotionMathTests.setUp
    execute = motion.MotionMathTests.execute

    def _error(self, expression):
        """Return the normalized error text for a failing expression."""
        result = self.execute("""
local ok, message = pcall(function() return %s end)
assert(not ok, "expected failure for: %s")
return tostring(message)
""" % (expression, expression))
        self.assertEqual(len(result["values"]), 1, result)
        return result["values"][0]

    def test_shifts_check_first_argument_before_second(self):
        # The crucial regression: a bad argument #1 with a bad argument #2 must
        # still report #1 (C++ argument evaluation order used to report #2).
        for name in ("bit32.lshift", "bit32.rshift"):
            for args in ("", "buffer.create(8)", "buffer.create(8), 'x'",
                         "'abc'", "'abc', 'x'"):
                message = self._error("%s(%s)" % (name, args))
                self.assertIn("argument #1", message,
                              "%s(%s) -> %s" % (name, args, message))
                self.assertNotIn("argument #2", message,
                                 "%s(%s) -> %s" % (name, args, message))

    def test_shifts_report_second_argument_when_first_is_valid(self):
        for name in ("bit32.lshift", "bit32.rshift"):
            for args, expected in (
                ("1", "missing argument #2"),
                ("1, 'x'", "invalid argument #2 to '%s' (number expected, got string)" % name.split(".")[1]),
            ):
                message = self._error("%s(%s)" % (name, args))
                self.assertIn(expected, message,
                              "%s(%s) -> %s" % (name, args, message))

    def test_shift_numeric_results_are_unchanged(self):
        result = self.execute("""
return bit32.lshift(1, 4), bit32.rshift(256, 4),
       bit32.lshift(0xffffffff, 1), bit32.rshift(-1, 1)
""")
        self.assertEqual(result["values"], [16, 16, 0xfffffffe, 0x7fffffff])

    def test_buffer_argument_types_and_order_match_engine(self):
        cases = (
            ("buffer.create(-1)", "invalid argument #1 to 'create' (size)"),
            ("buffer.readu8(-1)", "invalid argument #1 to 'readu8' (buffer expected, got number)"),
            ("buffer.writeu8(buffer.create(8))", "missing argument #2 to 'writeu8' (number expected)"),
            ("buffer.copy(buffer.create(8), 0, 1)",
             "invalid argument #3 to 'copy' (buffer expected, got number)"),
            ("buffer.fill(buffer.create(8), 0)",
             "missing argument #3 to 'fill' (number expected)"),
            ("buffer.len(-1)", "invalid argument #1 to 'len' (buffer expected, got number)"),
        )
        for expression, expected in cases:
            message = self._error(expression)
            self.assertIn(expected, message,
                          "%s -> %s" % (expression, message))

    def test_buffer_read_write_copy_roundtrip(self):
        result = self.execute("""
local b = buffer.create(8)
buffer.writeu8(b, 0, 0x41)
buffer.writeu16(b, 2, 0x4243)
buffer.writei32(b, 4, -7)
local c = buffer.create(8)
buffer.copy(c, 0, b, 0, 8)
return buffer.readu8(c, 0), buffer.readu16(c, 2), buffer.readi32(c, 4), buffer.len(c)
""")
        self.assertEqual(result["values"], [0x41, 0x4243, -7, 8])


if __name__ == "__main__":
    unittest.main()
