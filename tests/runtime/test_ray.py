"""Public Ray operations in both compiled source hosts, using synthetic worlds."""
import copy
import os
from pathlib import Path
import unittest
from unittest import mock

import test_cframe_transforms as transforms


def encoded(origin, direction):
    return {'$ray': [{'$vector3': origin}, {'$vector3': direction}]}


class RayTests(unittest.TestCase):
    run_script = transforms.CFrameTransformTests.run_script

    def test_constructor_properties_unit_and_value_equality(self):
        self.run_script('''
local origin,direction=Vector3.new(10,20,30),Vector3.new(0,3,4)
local ray=Ray.new(origin,direction)
assert(typeof(ray)=="Ray" and type(ray)=="userdata")
vec(ray.Origin,origin);vec(ray.Direction,direction)
vec(ray.Unit.Origin,origin);vec(ray.Unit.Direction,Vector3.new(0,.6,.8))
near(ray.Unit.Direction.Magnitude,1)
assert(ray==Ray.new(origin,direction))
assert(ray~=Ray.new(origin,-direction))
assert(ray~=Ray.new(-origin,direction))
assert(ray~=origin and ray~=nil and ray~=Color3.new())
assert(#tostring(ray)>0)
-- Construction preserves direction magnitude; rays are not normalized implicitly.
near(ray.Direction.Magnitude,5)
vec(Ray.new(origin,Vector3.zero).Direction,Vector3.zero)
''')

    def test_unit_ray_projection_clamps_behind_origin_and_extends_forward(self):
        self.run_script('''
local r=Ray.new(Vector3.new(10,20,30),Vector3.xAxis)
vec(r:ClosestPoint(Vector3.new(13,24,30)),Vector3.new(13,20,30))
near(r:Distance(Vector3.new(13,24,30)),4)
vec(r:ClosestPoint(Vector3.new(7,24,30)),r.Origin)
near(r:Distance(Vector3.new(7,24,30)),5)
vec(r:ClosestPoint(Vector3.new(1010,20,30)),Vector3.new(1010,20,30))
near(r:Distance(r.Origin),0)
local diagonal=Ray.new(Vector3.zero,Vector3.new(3,4,0)).Unit
vec(diagonal:ClosestPoint(Vector3.new(6,8,10)),Vector3.new(6,8,0))
near(diagonal:Distance(Vector3.new(6,8,10)),10)
''')

    def test_projection_is_rigid_transform_invariant(self):
        self.run_script('''
local base=Ray.new(Vector3.new(2,3,-4),Vector3.zAxis)
for i=1,30 do
    local cf=CFrame.new(i,-i,i/2)*CFrame.Angles(i/10,-i/7,i/3)
    local moved=Ray.new(cf*base.Origin,cf:VectorToWorldSpace(base.Direction))
    for _,point in {Vector3.new(5,7,6),Vector3.new(5,7,-10),base.Origin} do
        vec(moved:ClosestPoint(cf*point),cf*base:ClosestPoint(point))
        near(moved:Distance(cf*point),base:Distance(point))
    end
end
''')

    def test_immutable_values_and_invalid_arguments(self):
        self.run_script('''
local r=Ray.new(Vector3.zero,Vector3.xAxis)
-- Real clients default absent components to zero vectors.
local blank=Ray.new()
vec(blank.Origin,Vector3.zero);vec(blank.Direction,Vector3.zero)
local one=Ray.new(Vector3.new(1,2,3))
vec(one.Origin,Vector3.new(1,2,3));vec(one.Direction,Vector3.zero)
for _,f in {
    function()r.Origin=Vector3.one end,
    function()r.Direction=Vector3.yAxis end,
    function()r.Unit=r end,
    function()Ray.new={}end,
    function()Ray.new(Vector3.zero,42)end,
    function()Ray.new({},Vector3.zero)end,
    function()r:ClosestPoint({})end,
    function()r.Distance({},Vector3.zero)end,
    function()return r.Unknown end,
    function()return r["Origin"..string.char(0).."extra"]end,
    function()Instance.new("Part"):SetAttribute("ray",r)end,
} do assert(not pcall(f))end
vec(r.Origin,Vector3.zero);near(r:Distance(Vector3.yAxis),1)
''')

    def test_snapshot_and_mutation_round_trip(self):
        snapshot=copy.deepcopy(transforms.SNAPSHOT)
        root=next(n for n in snapshot['nodes'] if n['id']=='scope:root-1')
        root['properties']['TestRay']=encoded([1,2,3],[0,0,-1])
        results=self.run_script('''
local p=game:GetService("Players").LocalPlayer.Character.HumanoidRootPart
assert(p.TestRay==Ray.new(Vector3.new(1,2,3),-Vector3.zAxis))
near(p.TestRay:Distance(Vector3.new(4,6,-10)),5)
p.TestRay=Ray.new(Vector3.new(4,5,6),Vector3.yAxis)
vec(p.TestRay.Origin,Vector3.new(4,5,6))
''',snapshot)
        for result in results:
            mutation=next(m for m in result['mutations'] if m.get('property')=='TestRay')
            self.assertEqual(mutation['value'],encoded([4,5,6],[0,1,0]))

    def test_malformed_snapshot_rays_fail_without_losing_valid_values(self):
        snapshot=copy.deepcopy(transforms.SNAPSHOT)
        root=next(n for n in snapshot['nodes'] if n['id']=='scope:root-1')
        bad=[[],[1,2],[{'$vector3':[1,2]}, {'$vector3':[0,1,0]}],
             [{'$vector3':[0,False,0]},{'$vector3':[0,1,0]}],
             [{'$vector3':[0,{'$number':'wrong'},0]},{'$vector3':[0,1,0]}]]
        root['properties'].update({f'BadRay{i+1}':{'$ray':value} for i,value in enumerate(bad)})
        self.run_script('''
local p=game:GetService("Players").LocalPlayer.Character.HumanoidRootPart
for n=1,10 do for i=1,5 do assert(not pcall(function()return p["BadRay"..i]end))end end
near(Ray.new(Vector3.zero,Vector3.xAxis):Distance(Vector3.new(0,3,4)),5)
''',snapshot)

    def test_persistent_callbacks_and_cached_snapshot_constructor(self):
        snapshot=copy.deepcopy(transforms.SNAPSHOT)
        root=next(n for n in snapshot['nodes'] if n['id']=='scope:root-1')
        root['properties']['TestRay']=encoded([1,2,3],[0,0,-1])
        rust=Path(os.environ.get('CFRAME_PERSISTENT_HOST',str(transforms.DEFAULT_HOSTS[1])))
        with mock.patch.object(transforms.persistent_runtime,'RUST_HOST',rust):
            host=transforms.persistent_runtime.PersistentLuauHost(snapshot)
        self.addCleanup(host.close)
        first=host.call({'op':'execute','source':transforms.HELPERS+'''
getgenv().savedRay=Ray.new(Vector3.new(1,2,3),-Vector3.zAxis)
local e=Instance.new("BindableEvent")
e.Event:Connect(function(value)getgenv().receivedRay=value.ray end)
e:Fire({ray=savedRay})
local f=Instance.new("BindableFunction")
f.OnInvoke=function(value)return value end
assert(f:Invoke(savedRay)==savedRay)
getgenv().Ray={new=function()error("overwritten constructor must not be called")end}
return true
'''})
        self.assertTrue(first['ok'],first);self.assertTrue(first['completed'],first)
        self.assertFalse(first['task_errors'],first)
        second=host.call({'op':'execute','source':transforms.HELPERS+'''
assert(savedRay==receivedRay)
local p=game:GetService("Players").LocalPlayer.Character.HumanoidRootPart
assert(p.TestRay==savedRay)
vec(receivedRay:ClosestPoint(Vector3.new(1,2,-5)),Vector3.new(1,2,-5))
return receivedRay,p.TestRay
'''})
        self.assertTrue(second['ok'],second);self.assertTrue(second['completed'],second)
        self.assertFalse(second['task_errors'],second)
        self.assertEqual(second['values'],[encoded([1,2,3],[0,0,-1])]*2)


if __name__=='__main__':unittest.main()
