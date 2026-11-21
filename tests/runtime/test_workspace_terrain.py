"""Workspace.Terrain is readable even when the server did not replicate it."""
import unittest

import test_motion_math as motion


@unittest.skipUnless(motion.RUST_HOST.is_file(), 'build the persistent worker first')
class WorkspaceTerrainTests(unittest.TestCase):
    setUp = motion.MotionMathTests.setUp
    execute = motion.MotionMathTests.execute

    def test_terrain_is_a_workspace_child(self):
        self.execute('''
local t = workspace.Terrain
assert(t and typeof(t) == "Instance", tostring(t))
assert(t.ClassName == "Terrain", t.ClassName)
assert(t.Parent == workspace, tostring(t.Parent))
''')


if __name__ == '__main__':
    unittest.main()
