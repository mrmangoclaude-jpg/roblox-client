"""Path2D control points and curve queries, checked against Roblox Studio.

tests/fixtures/path2d_studio holds batteries that were run in Studio, with Studio's answers beside them: argument
conversion and error messages, equality and mutation of control points, the control-point list versus the internal
spline, parent requirements, closed paths and index rounding. The golden test replays a six-point path (158x267)
shaped like the one a protected script measures; its GetLength, 420.553436279, is Studio's own answer, and the
remaining lines pin the float32 curve model.
"""
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import test_cframe_transforms as transforms

STUDIO = Path(__file__).resolve().parents[2] / 'tests/fixtures/path2d_studio'

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


def normalize(line):
    """Drop the script position Studio and Rove put before an error, and the tab layout."""
    line = line.replace(chr(9), ' ')
    line = re.sub(r'^(.*?)(err:)[\w\-. ]+:\d+: ', r'\1\2', line)
    return re.sub(r' +', ' ', line).strip()


class Path2DTests(unittest.TestCase):
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

    def test_studio_batteries_match_line_for_line(self):
        batteries = sorted(STUDIO.glob('*.luau'))
        self.assertGreaterEqual(len(batteries), 6)
        for script in batteries:
            expected = [normalize(line) for line in
                        (STUDIO / (script.stem + '.expected.txt')).read_text().strip().splitlines()]
            for text in self.run_text(script.read_text()):
                with self.subTest(battery=script.stem):
                    self.assertEqual([normalize(line) for line in text.strip().splitlines()], expected)

    def test_six_point_path_matches_the_recorded_engine_answers(self):
        for text in self.run_text(GOLDEN_SOURCE):
            self.assertEqual(text.strip(), GOLDEN)


if __name__ == '__main__':
    unittest.main()
