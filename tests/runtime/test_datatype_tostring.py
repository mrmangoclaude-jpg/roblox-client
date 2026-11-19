"""Datatype tostring formats verified bit-exact against Roblox Studio.

The Luraph v15 environment probe hashes tostring() of datatype values into its
stage key; a divergent rendering produces a wrong key and an anti-tamper spin.
TweenInfo/Ray/PhysicalProperties render at %.9g while Vector3 uses the VM's
full shortest-round-trip form -- these are distinct conventions.
"""
import unittest

import test_motion_math as motion


@unittest.skipUnless(motion.RUST_HOST.is_file(), 'build the persistent worker first')
class DatatypeTostringTests(unittest.TestCase):
    setUp = motion.MotionMathTests.setUp
    execute = motion.MotionMathTests.execute

    def test_tweeninfo_renders_the_full_descriptor(self):
        self.execute('''
assert(tostring(TweenInfo.new(1)) ==
    "Time:1 DelayTime:0 RepeatCount:0 Reverses:False EasingDirection:Out EasingStyle:Quad")
assert(tostring(TweenInfo.new(0.5, Enum.EasingStyle.Linear, Enum.EasingDirection.InOut, 2, true, 0.25)) ==
    "Time:0.5 DelayTime:0.25 RepeatCount:2 Reverses:True EasingDirection:InOut EasingStyle:Linear")
''')

    def test_ray_uses_nine_significant_digits_not_vector3_precision(self):
        self.execute('''
assert(tostring(Ray.new(Vector3.new(0, 0, 0), Vector3.new(1, 1, 1))) == "{0, 0, 0}, {1, 1, 1}")
assert(tostring(Ray.new(Vector3.new(1.5, -2.25, 0), Vector3.new(0.1, 0.2, 0.3))) ==
    "{1.5, -2.25, 0}, {0.100000001, 0.200000003, 0.300000012}")
''')

    def test_physical_properties_uses_nine_significant_digits(self):
        self.execute('''
assert(tostring(PhysicalProperties.new(1, 0.3, 0.5)) == "1, 0.300000012, 0.5, 1, 1, 1")
assert(tostring(PhysicalProperties.new(0.1, 0.2, 0.3)) ==
    "0.100000001, 0.200000003, 0.300000012, 1, 1, 1")
''')

    def test_vector3_keeps_full_shortest_round_trip_precision(self):
        self.execute('''
assert(tostring(Vector3.new(1, 2, 3)) == "1, 2, 3")
assert(tostring(Vector3.new(0.1, 0.2, 0.3)) ==
    "0.10000000149011612, 0.20000000298023224, 0.30000001192092896")
''')