"""Integer datatype behavior and transport through the real Luau VM."""
import copy
import json
import subprocess
import tempfile
from pathlib import Path
import unittest
import test_motion_math as motion

ROOT=Path(__file__).resolve().parents[2]


@unittest.skipUnless(motion.RUST_HOST.is_file(),'build the persistent worker first')
class IntegerVectorsTests(unittest.TestCase):
    setUp=motion.MotionMathTests.setUp
    execute=motion.MotionMathTests.execute

    def test_complete_native_constructor_arithmetic_and_attribute_probe(self):
        source=(ROOT/'tests/fixtures/integer_vectors_studio_probe.luau').read_text()
        expected=json.loads((ROOT/'tests/fixtures/references/integer-vectors-studio-reference.json').read_text())
        expected.pop('version')
        result=self.execute(source)
        self.assertEqual(json.loads(result['values'][0]),expected)

    def test_immutable_fields_type_identity_aliases_and_overflow(self):
        self.execute('''
for _,ctor in ipairs({Vector2int16.new,Vector3int16.new})do
 local a=ctor(32767,-32768,9)
 assert(a+a==ctor(-2,0,18))
 assert(-a==ctor(-32767,-32768,-9))
 assert(a.x==a.X and a.y==a.Y)
 assert(not pcall(function()a.X=0 end))
 assert(not pcall(function()return a.Magnitude end))
 assert(ctor(1.99999999999).X==1 and ctor(32767.9999).X==32767)
 assert(ctor(1e20).X==-1 and ctor(-1e20).X==0)
 assert(ctor({}).X==0 and ctor(function()end).X==0)
end
assert(typeof(Vector2int16.new())=="Vector2int16")
assert(typeof(Vector3int16.new())=="Vector3int16")
assert(Vector2int16.new(1,2)~=Vector3int16.new(1,2,0))
assert(not pcall(function()return Vector2int16.new()+Vector3int16.new()end))
assert(2/Vector3int16.new(1,2,3)==Vector3int16.new(2,1,0)) -- Studio divides a number by each component
assert(not pcall(function()Vector3int16.new=function()end end))
''')

    def test_region_defaults_reversed_bounds_value_equality_and_validation(self):
        self.execute('''
local a,b=Vector3int16.new(3,4,5),Vector3int16.new(-1,-2,-3)
local r=Region3int16.new(a,b)
assert(typeof(r)=="Region3int16" and r.Min==a and r.Max==b)
assert(r==Region3int16.new(a,b) and r~=Region3int16.new(b,a))
assert(tostring(r)=="3, 4, 5; -1, -2, -3")
assert(Region3int16.new().Min==Vector3int16.new())
assert(Region3int16.new(a).Max==Vector3int16.new())
assert(not pcall(function()r.Min=b end))
assert(not pcall(Region3int16.new,Vector2int16.new()))
assert(not pcall(Region3int16.new,Vector3.new()))
assert(not pcall(function()return r.Size end))
assert(not pcall(function()Instance.new("Folder"):SetAttribute("Region",r)end))
''')

    def test_bindable_event_and_yielding_function_preserve_nested_typed_values(self):
        result=self.execute('''
local payload={Vector2int16.new(-32768,32767),Vector3int16.new(9,8,7),
 Region3int16.new(Vector3int16.new(-1,-2,-3),Vector3int16.new(1,2,3))}
local event=Instance.new("BindableEvent")
local received
event.Event:Connect(function(data)
 task.wait(.005)
 assert(data~=payload)
 for i,v in ipairs(payload)do assert(data[i]==v and typeof(data[i])==typeof(v))end
 received=data
end)
event:Fire(payload)
for _=1,100 do if received then break end;task.wait(.005)end
assert(received)
local fn=Instance.new("BindableFunction")
fn.OnInvoke=function(data)task.wait(.005);return data,Region3int16.new()end
local data,region=fn:Invoke(received)
assert(data~=received and data[3]==payload[3] and region==Region3int16.new())
event:Destroy();fn:Destroy()
return data[1],data[2],data[3]
''')
        self.assertEqual(result['values'],[
            {'$vector2int16':[-32768,32767]}, {'$vector3int16':[9,8,7]},
            {'$region3int16':[{'$vector3int16':[-1,-2,-3]},{'$vector3int16':[1,2,3]}]}])

    def test_snapshot_values_restore_using_cached_constructors(self):
        snapshot=copy.deepcopy(motion.SNAPSHOT)
        game=next(n for n in snapshot['nodes'] if n['class_name']=='Workspace')
        game['properties']['IntegerPayload']={'$region3int16':[
            {'$vector3int16':[-1,-2,-3]},{'$vector3int16':[4,5,6]}]}
        self.host.close();self.host=motion.PersistentLuauHost(snapshot);self.addCleanup(self.host.close)
        result=self.execute('''
Vector3int16={new=function()error("global constructor must not be used by transport")end}
Region3int16={new=function()error("global constructor must not be used by transport")end}
local r=workspace.IntegerPayload
assert(typeof(r)=="Region3int16" and typeof(r.Min)=="Vector3int16")
assert(r.Min.X==-1 and r.Max.Z==6)
return r
''')
        self.assertEqual(result['values'],[game['properties']['IntegerPayload']])

    def test_new_types_are_available_inside_required_modules(self):
        result=self.execute((ROOT/'runtime/scripts/integer_vectors_demo.luau').read_text())
        self.assertEqual(result['values'],['Integer vector scripting completed',{'$vector3int16':[12,6,-9]}])

    @unittest.skipUnless(motion.STANDALONE.is_file(),'build the standalone worker first')
    def test_both_native_workers_run_datetime_and_integer_value_scripts(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            snapshot=path/'world.json';snapshot.write_text(json.dumps(motion.SNAPSHOT))
            sources=['''local now=DateTime.now();local t=now:ToLocalTime()
assert(DateTime.fromLocalTime(t.Year,t.Month,t.Day,t.Hour,t.Minute,t.Second,t.Millisecond)==now)
return DateTime.fromIsoDate("2026-11-02T12:00:00+05:45"):ToIsoDate(),typeof(now)''',
'''local a=Vector3int16.new(32767,-32768,9)
local b=a+Vector3int16.new(1,-1,2)
local region=Region3int16.new(a,b)
assert(region.Min==a and region.Max==b)
return region,Vector2int16.new(1,2)*2.5''']
            for source in sources:
                script=path/'source.luau';script.write_text(source)
                responses=[]
                for host in [motion.RUST_HOST,motion.STANDALONE]:
                    result=subprocess.run([str(host),'--source',str(script),
                        '--world-snapshot',str(snapshot),'--timeout-ms','2000'],capture_output=True,timeout=10)
                    body=json.loads(result.stdout)
                    self.assertEqual(result.returncode,0,body)
                    self.assertTrue(body['ok'],body)
                    self.assertFalse(body.get('task_errors'),body)
                    responses.append(body['values'])
                self.assertEqual(responses[0],responses[1])


if __name__=='__main__':unittest.main()
