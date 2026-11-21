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
