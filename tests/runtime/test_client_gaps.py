"""Engine members that real client scripts reach for during startup and that used to be missing."""
import unittest

import test_motion_math as motion


@unittest.skipUnless(motion.RUST_HOST.is_file(), 'build the persistent worker first')
class ClientGapTests(unittest.TestCase):
    setUp = motion.MotionMathTests.setUp
    execute = motion.MotionMathTests.execute

    def test_enum_catalog_covers_studio_enums_with_studio_values(self):
        self.execute('''
assert(Enum.SurfaceGuiSizingMode.FixedSize.Value==0 and Enum.SurfaceGuiSizingMode.PixelsPerStud.Value==1)
assert(Enum.SurfaceGuiSizingMode:FromName("FixedSize")==Enum.SurfaceGuiSizingMode.FixedSize)
assert(Enum.AudioCaptureMode~=nil and #Enum:GetEnums()>=600)
assert(not pcall(function()return Enum.NotAnEnum end))
''')

    def test_part_type_and_easing_style_match_the_clients_item_lists(self):
        # Hand-written enums that a protected script enumerates; the live client (and Studio) have these items and values.
        self.execute('''
local function items(enum) local t = {} for _, item in enum:GetEnumItems() do t[#t + 1] = item.Name .. "=" .. item.Value end return table.concat(t, ",") end
assert(items(Enum.PartType) == "Ball=0,Block=1,Cylinder=2,Wedge=3,CornerWedge=4,Capsule=5", items(Enum.PartType))
assert(items(Enum.EasingStyle) == "Linear=0,Sine=1,Back=2,Quad=3,Quart=4,Quint=5,Bounce=6,Elastic=7,Exponential=8,Circular=9,Cubic=10,Bezier=11,Spring=12", items(Enum.EasingStyle))
assert(Enum.PartType:FromValue(5) == Enum.PartType.Capsule and Enum.EasingStyle:FromName("Spring") == Enum.EasingStyle.Spring)
local info = TweenInfo.new(1, Enum.EasingStyle.Bezier)
assert(info.EasingStyle == Enum.EasingStyle.Bezier)
local part = Instance.new("Part")
part.Shape = Enum.PartType.Capsule
assert(part.Shape == Enum.PartType.Capsule)
''')

    def test_reflection_service_and_player_scripts_registration(self):
        self.execute('''
assert(game:GetService("ReflectionService").ClassName=="ReflectionService")
local scripts=game:GetService("Players").LocalPlayer:WaitForChild("PlayerScripts")
scripts:RegisterTouchCameraMovementMode(Enum.DevTouchCameraMovementMode.Classic)
scripts:RegisterComputerMovementMode(Enum.DevComputerMovementMode.KeyboardMouse)
scripts:ClearTouchCameraMovementModes()
assert(not pcall(scripts.RegisterTouchCameraMovementMode,scripts))
''')

    def test_reflected_properties_get_change_signals_and_unknown_ones_are_rejected(self):
        self.execute('''
local gui=Instance.new("SurfaceGui")
assert(typeof(gui:GetPropertyChangedSignal("Enabled"))=="RBXScriptSignal")
local ok,message=pcall(gui.GetPropertyChangedSignal,gui,"NotAProperty")
assert(not ok and string.find(message,"NotAProperty is not a valid property name",1,true))
''')


if __name__ == '__main__':
    unittest.main()
