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
