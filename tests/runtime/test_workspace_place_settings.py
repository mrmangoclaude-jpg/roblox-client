"""Workspace place settings that are not replicated are still readable, as in Roblox."""
import unittest

import test_motion_math as motion


@unittest.skipUnless(motion.RUST_HOST.is_file(), 'build the persistent worker first')
class WorkspacePlaceSettingsTests(unittest.TestCase):
    setUp = motion.MotionMathTests.setUp
    execute = motion.MotionMathTests.execute

    def test_workspace_streaming_and_filtering_flags_are_readable(self):
        self.execute('''
assert(workspace.StreamingEnabled == true, "StreamingEnabled")
assert(workspace.FilteringEnabled == true, "FilteringEnabled")
''')

    def test_replicated_workspace_property_still_wins(self):
        self.execute('''
assert(workspace.Gravity == 196.2, workspace.Gravity)
''')
