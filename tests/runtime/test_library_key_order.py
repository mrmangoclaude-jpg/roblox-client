"""pairs() order of library tables, verified against the real client.

Luraph v15 folds table iteration order into its decryption key. The Vector2 and
CFrame constructor tables have 7 and 12 string keys respectively; their key sets
matched Roblox already but the iteration order did not, which produced a wrong
key and a garbage-decryption anti-tamper spin. The values below are the real
client's order (captured through the executor oracle).
"""
import unittest

import test_motion_math as motion


@unittest.skipUnless(motion.RUST_HOST.is_file(), 'build the persistent worker first')
class LibraryKeyOrderTests(unittest.TestCase):
    setUp = motion.MotionMathTests.setUp
    execute = motion.MotionMathTests.execute

    def _order(self, table):
        return self.execute('''
local out = {}
for k in pairs(%s) do out[#out + 1] = k end
return table.concat(out, ",")
''' % table)['values'][0]

    def test_vector2_library_iteration_order(self):
        self.assertEqual(
            self._order('Vector2'),
            'min,xAxis,zero,max,one,yAxis,new',
        )

    def test_cframe_library_iteration_order(self):
        self.assertEqual(
            self._order('CFrame'),
            'identity,Angles,fromEulerAnglesYXZ,fromRotationBetweenVectors,'
            'lookAlong,fromOrientation,fromMatrix,fromEulerAnglesXYZ,'
            'fromEulerAngles,lookAt,fromAxisAngle,new',
        )
