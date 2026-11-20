"""Actual authored-Luau tests for TweenInfo and TweenService:GetValue."""
import copy
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import local_runtime
from persistent_runtime import PersistentLuauHost

if os.environ.get("LUAU_TEST_HOST"):
    local_runtime.RUST_HOST = Path(os.environ["LUAU_TEST_HOST"])
    if not local_runtime.RUST_HOST.is_file():
        raise RuntimeError("LUAU_TEST_HOST must point to a completed build")
RUST_HOST = local_runtime.RUST_HOST
import persistent_runtime
persistent_runtime.RUST_HOST = RUST_HOST

SNAPSHOT = json.loads((ROOT / "tests/fixtures/world_snapshot.json").read_text())


@unittest.skipUnless(RUST_HOST.is_file(), "build the Rust host with tween bindings first")
class TweenValueTests(unittest.TestCase):
    def setUp(self):
        self.host = PersistentLuauHost(copy.deepcopy(SNAPSHOT))
        self.addCleanup(self.host.close)

    def execute(self, source):
        result = self.host.call({"op": "execute", "source": source, "timeout_ms": 1000})
        self.assertTrue(result.get("ok"), result)
        self.assertFalse(result.get("task_errors"), result)
        return result

    def test_easing_enum_names_and_values_match_creator_docs(self):
        result = self.execute('''
local styles={"Linear","Sine","Back","Quad","Quart","Quint","Bounce",
               "Elastic","Exponential","Circular","Cubic","Bezier","Spring"} -- the docs list 11; the engine (client, Studio) has these 13
local directions={"In","Out","InOut"}
local gotStyles=Enum.EasingStyle:GetEnumItems()
local gotDirections=Enum.EasingDirection:GetEnumItems()
assert(#gotStyles==#styles and #gotDirections==#directions)
for i,name in ipairs(styles) do
    local item=Enum.EasingStyle[name]
    assert(item.Name==name and item.Value==i-1 and item.EnumType==Enum.EasingStyle)
    assert(gotStyles[i]==item)
end
for i,name in ipairs(directions) do
    local item=Enum.EasingDirection[name]
    assert(item.Name==name and item.Value==i-1 and item.EnumType==Enum.EasingDirection)
    assert(gotDirections[i]==item)
end
return tostring(Enum.EasingStyle), tostring(Enum.EasingDirection)
''')
        self.assertEqual(result["values"], ["EasingStyle", "EasingDirection"])

    def test_tween_info_defaults_fields_immutability_and_equality(self):
        result = self.execute('''
local a=TweenInfo.new()
local b=TweenInfo.new(1,Enum.EasingStyle.Quad,Enum.EasingDirection.Out,0,false,0)
assert(typeof(a)=="TweenInfo" and tostring(a)=="TweenInfo" and a==b)
assert(a.Time==1 and a.EasingStyle==Enum.EasingStyle.Quad)
assert(a.EasingDirection==Enum.EasingDirection.Out and a.RepeatCount==0)
assert(a.Reverses==false and a.DelayTime==0)
local custom=TweenInfo.new(2.5,Enum.EasingStyle.Bounce,Enum.EasingDirection.InOut,-1,true,.25)
assert(custom.Time==2.5 and custom.EasingStyle==Enum.EasingStyle.Bounce)
assert(custom.EasingDirection==Enum.EasingDirection.InOut and custom.RepeatCount==-1)
assert(custom.Reverses==true and custom.DelayTime==.25 and custom~=a)
for _,key in ipairs({"Time","EasingStyle","EasingDirection","RepeatCount","Reverses","DelayTime"}) do
    local ok=pcall(function()custom[key]=0 end)
    assert(not ok,key)
end
return a.Time,a.EasingStyle.Value,a.EasingDirection.Value,
       custom.RepeatCount,custom.Reverses,custom.DelayTime
''')
        self.assertEqual(result["values"], [1, 3, 1, -1, True, 0.25])

    def test_tween_info_serializes_as_six_components(self):
        result = self.execute('return TweenInfo.new(2.5,Enum.EasingStyle.Bounce,Enum.EasingDirection.InOut,-1,true,.25)')
        self.assertEqual(result["values"], [{"$tween_info": [2.5, 6, 2, -1, True, 0.25]}])

    def test_bindable_event_passes_tween_info(self):
        self.execute('''
local event=Instance.new("BindableEvent")
getgenv().receivedTweenInfo=nil
event.Event:Connect(function(value)receivedTweenInfo=value end)
event:Fire(TweenInfo.new(3,Enum.EasingStyle.Elastic,Enum.EasingDirection.In,2,true,.5))
''')
        result = self.execute('''
local value=receivedTweenInfo
return typeof(value),value.Time,value.EasingStyle.Value,value.EasingDirection.Value,
       value.RepeatCount,value.Reverses,value.DelayTime
''')
        self.assertEqual(result["values"], ["TweenInfo", 3, 7, 0, 2, True, 0.5])

    def test_tween_info_rejects_invalid_types_and_ranges(self):
        result = self.execute('''
local bad={
    function()return TweenInfo.new(-1)end,
    function()return TweenInfo.new(math.huge)end,
    function()return TweenInfo.new(0/0)end,
    function()return TweenInfo.new(1,Enum.Axis.X)end,
    function()return TweenInfo.new(1,Enum.EasingStyle.Linear,Enum.Axis.X)end,
    function()return TweenInfo.new(1,nil,nil,.5)end,
    function()return TweenInfo.new(1,nil,nil,2147483648)end,
    function()return TweenInfo.new(1,nil,nil,0,0)end,
    function()return TweenInfo.new(1,nil,nil,0,false,-1)end,
    function()return TweenInfo.new(1,nil,nil,0,false,math.huge)end,
    function()return TweenInfo.new(1,nil,nil,0,false,0,7)end,
}
for _,create in ipairs(bad) do assert(not pcall(create)) end
assert(TweenInfo.new(0).Time==0)
assert(TweenInfo.new(1,nil,nil,-1).RepeatCount==-1)
return #bad
''')
        self.assertEqual(result["values"], [11])

    def test_get_value_reference_cases_all_styles_and_directions(self):
        result = self.execute('''
local tween=game:GetService("TweenService")
local function near(a,b)assert(math.abs(a-b)<2e-6,tostring(a).." vs "..tostring(b))end
local function get(alpha,style,direction)
    return tween:GetValue(alpha,Enum.EasingStyle[style],Enum.EasingDirection[direction])
end
near(get(.25,"Linear","In"),.25)
near(get(.25,"Sine","In"),1-math.cos(math.pi/8))
near(get(.25,"Quad","Out"),.4375)
near(get(.25,"Quad","InOut"),.125)
near(get(.25,"Cubic","In"),.015625)
near(get(.25,"Quart","In"),.00390625)
near(get(.25,"Quint","In"),.0009765625)
near(get(.5,"Bounce","Out"),.765625)
near(get(.5,"Elastic","Out"),1-2^-5*math.sin(math.pi*3.25))
near(get(.25,"Exponential","In"),2^-7.5)
assert(math.abs(get(.25,"Circular","Out")-math.sqrt(1-.75^2))<1e-6)
near(get(.5,"Back","InOut"),.5)
for _,style in ipairs(Enum.EasingStyle:GetEnumItems()) do
    for _,direction in ipairs(Enum.EasingDirection:GetEnumItems()) do
        near(tween:GetValue(0,style,direction),0)
        near(tween:GetValue(1,style,direction),1)
    end
end
near(get(-10,"Linear","In"),0)
near(get(10,"Linear","Out"),1)
return get(.5,"Quad","InOut")
''')
        self.assertEqual(result["values"], [0.5])

    def test_get_value_rejects_bad_alpha_and_enum_kinds(self):
        result = self.execute('''
local tween=game:GetService("TweenService")
local function call(alpha,style,direction)
    return pcall(function()return tween:GetValue(alpha,style,direction)end)
end
assert(call(math.huge,Enum.EasingStyle.Linear,Enum.EasingDirection.In))
local nan=tween:GetValue(0/0,Enum.EasingStyle.Linear,Enum.EasingDirection.In)
assert(nan~=nan)
assert(not call(.5,Enum.Axis.X,Enum.EasingDirection.In))
assert(not call(.5,Enum.EasingStyle.Linear,Enum.Axis.X))
assert(not pcall(function()tween:GetValue(.5,"Linear",Enum.EasingDirection.In)end))
return true
''')
        self.assertEqual(result["values"], [True])


if __name__ == "__main__":
    unittest.main()
