"""Exact-output parity for the string/table/select/pcall/xpcall functions Luraph calls.

Ground truth: a single 72-record probe run in the real Roblox client via the
roblox MCP connector and in the Rove probe session. All records matched byte for
byte except the two that echo an error message: the client renders the source
location as `[string "..."]:N:` while Rove uses `persistent-source:N:`. That
prefix is a chunk-name artifact, so the assertions below strip it and compare
the remaining message exactly.

These functions are on the guard's critical path (byte=60, select=62, pcall=62,
xpcall=61, pack=10, unpack=10, find/char/gsub=7 each), and Luraph mixes exact
error strings into its stage keys.
"""
import unittest

import test_motion_math as motion


@unittest.skipUnless(motion.RUST_HOST.is_file(), 'build the persistent worker first')
class StringTableFidelityTests(unittest.TestCase):
    setUp = motion.MotionMathTests.setUp
    execute = motion.MotionMathTests.execute

    def test_string_library_argument_errors_exact(self):
        self.execute(r'''
local function strip(m) return (tostring(m):gsub("^.-:%d+: ", "")) end
local cases = {
  {function() return string.byte() end, "missing argument #1 to 'byte' (string expected)"},
  {function() return string.byte("x", "y") end, "invalid argument #2 to 'byte' (number expected, got string)"},
  {function() return string.byte(true) end, "invalid argument #1 to 'byte' (string expected, got boolean)"},
  {function() return string.byte(Vector2.new(1,2)) end, "invalid argument #1 to 'byte' (string expected, got Vector2)"},
  {function() return string.char("x") end, "invalid argument #1 to 'char' (number expected, got string)"},
  {function() return string.char(true) end, "invalid argument #1 to 'char' (number expected, got boolean)"},
  {function() return string.find() end, "missing argument #1 to 'find' (string expected)"},
  {function() return string.find(1) end, "missing argument #2 to 'find' (string expected)"},
  {function() return string.find(true) end, "invalid argument #1 to 'find' (string expected, got boolean)"},
  {function() return string.gsub() end, "missing argument #1 to 'gsub' (string expected)"},
  {function() return string.gsub(1) end, "missing argument #2 to 'gsub' (string expected)"},
  {function() return string.gsub(1, 2) end, "missing argument #3 to 'gsub' (string/function/table expected)"},
  {function() return string.gsub(Vector2.new(1,2)) end, "invalid argument #1 to 'gsub' (string expected, got Vector2)"},
}
for i, c in ipairs(cases) do
  local ok, message = pcall(c[1])
  assert(not ok, "case "..i.." unexpectedly succeeded")
  assert(strip(message) == c[2], "case "..i..": "..strip(message).." ~= "..c[2])
end
''')

    def test_string_results_and_control_bytes(self):
        self.execute(r'''
assert(string.byte("x") == 120)
assert(string.byte(1) == 49)
assert(select("#", string.byte(1, 2)) == 0)
local a = string.char()
assert(type(a) == "string" and #a == 0)
local b = string.char(1)
assert(#b == 1 and b:byte(1) == 1)
local c = string.char(1, 2)
assert(#c == 2 and c:byte(1) == 1 and c:byte(2) == 2)
assert(string.find("x", "y") == nil)
assert(string.find(1, 2) == nil)
''')

    def test_table_pack_unpack_and_select_results(self):
        self.execute(r'''
local function strip(m) return (tostring(m):gsub("^.-:%d+: ", "")) end
local p0 = table.pack()
assert(p0.n == 0 and p0[1] == nil)
local p2 = table.pack("x", "y")
assert(p2.n == 2 and p2[1] == "x" and p2[2] == "y")
local pv = table.pack(Vector2.new(1,2))
assert(pv.n == 1 and tostring(pv[1]) == "1, 2")
local ok, e1 = pcall(table.unpack)
assert(not ok and strip(e1) == "missing argument #1 to 'unpack' (table expected)", strip(e1))
local ok2, e2 = pcall(table.unpack, 1)
assert(not ok2 and strip(e2) == "invalid argument #1 to 'unpack' (table expected, got number)", strip(e2))
local ok3, e3 = pcall(table.unpack, Vector2.new(1,2))
assert(not ok3 and strip(e3) == "invalid argument #1 to 'unpack' (table expected, got Vector2)", strip(e3))
local ok4, e4 = pcall(select)
assert(not ok4 and strip(e4) == "missing argument #1 to 'select' (number expected)", strip(e4))
local ok5, e5 = pcall(select, "x")
assert(not ok5 and strip(e5) == "invalid argument #1 to 'select' (number expected, got string)", strip(e5))
assert(select("#", select(1)) == 0)
assert(select(1, 2) == 2)
''')

    def test_pcall_and_xpcall_argument_text(self):
        self.execute(r'''
local function strip(m) return (tostring(m):gsub("^.-:%d+: ", "")) end
local ok, e0 = pcall(pcall)
assert(not ok and strip(e0) == "missing argument #1", strip(e0))
local r1 = table.pack(pcall(1))
assert(r1.n == 2 and r1[1] == false and strip(r1[2]) == "attempt to call a number value")
local rv = table.pack(pcall(Vector2.new(1,2)))
assert(rv.n == 2 and rv[1] == false and strip(rv[2]) == "attempt to call a Vector2 value")
local x0, xe0 = pcall(xpcall)
assert(not x0 and strip(xe0) == "missing argument #2 to 'xpcall' (function expected)", strip(xe0))
local x1, xe1 = pcall(xpcall, 1)
assert(not x1 and strip(xe1) == "missing argument #2 to 'xpcall' (function expected)", strip(xe1))
local x2, xe2 = pcall(xpcall, 1, 2)
assert(not x2 and strip(xe2) == "invalid argument #2 to 'xpcall' (function expected, got number)", strip(xe2))
local xv, xe3 = pcall(xpcall, Vector2.new(1,2))
assert(not xv and strip(xe3) == "missing argument #2 to 'xpcall' (function expected)", strip(xe3))
local xh, xe4 = pcall(xpcall, function() error("BOOM") end, 5)
assert(not xh and strip(xe4) == "invalid argument #2 to 'xpcall' (function expected, got number)", strip(xe4))
''')

    def test_xpcall_handler_message_format(self):
        self.execute(r'''
-- The handler receives the error string with a `<chunk>:<line>: ` prefix.
-- Only that prefix differs between the real client and Rove; the payload is
-- exactly "BOOM", and xpcall returns (false, handler_result).
local got = table.pack(xpcall(function() error("BOOM") end, function(m) return m end))
assert(got.n == 2 and got[1] == false)
local msg = tostring(got[2])
local stripped = msg:gsub("^.-:%d+: ", "")
assert(stripped == "BOOM", msg)
assert(msg:find(": BOOM", 1, true) ~= nil, msg)
local typed = table.pack(xpcall(function() error("BOOM") end, function(m) return type(m) end))
assert(typed[2] == "string")
local pref = table.pack(xpcall(function() error("BOOM") end, function(m) return "H:" .. tostring(m) end))
local prefmsg = tostring(pref[2])
local prefstripped = prefmsg:gsub("^.-:%d+: ", "")
assert(prefmsg:find("H:", 1, true) ~= nil, prefmsg)
assert(prefstripped == "BOOM", prefmsg)
local tbl = table.pack(xpcall(function() error({code=1}) end, function(m) return type(m) end))
assert(tbl[2] == "table")
local multi = table.pack(xpcall(function() return 11, 22 end, function(m) return m end))
assert(multi.n == 3 and multi[1] == true and multi[2] == 11 and multi[3] == 22)
local badfn = table.pack(xpcall(5, function(m) return m end))
assert(badfn.n == 2 and badfn[1] == false)
assert(tostring(badfn[2]):gsub("^.-:%d+: ", "") == "attempt to call a number value", tostring(badfn[2]))
''')


if __name__ == '__main__':
    unittest.main()
