"""Engine-faithful argument handling that protected scripts probe for."""
import unittest

import test_cframe_transforms as transforms


class EngineArgumentHandlingTests(unittest.TestCase):
    run_script = transforms.CFrameTransformTests.run_script

    def test_vector2_new_ignores_extra_arguments(self):
        self.run_script('''
assert(Vector2.new(1, 2, 3) == Vector2.new(1, 2))
assert(Vector2.new(1, 2, "x", {}, nil, true) == Vector2.new(1, 2))
assert(Vector2.new(0.4422446546745451, 0.94966878328634, 0.1388023259328105) == Vector2.new(0.4422446546745451, 0.94966878328634))
assert(Vector2.new(5) == Vector2.new(5, 0) and Vector2.new() == Vector2.zero)
assert(not pcall(Vector2.new, "a"))
assert(not pcall(Vector2.new, 1, "b", 3))
''')

    def test_workspace_server_time_is_epoch_seconds(self):
        self.run_script('''
local workspace = game:GetService("Workspace")
local now = workspace:GetServerTimeNow()
assert(type(now) == "number" and math.abs(now - os.time()) < 5, now)
assert(workspace:GetServerTimeNow() >= now)
assert(not pcall(workspace.GetServerTimeNow, game))
''')


if __name__ == '__main__':
    unittest.main()
