"""Integrated authored-VM fixtures and movement intentions; no live connection."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from local_runtime import HOST, RUST_HOST
from persistent_runtime import PersistentLuauHost, PersistentClientScriptRuntime
from script_runtime import ClientScriptRuntime
from test_world_snapshot import fixture


def snapshot():
    result=json.loads((ROOT/'tests/fixtures/world_snapshot.json').read_text())
    result['nodes'].append({'id':'scope:http','class_name':'HttpService','name':'HttpService',
                            'parent':'game','properties':{}})
    result['services']['HttpService']='scope:http'
    return result


@unittest.skipUnless(RUST_HOST.is_file(),'build the Rust host first')
class ExpandedBindingsTests(unittest.TestCase):
    def setUp(self):
        self.host=PersistentLuauHost(snapshot())
        self.addCleanup(self.host.close)

    def execute(self,source):
        response=self.host.call({'op':'execute','source':source,'timeout_ms':1000})
        self.assertTrue(response['ok'],response)
        self.assertFalse(response['task_errors'],response)
        return response

    def check_fixture(self,name):
        result=self.execute((ROOT/'tests/fixtures'/name).read_text())
        self.assertTrue(result['completed'],result)

    def test_color3_fixture(self):self.check_fixture('color3_bindings.luau')
    def test_vector2_fixture(self):self.check_fixture('vector2_bindings.luau')
    def test_udim_fixture(self):self.check_fixture('udim_bindings.luau')
    def test_range_fixture(self):self.check_fixture('range_bindings.luau')
    def test_brickcolor_subset_fixture(self):self.check_fixture('brickcolor_bindings.luau')

    def test_brickcolor_native_palette_expansion(self):
        result=self.execute('''
local expected={
    {2,"Grey",161,165,162},
    {194,"Medium stone grey",163,162,165},
    {365,"Burnt Sienna",106,57,9},
    {1001,"Institutional white",248,248,248},
    {1032,"Hot pink",255,0,191},
}
for _,entry in ipairs(expected) do
    local value=BrickColor.new(entry[1])
    assert(value==BrickColor.new(entry[2]))
    assert(value.Number==entry[1] and value.Name==entry[2])
    assert(math.abs(value.r-entry[3]/255)<1e-9)
    assert(math.abs(value.g-entry[4]/255)<1e-9)
    assert(math.abs(value.b-entry[5]/255)<1e-9)
    local color=Color3.new(entry[3]/255,entry[4]/255,entry[5]/255)
    assert(value.Color==color)
    assert(BrickColor.new(color)==value)
    assert(BrickColor.new(entry[3]/255,entry[4]/255,entry[5]/255)==value)
end
for _,number in ipairs({4,999,1033}) do
    assert(BrickColor.new(number)==BrickColor.Gray())
end
assert(BrickColor.new("not in native palette")==BrickColor.Gray())
assert(BrickColor.palette(1).Number==301)
assert(typeof(BrickColor.random())=="BrickColor")
return #expected
''')
        self.assertEqual(result['values'],[5])

    def test_datetime_fixture(self):self.check_fixture('datetime_bindings.luau')
    def test_sequence_fixture(self):self.check_fixture('sequence_bindings.luau')
    def test_closure_fixture(self):self.check_fixture('closure_bindings.luau')
    def test_json_fixture(self):self.check_fixture('json_bindings.luau')

    def test_movement_fixture_emits_intents_without_changing_pose(self):
        before=self.execute('return game:GetService("Players").LocalPlayer.Character.HumanoidRootPart.Position')['values']
        result=self.execute((ROOT/'tests/fixtures/movement_intents.luau').read_text())
        intents=result['movement_intents']
        self.assertGreaterEqual(len(intents),4)
        self.assertEqual(intents[0]['kind'],'Move')
        self.assertFalse(intents[0]['relative_to_camera'])
        self.assertEqual(sum(i['kind']=='MoveTo' for i in intents),1)
        self.assertEqual([i['sequence'] for i in intents],list(range(1,len(intents)+1)))
        self.assertNotEqual(intents[0]['instance_id'],intents[-1]['instance_id'])
        after=self.execute('return game:GetService("Players").LocalPlayer.Character.HumanoidRootPart.Position')
        self.assertEqual(after['values'],before)
        self.assertEqual(after['movement_intents'],[])

    def test_impulses_are_bounded_local_intents(self):
        result=self.execute('''
local player=game:GetService("Players").LocalPlayer
local character=assert(player.Character)
local humanoid=assert(character:FindFirstChildOfClass("Humanoid"))
local root=assert(character:FindFirstChild("HumanoidRootPart"))
root:ApplyImpulse(Vector3.new(8, 0, -4))
root:ApplyImpulseAtPosition(Vector3.new(0, 4, 0), root.Position)
assert(not pcall(function() root:ApplyImpulse(Vector3.new(0/0,0,0)) end))
assert(not pcall(function() root:ApplyImpulseAtPosition(Vector3.zero, Vector3.zero, true) end))
return "queued"
''')
        intents=result['movement_intents']
        self.assertEqual([item['kind'] for item in intents],['Impulse','Impulse'])
        self.assertEqual([item['sequence'] for item in intents],[1,2])
        self.assertEqual(intents[0]['vector'],[8,0,-4])
        self.assertEqual(intents[1]['position'],[1,2,3])

    def test_physics_feedback_does_not_drain_queued_callbacks_or_intents(self):
        player=next(node for node in snapshot()['nodes'] if node['id']=='scope:player-1')
        character=player['properties']['Character']['$ref']
        humanoid=next(node for node in snapshot()['nodes']
                      if node.get('parent')==character and node['class_name']=='Humanoid')
        feedback=lambda name,value,transitions: {
            'humanoid_id': humanoid['id'],
            'state': {'name': name, 'value': value},
            'transitions': transitions, 'signals': []}
        def assert_feedback_response(response):
            self.assertTrue(response['ok'],response)
            self.assertTrue(response['persistent'],response)
            self.assertEqual(response['values'],[])
            for key in ('runtime_protected_integrity','runtime_thread_integrity'):
                self.assertIn(key,response)
                self.assertEqual(response[key].get('failures'),0,response)
        first=self.host.call({'op':'physics_feedback',
                              'feedback':feedback('Freefall',5,[{'name':'Freefall','value':5}])})
        assert_feedback_response(first)
        registered=self.execute('''
local player=game:GetService("Players").LocalPlayer
local character=assert(player.Character)
local humanoid=assert(character:FindFirstChildOfClass("Humanoid"))
local root=assert(character:FindFirstChild("HumanoidRootPart"))
humanoid.StateChanged:Connect(function(oldState,newState)
    assert(oldState==Enum.HumanoidStateType.Freefall)
    assert(newState==Enum.HumanoidStateType.Running)
    print("feedback callback ran")
    root:ApplyImpulse(Vector3.new(3,0,0))
end)
humanoid.FreeFalling:Connect(function(active)
    assert(active==false)
    print("boolean signal ran")
end)
return true
''')
        self.assertTrue(registered['ok'])
        second_feedback=feedback('Running',8,[{'name':'Running','value':8}])
        second_feedback['signals']=[{'name':'FreeFalling','active':False}]
        second=self.host.call({'op':'physics_feedback','feedback':second_feedback})
        assert_feedback_response(second)
        polled=self.host.call({'op':'poll','timeout_ms':100})
        self.assertTrue(polled['ok'],polled)
        self.assertIn('feedback callback ran',polled['output'])
        self.assertIn('boolean signal ran',polled['output'])
        self.assertTrue(any(intent['kind']=='Impulse' and intent['vector']==[3,0,0]
                            for intent in polled['movement_intents']))

    def test_datatypes_round_trip_through_attributes_clone_and_results(self):
        result=self.execute('''
local values={Color3.new(2,-1,.5),Vector2.new(3,4),UDim.new(.5,7),UDim2.new(.5,7,1,-2),
    NumberRange.new(2,5),Rect.new(4,5,1,2),BrickColor.new(21),NumberSequence.new(2,5),
    ColorSequence.new(Color3.new(1,0,0),Color3.new(0,0,1))}
getgenv().holder=Instance.new("Folder")
for i,v in values do holder:SetAttribute("v"..i,v);assert(holder:GetAttribute("v"..i)==v)end
local clone=holder:Clone()
for i,v in values do assert(clone:GetAttribute("v"..i)==v)end
return values[1],values[2],values[3],values[4],values[5],values[6],values[7],DateTime.fromUnixTimestampMillis(1234)
''')
        self.assertEqual(result['values'],[
            {'$color3':[2,-1,.5]},{'$vector2':[3,4]},{'$udim':[.5,7]},
            {'$udim2':[{'$udim':[.5,7]},{'$udim':[1,-2]}]},
            {'$number_range':[2,5]},{'$rect':[{'$vector2':[1,2]},{'$vector2':[4,5]}]},
            {'$brickcolor':21},{'$datetime':1234}])
        self.execute('getgenv().Color3={};return holder:GetAttribute("v1").R==2')

    def test_bindable_events_preserve_datatypes(self):
        self.execute('''
local event=Instance.new("BindableEvent")
getgenv().received=nil
event.Event:Connect(function(value)received=value end)
event:Fire(Color3.new(.25,.5,.75))
''')
        self.assertEqual(self.execute('return typeof(received),received.R,received.G,received.B')['values'],['Color3',.25,.5,.75])

    def test_json_rejects_an_incorrect_copied_receiver(self):
        self.assertEqual(self.execute('local encode=game:GetService("HttpService").JSONEncode;return pcall(function()encode(workspace,{})end)')['values'][0],False)

    def test_local_json_service_does_not_require_a_replicated_service(self):
        base=json.loads((ROOT/'tests/fixtures/world_snapshot.json').read_text())
        host=PersistentLuauHost(base);self.addCleanup(host.close)
        result=host.call({'op':'execute','source':'''getgenv().http=game:GetService("HttpService")
assert(game:FindService("HttpService")==http)
assert(client.propertyOrigin(http,"Name")=="local")
assert(client.propertyOrigin(http,"Parent")=="local")
assert(client.propertyOrigin(http,"ClassName")=="local")
return http:JSONDecode(http:JSONEncode({answer=42})).answer
'''})
        self.assertTrue(result['ok'],result)
        self.assertEqual(result['values'],[42])
        created=next(m['node'] for m in result['mutations'] if m['kind']=='create')
        self.assertEqual(created['class_name'],'HttpService')
        self.assertFalse(created['server_owned'])
        again=host.call({'op':'execute','source':'return http==game:GetService("HttpService")'})
        self.assertTrue(again['ok'],again)
        self.assertEqual(again['values'],[True])
        self.assertEqual(again['mutations'],[])

    def test_json_service_survives_legacy_overlay_without_local_id_collision(self):
        world,_=fixture();runtime=ClientScriptRuntime(lambda:world,123)
        created=runtime.execute('local f=Instance.new("Folder");f.Name="ExistingLocal";return true')
        self.assertTrue(created['ok'],created)
        result=runtime.execute('return game:GetService("HttpService"):JSONDecode("42")')
        self.assertTrue(result['ok'],result)
        self.assertEqual(result['values'],[42])
        result=runtime.execute('local h=game:FindService("HttpService");return h:JSONDecode("43"),client.propertyOrigin(h,"Name")')
        self.assertTrue(result['ok'],result)
        self.assertEqual(result['values'],[43,'local'])

    def test_movement_quota_is_reported_without_losing_vm(self):
        result=self.execute('''
local h=game:GetService("Players").LocalPlayer.Character:FindFirstChildOfClass("Humanoid")
for i=1,256 do h:Move(Vector3.zero)end
local ok=pcall(function()h:Move(Vector3.zero)end)
return ok
''')
        self.assertEqual(result['values'],[False])
        self.assertEqual(len(result['movement_intents']),256)
        self.assertEqual(self.execute('return 42')['values'],[42])

    def test_legacy_and_rust_hosts_agree_on_datatype_results(self):
        source='return Color3.new(2,-1,.5),Vector2.new(3,4),UDim2.fromOffset(2,4)'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);(path/'source.luau').write_text(source)
            (path/'snapshot.json').write_text(json.dumps(snapshot()))
            responses=[]
            for host in [HOST,RUST_HOST]:
                run=subprocess.run([str(host),'--source',str(path/'source.luau'),'--world-snapshot',str(path/'snapshot.json')],capture_output=True,timeout=7)
                response=json.loads(run.stdout);self.assertTrue(response['ok'],response)
                self.assertEqual(run.returncode,0)
                responses.append(response)
            stable_fields=('ok','values','output','task_errors')
            normalized=[{field:response.get(field, '' if field=='output' else [] if field=='task_errors' else None)
                         for field in stable_fields} for response in responses]
            self.assertEqual(normalized[0],normalized[1])

    def test_cpp_host_vector2_and_cframe_round_to_float32(self):
        # Engine datatypes store float32 components: 1.1/2.2/3.3 are not exact
        # in float32, so a double-precision host would return them unchanged.
        source='''
local v=Vector2.new(1.1,2.2)
assert(v.X~=1.1,"Vector2.X must round to float32")
assert(v.Y~=2.2,"Vector2.Y must round to float32")
local cf=CFrame.new(1.1,2.2,3.3)
assert(cf.Position.X~=1.1,"CFrame position must round to float32")
assert(Vector2.new(3,4).Magnitude==5)
assert(Vector2.new(3,4).Unit==Vector2.new(0.6,0.8))
assert(Vector2.new(3,4):Dot(Vector2.new(-2,5))==14)
return "float32 parity ok"
'''
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);(path/'source.luau').write_text(source)
            (path/'snapshot.json').write_text(json.dumps(snapshot()))
            run=subprocess.run([str(HOST),'--source',str(path/'source.luau'),'--world-snapshot',str(path/'snapshot.json')],capture_output=True,timeout=7)
            response=json.loads(run.stdout);self.assertTrue(response['ok'],response)
            self.assertEqual(run.returncode,0)
            self.assertEqual(response['values'],["float32 parity ok"])

    def test_luau_move_reaches_only_the_separate_local_preview(self):
        world,_=fixture();before=copy.deepcopy(world.instances)
        runtime=PersistentClientScriptRuntime(lambda:world,123);self.addCleanup(runtime.close)
        result=runtime.execute('game:GetService("Players").LocalPlayer.Character:FindFirstChildOfClass("Humanoid"):Move(Vector3.xAxis)')
        self.assertTrue(result['ok'],result)
        self.assertEqual(result['local_movement']['accepted_intents'],1)
        initial=result['local_movement']['predicted_position']
        preview=runtime.movement_preview.advance(world,123,runtime.movement_last_step+.25)
        self.assertEqual([preview['predicted_position'][0],preview['predicted_position'][2]],[initial[0]+4,initial[2]])
        self.assertFalse(preview['server_confirmed'])
        self.assertEqual(world.instances,before)

    def test_delayed_stop_preserves_preceding_local_motion(self):
        world,_=fixture();runtime=PersistentClientScriptRuntime(lambda:world,123)
        self.addCleanup(runtime.close)
        result=runtime.execute('''
local h=game:GetService("Players").LocalPlayer.Character:FindFirstChildOfClass("Humanoid")
h:Move(Vector3.xAxis)
task.delay(.1,function()h:Move(Vector3.zero)end)
''')
        self.assertTrue(result['ok'],result)
        initial=result['local_movement']['predicted_position']
        job_id=result['job_id']
        time.sleep(.13)
        result=runtime.poll(force=True)
        self.assertEqual(result['local_movement']['accepted_intents'],2)
        stopped=result['local_movement']['predicted_position']
        self.assertGreater(stopped[0],initial[0])
        self.assertEqual(runtime.status(job_id)['local_movement']['predicted_position'],stopped)
        time.sleep(.01)
        later=runtime.poll(force=True)['local_movement']['predicted_position']
        self.assertEqual([later[0],later[2]],[stopped[0],stopped[2]])


if __name__=='__main__':unittest.main()
