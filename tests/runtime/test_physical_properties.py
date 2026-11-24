"""Authored Luau checks for the numeric PhysicalProperties value subset."""
import copy
import json
import os
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import local_runtime
import persistent_runtime
if os.environ.get("LUAU_TEST_HOST"):
    local_runtime.RUST_HOST = Path(os.environ["LUAU_TEST_HOST"])
    if not local_runtime.RUST_HOST.is_file():
        raise RuntimeError("LUAU_TEST_HOST must point to a completed build")
    persistent_runtime.RUST_HOST = local_runtime.RUST_HOST
SNAPSHOT = json.loads((ROOT / "tests/fixtures/world_snapshot.json").read_text())


def snapshot_with_received_physical_properties(components):
    snapshot = copy.deepcopy(SNAPSHOT)
    root = next(node for node in snapshot["nodes"] if node["id"] == "scope:root-1")
    root["properties"]["CustomPhysicalProperties"] = components
    root.setdefault("origins", {})["CustomPhysicalProperties"] = "received"
    return snapshot


def f32(value):
    import struct
    return struct.unpack("f", struct.pack("f", value))[0]


@unittest.skipUnless(local_runtime.RUST_HOST.is_file(), "build the Rust host with PhysicalProperties first")
class PhysicalPropertiesTests(unittest.TestCase):
    def setUp(self):
        self.host = persistent_runtime.PersistentLuauHost(copy.deepcopy(SNAPSHOT))
        self.addCleanup(self.host.close)

    def execute(self, source):
        result = self.host.call({"op": "execute", "source": source, "timeout_ms": 1000})
        mutations = list(result.get("mutations", []))
        if result.get("completed"):
            result["mutations"] = mutations
        else:
            job_id = result.get("job_id")
            deadline = time.monotonic() + 3
            while type(job_id) is int and time.monotonic() < deadline:
                poll = self.host.call({"op": "poll", "timeout_ms": 100})
                mutations.extend(poll.get("mutations", []))
                match = next((job for job in poll.get("completed_jobs", [])
                              if job.get("job_id") == job_id), None)
                if match is not None:
                    result = match
                    result["mutations"] = mutations + list(result.get("mutations", []))
                    break
            else:
                result["mutations"] = mutations
        self.assertTrue(result.get("ok"), result)
        self.assertFalse(result.get("task_errors"), result)
        return result

    def test_numeric_overloads_fields_type_and_immutability(self):
        result = self.execute('''
local three=PhysicalProperties.new(.7,.3,.5)
local five=PhysicalProperties.new(.7,.3,.5,1,1)
local six=PhysicalProperties.new(.7,.3,.5,1,1,.25)
assert(typeof(three)=="PhysicalProperties")
local function near(a,b)return math.abs(a-b)<1e-6 end
assert(near(three.Density,.7) and near(three.Friction,.3) and near(three.Elasticity,.5))
assert(three.FrictionWeight==1 and three.ElasticityWeight==1)
assert(three.AcousticAbsorption==1)
assert(three==five and six~=five)
assert(six.AcousticAbsorption==.25)
for _,key in ipairs({"Density","Friction","Elasticity","FrictionWeight","ElasticityWeight","AcousticAbsorption"}) do
    assert(not pcall(function()six[key]=1 end),key)
end
return three.Density,three.Friction,three.Elasticity,
       three.FrictionWeight,three.ElasticityWeight,three.AcousticAbsorption,
       six.AcousticAbsorption
''')
        self.assertEqual(result["values"], [f32(.7), f32(.3), f32(.5), 1, 1, 1, .25])

    def test_values_clamp_to_documented_engine_ranges(self):
        result = self.execute('''
local p=PhysicalProperties.new(-10,3,4,101,-1,2)
return p.Density,p.Friction,p.Elasticity,p.FrictionWeight,p.ElasticityWeight,p.AcousticAbsorption
''')
        self.assertEqual(result["values"], [f32(.0001), 2, 1, 100, 0, 1])

    def test_nonfinite_and_incomplete_inputs_are_rejected(self):
        result = self.execute('''
local short=pcall(function()PhysicalProperties.new(.7,.3)end)
local long=pcall(function()PhysicalProperties.new(.7,.3,.5,1,1,.2,.1)end)
local nan=pcall(function()PhysicalProperties.new(0/0,.3,.5)end)
local infinite=pcall(function()PhysicalProperties.new(.7,.3,math.huge)end)
return short,long,nan,infinite
''')
        self.assertEqual(result["values"], [False, False, False, False])

    def test_values_round_trip_through_bindable_event(self):
        result = self.execute('''
local event=Instance.new("BindableEvent")
local expected=PhysicalProperties.new(2.2,.4,.8,30,40,.6)
local received=nil
event.Event:Connect(function(value)received=value end)
event:Fire(expected)
task.wait()
assert(received==expected and typeof(received)=="PhysicalProperties")
return received.Density,received.Friction,received.Elasticity,
       received.FrictionWeight,received.ElasticityWeight,received.AcousticAbsorption
''')
        self.assertEqual(result["values"], [f32(2.2), f32(.4), f32(.8), 30, 40, f32(.6)])


    def test_custom_physical_properties_assignment_read_reset_and_clone(self):
        result = self.execute('''
local part=Instance.new("Part",workspace)
local value=PhysicalProperties.new(2.2,.4,.8,30,40,.6)
part.CustomPhysicalProperties=value
assert(part.CustomPhysicalProperties==value)
local clone=part:Clone()
assert(clone.CustomPhysicalProperties==value)
part.CustomPhysicalProperties=nil
return part.CustomPhysicalProperties==nil,clone.CustomPhysicalProperties.Density,
       clone.CustomPhysicalProperties.FrictionWeight
''')
        self.assertEqual(result["values"], [True, f32(2.2), 30])
        assignments = [item for item in result["mutations"]
                       if item.get("kind") == "set" and item.get("property") == "CustomPhysicalProperties"]
        self.assertEqual(len(assignments), 2)
        self.assertEqual(assignments[0]["value"]["$physical_properties"],
                         [f32(2.2), f32(.4), f32(.8), 30, 40, f32(.6)])
        self.assertIsNone(assignments[1]["value"])


    def test_received_five_and_six_component_properties_and_nil(self):
        cases = [
            ([0.7, 0.3, 0.5, 1.0, 1.0], [f32(.7), f32(.3), f32(.5), 1, 1, 0]),
            ([0.7, 0.3, 0.5, 4.0, 5.0, 0.25], [f32(.7), f32(.3), f32(.5), 4, 5, .25]),
        ]
        for raw, expected in cases:
            with self.subTest(component_count=len(raw)):
                host = persistent_runtime.PersistentLuauHost(
                    snapshot_with_received_physical_properties(raw))
                self.addCleanup(host.close)
                result = host.call({"op": "execute", "source": '''
local root=game:GetService("Players").LocalPlayer.Character:FindFirstChild("HumanoidRootPart")
local value=root.CustomPhysicalProperties
return typeof(value),value.Density,value.Friction,value.Elasticity,
       value.FrictionWeight,value.ElasticityWeight,value.AcousticAbsorption
''', "timeout_ms": 1000})
                self.assertTrue(result.get("ok"), result)
                self.assertEqual(result["values"], ["PhysicalProperties", *expected])

        host = persistent_runtime.PersistentLuauHost(
            snapshot_with_received_physical_properties(None))
        self.addCleanup(host.close)
        result = host.call({"op": "execute", "source": '''
local root=game:GetService("Players").LocalPlayer.Character:FindFirstChild("HumanoidRootPart")
return root.CustomPhysicalProperties==nil
''', "timeout_ms": 1000})
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(result["values"], [True])

    def test_missing_received_property_is_not_guessed_as_nil(self):
        host = persistent_runtime.PersistentLuauHost(copy.deepcopy(SNAPSHOT))
        self.addCleanup(host.close)
        result = host.call({"op": "execute", "source": '''
local root=game:GetService("Players").LocalPlayer.Character:FindFirstChild("HumanoidRootPart")
local ok=pcall(function()return root.CustomPhysicalProperties end)
return ok
''', "timeout_ms": 1000})
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(result["values"], [False])

    def test_local_property_assignment_rejects_non_physical_value(self):
        result = self.execute('''
local part=Instance.new("Part",workspace)
local ok=pcall(function()part.CustomPhysicalProperties="not physical properties"end)
return ok,part.CustomPhysicalProperties==nil
''')
        self.assertEqual(result["values"], [False, True])

    def test_custom_physical_properties_cannot_be_stored_as_attribute(self):
        result = self.execute('''
local part=Instance.new("Part")
local accepted=pcall(function()
    part:SetAttribute("Physics",PhysicalProperties.new(.7,.3,.5))
end)
return accepted,part:GetAttribute("Physics")
''')
        self.assertEqual(result["values"], [False, None])


if __name__ == "__main__":
    unittest.main()
