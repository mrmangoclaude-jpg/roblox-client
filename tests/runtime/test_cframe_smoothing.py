"""CFrame smoothing and script helpers executed by the real Luau worker."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import test_motion_math as motion

ROOT=Path(__file__).resolve().parents[2]
REFERENCE=json.loads((ROOT/'tests/fixtures/references/cframe-smoothing-studio-reference.json').read_text())
HELPERS='''
local service=game:GetService("TweenService")
local function frame(values)return CFrame.new(unpack(values))end
local function close(actual,expected,label)
 local components={actual:GetComponents()}
 for i=1,12 do
  assert(math.abs(components[i]-expected[i])<math.max(3e-5,math.abs(expected[i])*3e-5),label.." component "..i..": "..components[i].." vs "..expected[i])
 end
end
'''


@unittest.skipUnless(motion.RUST_HOST.is_file(),'build the worker first')
class CFrameSmoothingTests(unittest.TestCase):
    setUp=motion.MotionMathTests.setUp
    execute=motion.MotionMathTests.execute

    def test_single_steps_match_studio_including_raw_velocity_and_clamps(self):
        source='local cases=game:GetService("HttpService"):JSONDecode([==['+json.dumps(REFERENCE['cases'])+']==])\n'
        self.execute(HELPERS+source+'''
for _,c in ipairs(cases)do
 local velocity=type(c.velocity)=="table" and frame(c.velocity) or c.velocity
 local value,nextVelocity=service:SmoothDamp(frame(c.current),frame(c.target),velocity,c.smooth,c.speed,c.dt)
 assert(typeof(value)=="CFrame" and typeof(nextVelocity)=="CFrame")
 close(value,c.value,c.name.." value")
 close(nextVelocity,c.nextVelocity,c.name.." velocity")
end
''')

    def test_returned_velocity_matches_studio_over_moving_target_trajectory(self):
        source='local cases=game:GetService("HttpService"):JSONDecode([==['+json.dumps(REFERENCE['trajectory'])+']==])\n'
        self.execute(HELPERS+source+'''
local value,velocity=CFrame.identity,0
local reference=1
for step=1,120 do
 local target=step<=60 and CFrame.new(9,-2,1)*CFrame.Angles(-.2,-1.2,.8) or CFrame.new(-4,7,2)*CFrame.Angles(.8,2,-1.2)
 value,velocity=service:SmoothDamp(value,target,velocity,.2,30,1/60)
 if cases[reference] and step==cases[reference].step then
  close(value,cases[reference].value,"step "..step)
  close(velocity,cases[reference].velocity,"step "..step.." velocity")
  reference+=1
 end
end
assert(reference==#cases+1)
''')

    def test_zero_dt_preserves_payload_and_instant_time_returns_zero_velocity(self):
        self.execute('''
local service=game:GetService("TweenService")
local current=CFrame.new(1,2,3)*CFrame.Angles(.2,.4,-.3)
local target=CFrame.new(5,8,3)*CFrame.Angles(-1,.5,2)
local velocity=CFrame.new(1,2,3,.2,-.3,.4,5,6,7,8,9,10)
local value,nextVelocity=service:SmoothDamp(current,target,velocity,.5,nil,0)
assert(value==current and nextVelocity==velocity)
value,nextVelocity=service:SmoothDamp(current,target,velocity,0,nil,.1)
assert(value==target)
for _,v in ipairs({nextVelocity:GetComponents()})do assert(v==0)end
''')

    def test_numeric_velocity_initializes_zero_and_unknown_target_types_fail(self):
        self.execute('''
local s=game:GetService("TweenService")
local target=CFrame.Angles(0,1,0)
local a,b=s:SmoothDamp(CFrame.identity,target,0,.5,nil,.1)
local c,d=s:SmoothDamp(CFrame.identity,target,1,.5,nil,.1)
assert(a==c and b==d)
assert(a:AngleBetween(CFrame.identity)>0 and a:AngleBetween(target)<1)
assert(not pcall(function()s:SmoothDamp(CFrame.identity,Vector3.one,0,.5)end))
''')

    def test_raw_velocity_survives_another_execution_and_bindable_transport(self):
        self.execute('''
local s=game:GetService("TweenService")
savedValue,savedVelocity=s:SmoothDamp(CFrame.identity,CFrame.Angles(0,1,0),CFrame.identity,.5,nil,.1)
''')
        self.execute('''
local s=game:GetService("TweenService")
local before={savedVelocity:GetComponents()}
assert(math.abs(before[4]-.40218791365623476)<1e-6 and before[8]==1 and before[12]==1)
local b=Instance.new("BindableEvent")
local received
b.Event:Connect(function(value)received=value end)
b:Fire(savedVelocity);task.wait(.01)
assert(received==savedVelocity)
local a,v=s:SmoothDamp(savedValue,CFrame.Angles(0,1,0),received,.5,nil,.1)
assert(typeof(a)=="CFrame" and typeof(v)=="CFrame")
b:Destroy()
''')

    def test_legacy_cframe_methods_preserve_results_and_variadic_returns(self):
        self.execute('''
local a=CFrame.new(1,2,3)*CFrame.Angles(.2,.4,.6)
local b,c=CFrame.new(4,5,6),CFrame.new(7,8,9)
assert(a:inverse()==a:Inverse() and a:lerp(b,.3)==a:Lerp(b,.3))
for _,pair in ipairs({{"toWorldSpace","ToWorldSpace"},{"toObjectSpace","ToObjectSpace"}})do
 local x,y=a[pair[1]](a,b,c);local xx,yy=a[pair[2]](a,b,c)
 assert(x==xx and y==yy)
end
for _,pair in ipairs({{"pointToWorldSpace","PointToWorldSpace"},{"pointToObjectSpace","PointToObjectSpace"},{"vectorToWorldSpace","VectorToWorldSpace"},{"vectorToObjectSpace","VectorToObjectSpace"}})do
 local x,y=a[pair[1]](a,Vector3.one,Vector3.xAxis)
 local xx,yy=a[pair[2]](a,Vector3.one,Vector3.xAxis)
 assert(x==xx and y==yy)
end
for _,pair in ipairs({{"toEulerAnglesXYZ","ToEulerAnglesXYZ"},{"toEulerAnglesYXZ","ToEulerAnglesYXZ"},{"toAxisAngle","ToAxisAngle"}})do
 local x,y,z=a[pair[1]](a);local xx,yy,zz=a[pair[2]](a)
 assert(x==xx and y==yy and z==zz)
end
''')

    def test_get_enums_returns_sorted_canonical_supported_objects(self):
        self.execute('''
local root=Enum
local all=root:GetEnums()
local count=0
-- The real client's `pairs(Enum)` errors (Enums is opaque userdata), so count
-- through the supported GetEnums API instead of asserting non-Roblox behavior.
for _,value in ipairs(all)do if typeof(value)=="Enum" then count+=1 end end
assert(#all==count and count>10)
local seen={}
for i,value in ipairs(all)do
 assert(typeof(value)=="Enum" and value==root[tostring(value)] and not seen[value])
 seen[value]=true
 if i>1 then assert(tostring(all[i-1])<tostring(value))end
end
assert(seen[root.Axis] and seen[root.Material] and seen[root.PlaybackState])
all[1]=nil;assert(#root:GetEnums()==count)
assert(not pcall(function()root.GetEnums()end))
assert(not pcall(function()root.GetEnums({})end))
Enum=nil;assert(#root:GetEnums()==count)
''')

    def test_authored_cframe_demo_updates_pose_and_converges(self):
        result=self.execute((ROOT/'runtime/scripts/cframe_smoothing_demo.luau').read_text())
        self.assertEqual(result['values'][0],'CFrame smoothed')
        self.assertGreater(result['values'][1],1)
        self.assertLess(result['values'][2],.001)
        self.assertLess(result['values'][3],.001)

    @unittest.skipUnless(motion.STANDALONE.is_file(),'build the standalone host first')
    def test_standalone_runs_native_cases_and_pose_demo(self):
        source=HELPERS+'local cases=game:GetService("HttpService"):JSONDecode([==['+json.dumps(REFERENCE['cases'])+']==])\n'+'''
for _,c in ipairs(cases)do
 local velocity=type(c.velocity)=="table" and frame(c.velocity) or c.velocity
 local a,b=service:SmoothDamp(frame(c.current),frame(c.target),velocity,c.smooth,c.speed,c.dt)
 close(a,c.value,c.name);close(b,c.nextVelocity,c.name.." velocity")
end
assert(#Enum:GetEnums()>10 and typeof(Enum.HumanoidStateType)=="Enum")
assert(CFrame.identity:inverse()==CFrame.identity)
'''+(ROOT/'runtime/scripts/cframe_smoothing_demo.luau').read_text()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            (path/'source.luau').write_text(source)
            (path/'world.json').write_text(json.dumps(motion.SNAPSHOT))
            completed=subprocess.run([str(motion.STANDALONE),'--source',str(path/'source.luau'),
                '--world-snapshot',str(path/'world.json'),'--timeout-ms','2000'],capture_output=True,timeout=10)
            result=json.loads(completed.stdout)
            self.assertEqual(completed.returncode,0,result.get('error'))
            self.assertTrue(result['ok'],result.get('error'))
            self.assertFalse(result.get('task_errors'),result.get('task_errors'))
            self.assertEqual(result['values'][0],'CFrame smoothed')
            self.assertLess(result['values'][2],.001)
            self.assertLess(result['values'][3],.001)


if __name__=='__main__':unittest.main()
