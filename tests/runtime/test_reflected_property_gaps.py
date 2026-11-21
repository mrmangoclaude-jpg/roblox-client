"""Engine reflection facts the protocol snapshot may omit."""
import copy
import json
import unittest

import test_motion_math as motion


@unittest.skipUnless(motion.RUST_HOST.is_file(), 'build the persistent worker first')
class ReflectedPropertyTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = copy.deepcopy(motion.SNAPSHOT)

    def test_preferred_input_change_signal_is_a_declared_player_property(self):
        host = motion.PersistentLuauHost(copy.deepcopy(self.snapshot))
        self.addCleanup(host.close)
        result = host.call({'op': 'execute', 'source': '''
local player = game:GetService("Players").LocalPlayer
local ok, signal = pcall(function() return player:GetPropertyChangedSignal("PreferredInput") end)
assert(ok, tostring(signal))
assert(signal ~= nil)
''', 'timeout_ms': 2000})
        self.assertTrue(result['ok'], result.get('error'))

    def test_user_input_service_preferred_input_is_an_enum_item(self):
        host = motion.PersistentLuauHost(copy.deepcopy(self.snapshot))
        self.addCleanup(host.close)
        result = host.call({'op': 'execute', 'source': '''
local value = game:GetService("UserInputService").PreferredInput
assert(typeof(value) == "EnumItem", typeof(value))
assert(tostring(value):find("Enum.PreferredInput.", 1, true), tostring(value))
''', 'timeout_ms': 2000})
        self.assertTrue(result['ok'], result.get('error'))

    def test_billboard_gui_size_defaults(self):
        host = motion.PersistentLuauHost(copy.deepcopy(self.snapshot))
        self.addCleanup(host.close)
        result = host.call({'op': 'execute', 'source': '''
local gui = Instance.new("BillboardGui")
assert(typeof(gui.Size) == "UDim2", typeof(gui.Size))
assert(gui.Size == UDim2.new(0,0,0,0))
assert(typeof(gui.AbsoluteSize) == "Vector2", typeof(gui.AbsoluteSize))
local ok, signal = pcall(function() return gui:GetPropertyChangedSignal("Size") end)
assert(ok and signal ~= nil, tostring(signal))
local ok2 = pcall(function() gui.Size = UDim2.new(0,100,0,50) end)
assert(ok2)
assert(gui.Size == UDim2.new(0,100,0,50))
''', 'timeout_ms': 2000})
        self.assertTrue(result['ok'], result.get('error'))

    def test_camera_type_defaults_to_custom(self):
        host = motion.PersistentLuauHost(copy.deepcopy(self.snapshot))
        self.addCleanup(host.close)
        result = host.call({'op': 'execute', 'source': '''
local camera = game:GetService("Workspace").CurrentCamera
local value = camera.CameraType
assert(typeof(value) == "EnumItem", typeof(value))
assert(tostring(value):find("Enum.CameraType.Custom", 1, true), tostring(value))
''', 'timeout_ms': 2000})
        self.assertTrue(result['ok'], result.get('error'))

    def test_declared_property_without_replicated_value_reads_as_nil(self):
        snapshot = copy.deepcopy(self.snapshot)
        types = snapshot.setdefault('class_property_types', {})
        types.setdefault('Player', {})['DevEnableMouseLock'] = 'boolean'
        host = motion.PersistentLuauHost(snapshot)
        self.addCleanup(host.close)
        result = host.call({'op': 'execute', 'source': '''
local player = game:GetService("Players").LocalPlayer
local ok, value = pcall(function() return player.DevEnableMouseLock end)
assert(ok, tostring(value))
assert(value == nil, tostring(value))
''', 'timeout_ms': 2000})
        self.assertTrue(result['ok'], result.get('error'))

    def test_pivot_accepts_translation_only_cframe(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot.setdefault('nodes', []).append({
            'id': 'probe:model', 'class_name': 'Model', 'name': 'TranslationOnlyModel',
            'parent': self.snapshot['services']['Workspace'],
            'properties': {'WorldPivot': {'$cframe': {'position': [1, 2, 3]}}},
            'origins': {},
        })
        host = motion.PersistentLuauHost(snapshot)
        self.addCleanup(host.close)
        result = host.call({'op': 'execute', 'source': '''
local model = game:GetService("Workspace").TranslationOnlyModel
local ok, pivot = pcall(function() return model:GetPivot() end)
assert(ok, tostring(pivot))
assert(pivot ~= nil)
''', 'timeout_ms': 2000})
        self.assertTrue(result['ok'], result.get('error'))


if __name__ == '__main__':
    unittest.main()
