"""Path2D curve fidelity against the live Roblox client (2026-11-27).

Ground truth was captured from a real Roblox client (place 109983668079237)
with a 100x100 Frame parent and the concrete 3-point path
``(0,0), (10,0), (10,10)``, plus a 200x150 Frame path with non-zero tangents.
The guard calls GetTangentOnCurve, GetPositionOnCurve, GetPositionOnCurveArcLength,
GetTangentOnCurveArcLength, InsertControlPoint, UpdateControlPoint,
SetControlPoints and reads Path2D.Parent, so all of those results are compared
bit-for-bit (17 significant digits) below.
"""
import unittest
import test_motion_math as motion


@unittest.skipUnless(motion.RUST_HOST.is_file(), "build the persistent worker first")
class Path2DFidelityTests(unittest.TestCase):
    setUp = motion.MotionMathTests.setUp
    execute = motion.MotionMathTests.execute

    def test_three_point_path_curve_queries_match_live_client(self):
        # Every value here is the exact 17-digit result from the live client.
        result = self.execute("""
local sg = Instance.new("ScreenGui")
sg.IgnoreGuiInset = true
local f = Instance.new("Frame")
f.Size = UDim2.new(0, 100, 0, 100)
f.Parent = sg
local p = Instance.new("Path2D")
p.Parent = f
task.wait(0.2)
local function cp(x, y) return Path2DControlPoint.new(UDim2.new(0, x, 0, y)) end
p:SetControlPoints({ cp(0, 0), cp(10, 0), cp(10, 10) })
local function f17(v)
  if typeof(v) == "number" then return string.format("%.17g", v) end
  if typeof(v) == "Vector2" then return string.format("%.17g,%.17g", v.X, v.Y) end
  if typeof(v) == "UDim2" then
    return string.format("%.17g,%d,%.17g,%d", v.X.Scale, v.X.Offset, v.Y.Scale, v.Y.Offset)
  end
  return tostring(v)
end
local out = {}
local function check(name, expected, value)
  local actual = f17(value)
  assert(actual == expected, name .. ": expected " .. expected .. ", got " .. actual)
  out[#out + 1] = name
end
check("GetLength", "20", p:GetLength())
check("GetPositionOnCurve", "0.10000000149011612,0,0,0", p:GetPositionOnCurve(0.5))
check("GetTangentOnCurve", "0,10", p:GetTangentOnCurve(0.5))
check("GetPositionOnCurveArcLength", "0.10000000149011612,0,0.10000000149011612,0",
      p:GetPositionOnCurveArcLength(5))
check("GetTangentOnCurveArcLength", "0,10", p:GetTangentOnCurveArcLength(5))
check("GetMaxControlPoints", "100", p:GetMaxControlPoints())
check("GetControlPoints_n", "3", #p:GetControlPoints())
sg:Destroy()
return table.concat(out, ",")
""")
        self.assertEqual(result["values"][0],
                         ",".join(["GetLength", "GetPositionOnCurve", "GetTangentOnCurve",
                                   "GetPositionOnCurveArcLength", "GetTangentOnCurveArcLength",
                                   "GetMaxControlPoints", "GetControlPoints_n"]))

    def test_tangent_path_curve_queries_match_live_client(self):
        # 200x150 parent, three points with non-zero scale/offset tangents: this
        # exercises the cubic coefficient, adaptive-bisection length and RK4
        # arc-length code paths bit-for-bit.
        result = self.execute("""
local sg = Instance.new("ScreenGui")
sg.IgnoreGuiInset = true
local f = Instance.new("Frame")
f.Size = UDim2.new(0, 200, 0, 150)
f.Parent = sg
local p = Instance.new("Path2D")
p.Parent = f
task.wait(0.2)
local function ud(a, b, c, d) return UDim2.new(a, b, c, d) end
local function cp(pos, lt, rt) return Path2DControlPoint.new(pos, lt, rt) end
p:SetControlPoints({
  cp(ud(0.1, 3, 0.2, 5), ud(0.02, 1, -0.01, 2), ud(0.03, 2, 0.04, 1)),
  cp(ud(0.35, 7, 0.4, 11), ud(-0.05, 3, 0.06, 4), ud(0.07, 5, -0.08, 6)),
  cp(ud(0.8, 13, 0.6, 17), ud(0.09, 7, -0.02, 8), ud(-0.01, 9, 0.03, 10)),
})
local function fvec(v) return string.format("%.17g,%.17g", v.X, v.Y) end
local function fud(v) return string.format("%.17g,%d,%.17g,%d", v.X.Scale, v.X.Offset, v.Y.Scale, v.Y.Offset) end
local out = {}
local function check(name, expected, value)
  local actual = typeof(value) == "Vector2" and fvec(value) or fud(value)
  assert(actual == expected, name .. ": expected " .. expected .. ", got " .. actual)
  out[#out + 1] = name
end
assert(string.format("%.17g", p:GetLength()) == "180.60693359375")
check("pos0", "0.11500000208616257,0,0.23333333432674408,0", p:GetPositionOnCurve(0))
check("tan0", "24,21", p:GetTangentOnCurve(0))
check("pos0.25", "0.25187501311302185,0,0.40333333611488342,0", p:GetPositionOnCurve(0.25))
check("tan0.25", "69.75,58.5", p:GetTangentOnCurve(0.25))
check("pos0.5", "0.38499999046325684,0,0.47333332896232605,0", p:GetPositionOnCurve(0.5))
check("tan0.5", "57,-18", p:GetTangentOnCurve(0.5))
check("pos0.75", "0.70749998092651367,0,0.59083330631256104,0", p:GetPositionOnCurve(0.75))
check("tan0.75", "148.5,62.25", p:GetTangentOnCurve(0.75))
check("pos1", "0.86500000953674316,0,0.71333330869674683,0", p:GetPositionOnCurve(1))
check("tan1", "-75,-15", p:GetTangentOnCurve(1))
check("arcpos0.25", "0.28208497166633606,0,0.43548783659934998,0", p:GetPositionOnCurveArcLength(0.25))
check("arctan0.25", "68.044410705566406,51.194538116455078", p:GetTangentOnCurveArcLength(0.25))
check("arcpos0.5", "0.49062737822532654,0,0.48860448598861694,0", p:GetPositionOnCurveArcLength(0.5))
check("arctan0.5", "134.00460815429688,35.053817749023438", p:GetTangentOnCurveArcLength(0.5))
check("arcpos0.75", "0.70340454578399658,0,0.58855020999908447,0", p:GetPositionOnCurveArcLength(0.75))
check("arctan0.75", "149.207275390625,62.223953247070312", p:GetTangentOnCurveArcLength(0.75))
sg:Destroy()
return out
""")
        self.assertEqual(len(result["values"][0]), 16)

    def test_insert_update_and_error_text_match_live_client(self):
        # On the live client SetControlPoints builds the list, but a successful
        # curve query is what creates the spline; Insert at index 2 therefore
        # reports a spline bounds error while still updating the point list.
        result = self.execute("""
local sg = Instance.new("ScreenGui")
sg.IgnoreGuiInset = true
local f = Instance.new("Frame")
f.Size = UDim2.new(0, 100, 0, 100)
f.Parent = sg
local p = Instance.new("Path2D")
p.Parent = f
task.wait(0.2)
local function cp(x, y) return Path2DControlPoint.new(UDim2.new(0, x, 0, y)) end
p:SetControlPoints({ cp(0, 0), cp(10, 0), cp(10, 10) })
local function check(name, expected, ok, value)
  local actual = ok and tostring(value) or ("ERR:" .. tostring(value))
  assert(actual == expected, name .. ": expected " .. expected .. ", got " .. actual)
end
local function call(name, expected, fn)
  local ok, r = pcall(fn)
  check(name, expected, ok, r)
end
call("InsertControlPoint", "ERR:Spline inserting control point at index 1 access out of bounds",
     function() p:InsertControlPoint(2, cp(5, 5)); return "ok" end)
assert(#p:GetControlPoints() == 4)
assert(string.format("%.17g", p:GetLength()) == "24.142135620117188")
local pos = p:GetPositionOnCurve(0.5)
assert(string.format("%.17g,%.17g", pos.X.Scale, pos.Y.Scale) == "0.075000002980232239,0.02500000037252903")
call("UpdateControlPoint", "ok", function() p:UpdateControlPoint(2, cp(4, 4)); return "ok" end)
assert(string.format("%.17g,%d,%.17g,%d", p:GetControlPoints()[2].Position.X.Scale,
  p:GetControlPoints()[2].Position.X.Offset, p:GetControlPoints()[2].Position.Y.Scale,
  p:GetControlPoints()[2].Position.Y.Offset) == "0,4,0,4")
assert(string.format("%.17g", p:GetLength()) == "22.867956161499023")
call("Insert_bad_index", "ERR:Path2D:InsertControlPoint() at index 99 access out of bounds",
     function() p:InsertControlPoint(99, cp(1, 1)) end)
call("Update_bad_index", "ERR:Path2D:UpdateControlPoint() at index 99 access out of bounds",
     function() p:UpdateControlPoint(99, cp(1, 1)) end)
call("GetPosition_bad_arg", "ERR:Unable to cast string to float",
     function() p:GetPositionOnCurve("x") end)
call("SetControlPoints_bad", "ERR:Variant cast failed",
     function() p:SetControlPoints({ 1 }) end)
call("GetPosition_nil_arg", "ERR:Argument 1 missing or nil",
     function() p:GetPositionOnCurve(nil) end)
sg:Destroy()
return true
""")
        self.assertEqual(result["values"], [True])


if __name__ == "__main__":
    unittest.main()
