"""Path2D control points and curve queries.

The golden test replays a six-point path (158x267) shaped like the one a protected script measures: its
GetLength, 420.553436279, is Studio's own answer, and the remaining lines pin the float32 curve model.
"""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import test_cframe_transforms as transforms

GOLDEN_SOURCE = '''
local out = {}
local function fmt(...) out[#out+1] = string.format(...) end
local sg = Instance.new("ScreenGui")
local f = Instance.new("Frame")
f.Size = UDim2.fromOffset(158, 267)
f.Parent = sg
local p = Instance.new("Path2D")
p.Parent = f
local function cp(px,pxo,py,pyo, lx,lxo,ly,lyo, rx,rxo,ry,ryo)
    return Path2DControlPoint.new(UDim2.new(px,pxo,py,pyo), UDim2.new(lx,lxo,ly,lyo), UDim2.new(rx,rxo,ry,ryo))
end
p:SetControlPoints({
    cp(0,-3,0,-5, 0,0,0,0, 0,-4,0,-6),
    cp(0.5,-10,0,2, 0,-7,0,3, 0.125,-5,0.0625,-7),
    cp(0.5,-2,0.3125,0, 0,-2,0,-8, 0,0,0,0),
    cp(0,0,0.5,1, 0.125,7,0,-8, 0,3,0,-5),
    cp(0,7,0.5,1, 0.0625,4,0,-8, -0.125,6,0.125,3),
    cp(0,-7,0,1, 0,0,0,0, 0,0,0,0),
})
fmt("LEN %.17g", p:GetLength())
local r = p:GetBoundingRect()
fmt("BR %.17g %.17g %.17g %.17g", r.Min.X, r.Min.Y, r.Max.X, r.Max.Y)
for _, t in ipairs({0.2, 0.6, 2/3, 0.4, 2/9, 0.625, 0.875, 4/11, 0.25}) do
    local pos = p:GetPositionOnCurve(t)
    fmt("POS %.17g %.17g %d %.17g %d", t, pos.X.Scale, pos.X.Offset, pos.Y.Scale, pos.Y.Offset)
    local pa = p:GetPositionOnCurveArcLength(t)
    fmt("POSA %.17g %.17g %d %.17g %d", t, pa.X.Scale, pa.X.Offset, pa.Y.Scale, pa.Y.Offset)
    local tan = p:GetTangentOnCurve(t)
    fmt("TAN %.17g %.17g %.17g", t, tan.X, tan.Y)
    local ta = p:GetTangentOnCurveArcLength(t)
    fmt("TANA %.17g %.17g %.17g", t, ta.X, ta.Y)
end
return table.concat(out, "\\n")
'''

GOLDEN = '''LEN 420.55343627929688
BR -8 -7.3583402633666992 78.785285949707031 141.91522216796875
POS 0.20000000000000001 0.43670886754989624 0 0.0074906367808580399 0
POSA 0.20000000000000001 0.47161310911178589 0 0.039899509400129318 0
TAN 0.20000000000000001 44.25 29.0625
TANA 0.20000000000000001 23.876266479492188 73.426254272460938
POS 0.59999999999999998 0 0 0.50374531745910645 0
POSA 0.59999999999999998 0.0094688059762120247 0 0.49780037999153137 0
TAN 0.59999999999999998 9 -15
TANA 0.59999999999999998 17.220550537109375 -13.32380199432373
POS 0.66666666666666663 0.039439782500267029 0 0.48876404762268066 0
POSA 0.66666666666666663 0.0089725060388445854 0 0.52565956115722656 0
TAN 0.66666666666666663 23.208332061767578 -7.999995231628418
TANA 0.66666666666666663 -21.326120376586914 -21.573158264160156
POS 0.40000000000000002 0.48734176158905029 0 0.3125 0
POSA 0.40000000000000002 0.43411862850189209 0 0.3390829861164093 0
TAN 0.40000000000000002 -100.5 86.125
TANA 0.40000000000000002 -96.487197875976562 80.1378173828125
POS 0.22222222222222221 0.46261566877365112 0 0.026520038023591042 0
POSA 0.22222222222222221 0.48430547118186951 0 0.074043996632099152 0
TAN 0.22222222222222221 29.851844787597656 61.03704833984375
TANA 0.22222222222222221 13.431005477905273 93.036727905273438
POS 0.625 0.010956969112157822 0 0.49713981151580811 0
POSA 0.625 0.071477808058261871 0 0.48535579442977905 0
TAN 0.625 17.970703125 -13.078125
TANA 0.625 12.817559242248535 1.5649662017822266
POS 0.875 -0.0089497622102499008 0 0.49729341268539429 0
POSA 0.875 -0.041195880621671677 0 0.20086243748664856 0
TAN 0.875 -17.375 -81.9375
TANA 0.875 -5.1736545562744141 -268.34695434570312
POS 0.36363636363636365 0.48588195443153381 0 0.27792122960090637 0
POSA 0.36363636363636365 0.48535257577896118 0 0.29651004076004028 0
TAN 0.36363636363636365 -2.3305816650390625 73.927696228027344
TANA 0.36363636363636365 0.33524703979492188 55.645500183105469
POS 0.25 0.48222407698631287 0 0.066241659224033356 0
POSA 0.25 0.49089875817298889 0 0.11760587245225906 0
TAN 0.25 15.421875 89.56640625
TANA 0.25 4.9393463134765625 105.40457916259766'''.strip()


class Path2DTests(unittest.TestCase):
    run_script = transforms.CFrameTransformTests.run_script

    def run_text(self, source):
        texts = []
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / 'source.luau').write_text(source)
            (path / 'snapshot.json').write_text(json.dumps(transforms.SNAPSHOT))
            for host in transforms.HOSTS:
                with self.subTest(host=str(host)):
                    completed = subprocess.run(
                        [str(host), '--source', str(path / 'source.luau'),
                         '--world-snapshot', str(path / 'snapshot.json')],
                        capture_output=True, timeout=20)
                    result = json.loads(completed.stdout)
                    self.assertTrue(result['ok'], result)
                    texts.append(result['values'][0])
        return texts

    def test_control_point_datatype(self):
        self.run_script('''
local cp = Path2DControlPoint.new(UDim2.new(0.5,10,0.25,-4), UDim2.fromOffset(1,2), UDim2.fromScale(0.1,0.2))
assert(typeof(cp) == "Path2DControlPoint")
assert(cp.Position == UDim2.new(0.5,10,0.25,-4))
assert(cp.LeftTangent == UDim2.fromOffset(1,2) and cp.RightTangent == UDim2.fromScale(0.1,0.2))
local blank = Path2DControlPoint.new()
assert(blank.Position == UDim2.new() and blank.LeftTangent == UDim2.new() and blank.RightTangent == UDim2.new())
assert(Path2DControlPoint.new(UDim2.new(1,0,1,0)) == Path2DControlPoint.new(UDim2.new(1,0,1,0)))
assert(cp ~= blank)
local ok, err = pcall(Path2DControlPoint.new, 5)
assert(not ok and tostring(err):find("UDim2 expected"), err)
assert(not pcall(Path2DControlPoint.new, UDim2.new(), "x"))
assert(not pcall(function() cp.Position = UDim2.new() end))
assert(not pcall(function() return cp.Nope end))
assert(tostring(cp):find("^Path2DControlPoint"))
''')

    def test_control_point_editing_and_limits(self):
        self.run_script('''
local frame = Instance.new("Frame")
frame.Size = UDim2.fromOffset(400, 100)
local path = Instance.new("Path2D")
path.Parent = frame
assert(path:GetMaxControlPoints() == 100 and path:GetSegmentCount() == 0 and #path:GetControlPoints() == 0)
assert(typeof(path.ControlPointChanged) == "RBXScriptSignal")
local a = Path2DControlPoint.new(UDim2.fromOffset(0, 0))
local b = Path2DControlPoint.new(UDim2.fromOffset(400, 0))
path:SetControlPoints({a, b})
assert(#path:GetControlPoints() == 2 and path:GetSegmentCount() == 1)
path:InsertControlPoint(2, Path2DControlPoint.new(UDim2.fromOffset(200, 50)))
assert(#path:GetControlPoints() == 3 and path:GetSegmentCount() == 2)
path:UpdateControlPoint(2, Path2DControlPoint.new(UDim2.fromOffset(200, 0)))
assert(path:GetControlPoint(2).Position == UDim2.fromOffset(200, 0))
path:RemoveControlPoint(2)
assert(#path:GetControlPoints() == 2 and path:GetControlPoint(2) == b)
assert(not pcall(path.InsertControlPoint, path, 9, a))
assert(not pcall(path.RemoveControlPoint, path, 0))
assert(not pcall(path.UpdateControlPoint, path, 3, a))
assert(not pcall(path.GetControlPoint, path, 3))
assert(not pcall(path.SetControlPoints, path, {1, 2}))
local many = {}
for i = 1, 100 do many[i] = a end
path:SetControlPoints(many)
assert(#path:GetControlPoints() == 100)
many[101] = a
assert(not pcall(path.SetControlPoints, path, many))
assert(not pcall(path.InsertControlPoint, path, 1, a))
''')

    def test_line_curve_queries_and_closed_paths(self):
        self.run_script('''
local frame = Instance.new("Frame")
frame.Size = UDim2.fromOffset(400, 100)
local path = Instance.new("Path2D")
path.Parent = frame
assert(not pcall(path.GetPositionOnCurve, path, 0.5))
path:SetControlPoints({Path2DControlPoint.new(UDim2.fromOffset(0, 0)), Path2DControlPoint.new(UDim2.fromOffset(400, 0))})
assert(path:GetLength() == 400)
assert(path:GetTangentOnCurve(0.5) == Vector2.new(400, 0))
assert(path:GetTangentOnCurveArcLength(0.5) == Vector2.new(400, 0))
assert(path:GetPositionOnCurve(0.25) == UDim2.fromScale(0.25, 0))
assert(path:GetPositionOnCurveArcLength(0.5) == UDim2.fromScale(0.5, 0))
assert(path:GetPositionOnCurve(-3) == UDim2.fromScale(0, 0) and path:GetPositionOnCurve(7) == UDim2.fromScale(1, 0))
assert(not pcall(path.GetPositionOnCurve, path, 0/0))
frame.Size = UDim2.fromOffset(400, 500)
path:SetControlPoints({Path2DControlPoint.new(UDim2.fromOffset(0, 0)), Path2DControlPoint.new(UDim2.fromOffset(300, 0)),
    Path2DControlPoint.new(UDim2.fromOffset(300, 400))})
assert(path:GetSegmentCount() == 2 and path:GetLength() == 700)
path.Closed = true
assert(path:GetSegmentCount() == 3 and path:GetLength() == 1200)
''')

    def test_bounding_rect_pads_by_thickness(self):
        self.run_script('''
local frame = Instance.new("Frame")
frame.Size = UDim2.fromOffset(400, 100)
local path = Instance.new("Path2D")
path.Parent = frame
path:SetControlPoints({Path2DControlPoint.new(UDim2.fromOffset(0, 0)), Path2DControlPoint.new(UDim2.fromOffset(400, 0))})
for _, case in {{0, 0}, {0.5, 0.75}, {1, 1}, {2, 1.5}, {4, 2.5}, {10, 5.5}} do
    path.Thickness = case[1]
    local rect = path:GetBoundingRect()
    local pad = case[2]
    assert(rect.Min == Vector2.new(-pad, -pad) and rect.Max == Vector2.new(400 + pad, pad), tostring(rect))
end
''')

    def test_six_point_path_matches_the_recorded_engine_answers(self):
        for text in self.run_text(GOLDEN_SOURCE):
            self.assertEqual(text.strip(), GOLDEN)


if __name__ == '__main__':
    unittest.main()
