"""CFrame/Vector3 results that a protected script's environment battery folds into its key, checked against the live client.

Every expected number below was returned by a real Roblox client (2.747.1486) for exactly these arguments and is the exact value
of a 32-bit float. The values are bit-exact: any rounding or operation-order difference changes the last digit.
"""
import unittest

import test_motion_math as motion

PREAMBLE = '''
local function same(label, frame, ...)
	local got, want = {frame:GetComponents()}, {...}
	for i = 1, #want do
		assert(got[i] == want[i], string.format("%s component %d: got %.17g want %.17g", label, i, got[i], want[i]))
	end
end
local P = Vector3.new(0.51980823278427124, 0.0069598732516169548, 0.050145674496889114)
local T = Vector3.new(1.0893735885620117, 0.23172743618488312, 0.22159186005592346)
local D = Vector3.new(0.5695652961730957, 0.22476756572723389, 0.17144618928432465)
'''


@unittest.skipUnless(motion.RUST_HOST.is_file(), 'build the persistent worker first')
class ClientMathFidelityTests(unittest.TestCase):
    setUp = motion.MotionMathTests.setUp
    execute = motion.MotionMathTests.execute

    def run_lua(self, body):
        self.execute(PREAMBLE + body)

    def test_look_at_and_look_along_round_to_float32(self):
        self.run_lua('''
same("lookAt", CFrame.lookAt(P, T, Vector3.new(0, 1, 0)), P.X, P.Y, P.Z,
	-0.288237065076828, -0.33848324418067932, -0.89573907852172852, 0, 0.93544000387191772, -0.35348549485206604,
	0.95755904912948608, -0.10188762098550797, -0.26962849497795105)
same("lookAlong", CFrame.lookAlong(P, D, Vector3.new(0, 1, 0)), P.X, P.Y, P.Z,
	-0.28823709487915039, -0.33848327398300171, -0.89573907852172852, 0, 0.93544000387191772, -0.35348552465438843,
	0.95755904912948608, -0.10188764333724976, -0.26962852478027344)
''')

    def test_position_look_at_constructor_differs_from_look_at(self):
        # CFrame.new(position, lookAt) normalizes with reciprocal lengths and derives y last (live client, bit for bit).
        self.run_lua('''
same("new(position, lookAt)", CFrame.new(P, T), P.X, P.Y, P.Z,
	-0.28823709487915039, -0.33848327398300171, -0.89573907852172852, 7.4505814851022478e-09, 0.93544012308120728,
	-0.35348549485206604, 0.95755916833877563, -0.10188763588666916, -0.26962849497795105)
local q = CFrame.new(Vector3.new(-30.97917366027832, -25.80569839477539, -46.99174118041992),
	Vector3.new(-3.606553792953491, -5.946888446807861, 34.242713928222656))
assert(string.format("%08x", string.unpack("<I4", string.pack("<f", select(4, q:GetComponents())))) == "bf72990c")
assert(string.format("%08x", string.unpack("<I4", string.pack("<f", select(5, q:GetComponents())))) == "bd939762")
''')

    def test_axis_angle_is_a_single_precision_pipeline(self):
        self.run_lua('''
same("fromAxisAngle", CFrame.fromAxisAngle(Vector3.new(0.89573907852172852, 0.35348552465438843, 0.26962852478027344), 0.94195141839591945),
	0, 0, 0, 0.91860926151275635, -0.087665528059005737, 0.38532033562660217, 0.3484356701374054, 0.63966488838195801,
	-0.68514335155487061, -0.18641242384910583, 0.76363837718963623, 0.61814790964126587)
''')

    def test_euler_angles_with_an_explicit_order_match_angles(self):
        self.run_lua('''
local x, y, z = 0.94195141839591945, 0.1981933654841731, 0.9492041688265882
same("fromEulerAngles XYZ", CFrame.fromEulerAngles(x, y, z, Enum.RotationOrder.XYZ), 0, 0, 0,
	0.57093054056167603, -0.79703789949417114, 0.19689838588237762, 0.57091385126113892, 0.21308411657810211,
	-0.79287618398666382, 0.58999645709991455, 0.56508922576904297, 0.57669621706008911)
same("Angles", CFrame.Angles(x, y, z), 0, 0, 0,
	0.57093054056167603, -0.79703789949417114, 0.19689838588237762, 0.57091385126113892, 0.21308411657810211,
	-0.79287618398666382, 0.58999645709991455, 0.56508922576904297, 0.57669621706008911)
''')

    def test_lerp_interpolates_position_in_single_precision(self):
        self.run_lua('''
same("Lerp", CFrame.new():Lerp(CFrame.new(P), 0.58936314224343977),
	0.30635583400726318, 0.0041018929332494736, 0.029554013162851334, 1, 0, 0, 0, 1, 0, 0, 0, 1)
''')

    def test_rotation_between_perpendicular_unit_vectors_matches_the_engines_rounding(self):
        # The engine's quaternion components land one ulp above 1/sqrt(2), so the matrix is not exactly orthonormal.
        self.run_lua('''
same("fromRotationBetweenVectors", CFrame.fromRotationBetweenVectors(Vector3.new(1, 0, 0), Vector3.new(0, 1, 0)), 0, 0, 0,
	-1.1920928955078125e-07, -1.0000001192092896, 0, 1.0000001192092896, -1.1920928955078125e-07, 0, 0, 0, 1)
''')

    def test_vector3_methods_carry_the_engines_names_and_angle_is_a_float(self):
        self.run_lua('''
local v = Vector3.new(0.8176746964454651, 0.7790513038635254, 0.311459481716156)
for _, name in {"Abs", "Ceil", "Floor", "Sign", "Dot", "Cross", "Angle", "Lerp", "Max", "Min", "FuzzyEq"} do
	assert(debug.info(v[name], "n") == name, name .. " is named " .. tostring(debug.info(v[name], "n")))
end
assert(v:Angle(Vector3.new(0.6199175715446472, 0.9970009922981262, 0.24819017946720123)) == 0.2534259557723999)
assert(v:Dot(Vector3.new(0.6199175715446472, 0.9970009922981262, 0.24819017946720123)) == 1.3609069585800171)
''')

    def test_grapheme_iterator_has_no_debug_name(self):
        self.run_lua('''
local iterator = utf8.graphemes("t\\u{357}", 1, 3)
local name = debug.info(iterator, "n")
assert(name == "" or name == nil, tostring(name))
assert(select(2, iterator()) == 3)
''')


if __name__ == '__main__':
    unittest.main()
