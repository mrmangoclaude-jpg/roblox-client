"""Typed geometry enums and all Euler orders through real Luau hosts."""
import copy
import os
import time
from pathlib import Path
import unittest
from unittest import mock

import test_cframe_transforms as transforms


class GeometryEnumTests(unittest.TestCase):
    run_script=transforms.CFrameTransformTests.run_script

    def test_enum_metadata_identity_and_readonly_behavior(self):
        self.run_script('''
for _,spec in {
    {Enum.Axis,{"X","Y","Z"},"Axis"},
    {Enum.NormalId,{"Right","Top","Back","Left","Bottom","Front"},"NormalId"},
    {Enum.RotationOrder,{"XYZ","XZY","YZX","YXZ","ZXY","ZYX"},"RotationOrder"},
} do
    local e,names,name=spec[1],spec[2],spec[3]
    assert(typeof(e)=="Enum" and tostring(e)==name)
    local items=e:GetEnumItems();assert(#items==#names)
    for i,item in items do
        assert(typeof(item)=="EnumItem")
        assert(item.Name==names[i] and item.Value==i-1 and item.EnumType==e)
        assert(tostring(item)=="Enum."..name.."."..names[i])
        assert(item==e[names[i]] and rawequal(item,e:FromValue(i-1)))
        assert(rawequal(item,e:FromName(names[i])))
        local lookup={[item]="held"}
        assert(lookup[e:GetEnumItems()[i]]=="held")
        assert(not pcall(function()item.Value=99 end))
    end
    items[1]=nil;assert(#e:GetEnumItems()==#names)
    assert(e:FromName("Missing")==nil and e:FromValue(-1)==nil)
    assert(rawequal(e:FromValue(.5),e:FromValue(0)) and e:FromValue(math.huge)==nil) -- Studio truncates the value
    assert(e:FromName(names[1]..string.char(0).."junk")==nil)
    assert(not pcall(function()return e.Missing end))
    assert(not pcall(function()e.New=1 end))
end
assert(Enum.Axis.X~=Enum.NormalId.Right)
assert(Enum.Axis.X~=Enum.RotationOrder.XYZ)
assert(Enum.AnimationPriority.Action.Name=="Action")
assert(Enum.TextChatMessageStatus.Success.Name=="Success")
''')

    def test_export_enum_registry_initializes_and_stays_immutable(self):
        self.run_script('''
for _,spec in {
 {Enum.Material,"Plastic",256},
 {Enum.SecurityCapability,"Basic",7},
 {Enum.CollisionFidelity,"Default",0},
}do
 local e,name,value=unpack(spec)
 local item=e[name]
 assert(typeof(e)=="Enum" and typeof(item)=="EnumItem")
 assert(item.Name==name and item.Value==value and item.EnumType==e)
 assert(rawequal(item,e:FromName(name)) and rawequal(item,e:FromValue(value)))
 local found=false
 for _,candidate in ipairs(e:GetEnumItems())do if candidate==item then found=true end end
 assert(found)
 assert(not pcall(function()e.New=item end))
 assert(not pcall(function()item.Value=1000 end))
end
''')

    def test_axis_and_face_vector_constructors(self):
        self.run_script('''
vec(Vector3.FromAxis(Enum.Axis.X),Vector3.xAxis)
vec(Vector3.FromAxis(Enum.Axis.Y),Vector3.yAxis)
vec(Vector3.FromAxis(Enum.Axis.Z),Vector3.zAxis)
local expected={Vector3.xAxis,Vector3.yAxis,Vector3.zAxis,-Vector3.xAxis,-Vector3.yAxis,-Vector3.zAxis}
for i,item in Enum.NormalId:GetEnumItems() do vec(Vector3.FromNormalId(item),expected[i])end
local right=Vector3.FromNormalId(Enum.NormalId.Right)
local up=Vector3.FromNormalId(Enum.NormalId.Top)
vec(right:Cross(up),Vector3.zAxis);near(right:Dot(up),0)
vec(Vector3.new(),Vector3.zero)
near(Vector3.new(3,4).Magnitude,5)
vec(Vector3.new(3,4).Unit,Vector3.new(.6,.8,0))
''')

    def test_all_euler_orders_match_ordered_axis_products(self):
        self.run_script('''
local x,y,z=.3,.7,-1.1
local rotations={X=CFrame.Angles(x,0,0),Y=CFrame.Angles(0,y,0),Z=CFrame.Angles(0,0,z)}
for _,order in Enum.RotationOrder:GetEnumItems() do
    local expected=CFrame.identity
    for i=1,3 do expected*=rotations[string.sub(order.Name,i,i)]end
    frame(CFrame.fromEulerAngles(x,y,z,order),expected)
end
frame(CFrame.fromEulerAngles(x,y,z),CFrame.Angles(x,y,z))
frame(CFrame.fromEulerAngles(x,y,z,nil),CFrame.Angles(x,y,z))
frame(CFrame.fromEulerAngles(x,y,z,Enum.RotationOrder.YXZ),CFrame.fromOrientation(x,y,z))
''')

    def test_all_euler_orders_round_trip_regular_and_singular_rotations(self):
        self.run_script('''
local indices={X=1,Y=2,Z=3}
for _,order in Enum.RotationOrder:GetEnumItems() do
    local middle=indices[string.sub(order.Name,2,2)]
    for _,pitch in {-2.6,-math.pi/2,-math.pi/2+1e-8,-.4,0,.8,math.pi/2-1e-8,math.pi/2,2.4} do
        for _,outer in {-.7,.4,2.5} do
            local angles={outer,-.9,.6};angles[middle]=pitch
            local cf=CFrame.fromEulerAngles(angles[1],angles[2],angles[3],order)
            local x,y,z=(CFrame.new(100,200,300)*cf):ToEulerAngles(order)
            frame(CFrame.fromEulerAngles(x,y,z,order),cf)
        end
    end
end
local cf=CFrame.Angles(.3,.7,-1.1)
frame(CFrame.Angles(cf:ToEulerAngles()),cf)
frame(CFrame.Angles(cf:ToEulerAngles(nil)),cf)
''')

    def test_wrong_enum_type_and_invalid_receivers_are_rejected(self):
        self.run_script('''
for _,f in {
    function()return Vector3.FromAxis(Enum.NormalId.Right)end,
    function()return Vector3.FromNormalId(Enum.Axis.X)end,
    function()return Vector3.FromAxis(0)end,
    function()return Vector3.FromNormalId("Front")end,
    function()return CFrame.fromEulerAngles(0,0,0,Enum.Axis.X)end,
    function()return CFrame.identity:ToEulerAngles(Enum.NormalId.Right)end,
    function()return CFrame.fromEulerAngles(0,0,0,"XYZ")end,
    function()return Enum.Axis.GetEnumItems({})end,
    function()return Enum.Axis.FromValue({},0)end,
} do assert(not pcall(f))end
vec(Vector3.FromNormalId(Enum.NormalId.Front),-Vector3.zAxis)
frame(CFrame.fromEulerAngles(0,0,0),CFrame.identity)
''')

    def test_snapshot_enums_decode_canonically_and_serialize_mutations(self):
        snapshot=copy.deepcopy(transforms.SNAPSHOT)
        root=next(n for n in snapshot['nodes'] if n['id']=='scope:root-1')
        root['properties'].update({
            'AxisChoice':{'$enum':{'type':'Axis','name':'Z','value':2}},
            'FaceChoice':{'$enum':{'type':'NormalId','value':5}},
            'BadChoice':{'$enum':{'type':'Axis','name':'Y','value':0}},
            'LargeChoice':{'$enum':{'type':'Axis','value':2**63}},
        })
        results=self.run_script('''
local p=game:GetService("Players").LocalPlayer.Character.HumanoidRootPart
assert(rawequal(p.AxisChoice,Enum.Axis.Z))
assert(rawequal(p.FaceChoice,Enum.NormalId.Front))
assert(({[Enum.Axis.Z]=42})[p.AxisChoice]==42)
assert(not pcall(function()return p.BadChoice end))
assert(not pcall(function()return p.LargeChoice end))
p.AxisChoice=Enum.Axis.X
assert(p.AxisChoice==Enum.Axis.X)
''',snapshot)
        for result in results:
            mutation=next(m for m in result['mutations'] if m.get('property')=='AxisChoice')
            self.assertEqual(mutation['value'],{'$enum':{'type':'Axis','name':'X','value':0}})

    def test_persistent_enum_values_survive_callbacks_and_global_replacement(self):
        rust=Path(os.environ.get('CFRAME_PERSISTENT_HOST',str(transforms.DEFAULT_HOSTS[1])))
        with mock.patch.object(transforms.persistent_runtime,'RUST_HOST',rust):
            host=transforms.persistent_runtime.PersistentLuauHost(copy.deepcopy(transforms.SNAPSHOT))
        self.addCleanup(host.close)
        first=host.call({'op':'execute','source':transforms.HELPERS+'''
getgenv().axis=Enum.Axis.X
getgenv().order=Enum.RotationOrder.ZXY
getgenv().fromAxis=Vector3.FromAxis
getgenv().event=Instance.new("BindableEvent")
getgenv().received=nil
event.Event:Connect(function(value)received=value end)
event:Fire({axis=axis,order=order})
local f=Instance.new("BindableFunction")
f.OnInvoke=function(value)return value,axis end
local returned,returnedAxis=f:Invoke(order)
assert(returned==order and returnedAxis==axis)
getgenv().Enum={}
return true
'''})
        self.assertTrue(first['ok'],first)
        # BindableFunction.Invoke can finish on a later scheduler turn.
        if not first.get('completed'):
            job=first['job_id']
            deadline=time.monotonic()+2
            while time.monotonic()<deadline:
                polled=host.call({'op':'poll','timeout_ms':100})
                self.assertTrue(polled['ok'],polled)
                self.assertFalse(polled.get('task_errors'),polled)
                done=next((item for item in polled.get('completed_jobs',[]) if item['job_id']==job),None)
                if done:
                    first=done
                    break
                time.sleep(.005)
        self.assertTrue(first['completed'],first)
        second=host.call({'op':'execute','source':transforms.HELPERS+'''
assert(received.axis==axis and received.order==order)
assert(axis.EnumType.X==axis)
vec(fromAxis(axis),Vector3.xAxis)
frame(CFrame.fromEulerAngles(.2,.3,.4,order),CFrame.Angles(0,0,.4)*CFrame.Angles(.2,0,0)*CFrame.Angles(0,.3,0))
return axis,order
'''})
        self.assertTrue(second['ok'],second)
        self.assertFalse(second['task_errors'],second)
        self.assertEqual(second['values'],[
            {'$enum':{'type':'Axis','name':'X','value':0}},
            {'$enum':{'type':'RotationOrder','name':'ZXY','value':4}},
        ])


if __name__=='__main__':unittest.main()
