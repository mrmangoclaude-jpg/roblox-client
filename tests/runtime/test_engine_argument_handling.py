"""Engine-faithful argument handling that protected scripts probe for (verified in Roblox Studio)."""
import unittest

import test_cframe_transforms as transforms


class EngineArgumentHandlingTests(unittest.TestCase):
    run_script = transforms.CFrameTransformTests.run_script

    def test_vector2_new_converts_leniently_and_ignores_extra_arguments(self):
        self.run_script('''
assert(Vector2.new(1, 2, 3) == Vector2.new(1, 2))
assert(Vector2.new(1, 2, "x", {}, nil, true) == Vector2.new(1, 2))
assert(Vector2.new(0.4422446546745451, 0.94966878328634, 0.1388023259328105) == Vector2.new(0.4422446546745451, 0.94966878328634))
assert(Vector2.new("1", "2") == Vector2.new(1, 2))
assert(Vector2.new("a") == Vector2.zero and Vector2.new({}) == Vector2.zero and Vector2.new(true) == Vector2.zero)
assert(Vector2.new(nil, 1) == Vector2.new(0, 1) and Vector2.new(5) == Vector2.new(5, 0) and Vector2.new() == Vector2.zero)
local nan = Vector2.new(0/0, 1)
assert(nan.X ~= nan.X and nan.Y == 1)
assert(Vector2.new(math.huge, 1).X == math.huge)
''')

    def test_datatype_metatables_report_the_locked_message(self):
        self.run_script('''
local values = {
    Vector3.new(), Vector2.new(), Vector3int16.new(), Vector2int16.new(), CFrame.new(), Color3.new(), UDim.new(), UDim2.new(),
    Rect.new(0, 0, 1, 1), Ray.new(Vector3.zero, Vector3.one), Region3.new(Vector3.zero, Vector3.one),
    Region3int16.new(Vector3int16.new(), Vector3int16.new()), BrickColor.new("Red"), NumberRange.new(1, 2),
    NumberSequence.new(1), NumberSequenceKeypoint.new(0, 1), ColorSequence.new(Color3.new()),
    ColorSequenceKeypoint.new(0, Color3.new()), TweenInfo.new(), DateTime.now(), Axes.new(), Faces.new(),
    PhysicalProperties.new(1, 1, 1), OverlapParams.new(), RaycastParams.new(), Random.new(1), Path2DControlPoint.new(),
}
for index, value in values do
    assert(getmetatable(value) == "The metatable is locked", index .. " " .. typeof(value) .. " " .. tostring(getmetatable(value)))
end
assert(getmetatable(buffer.create(1)) == nil and getmetatable({}) == nil)
''')

    def test_rect_accepts_the_largest_float(self):
        self.run_script('''
local widest = 3.4028234663852886e38
local rect = Rect.new(-widest, -widest, widest, widest)
assert(rect.Max.X == widest and rect.Min.Y == -widest)
assert(Rect.new(Vector2.new(-widest, 0), Vector2.new(widest, 1)).Max.X == widest)
assert(not pcall(Rect.new, 0, 0, 3.5e38, 1))
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
