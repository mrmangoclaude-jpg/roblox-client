import copy
import json
from pathlib import Path
import time
import unittest
from unittest.mock import Mock

from local_runtime import RUST_HOST
from persistent_runtime import PersistentLuauHost, PersistentClientScriptRuntime
from test_world_snapshot import fixture
from world_snapshot import make_world_delta

ROOT=Path(__file__).resolve().parents[2]
SNAPSHOT=json.loads((ROOT/'tests/fixtures/world_snapshot.json').read_text())


@unittest.skipUnless(RUST_HOST.is_file(), 'build the Rust host first')
class PersistentRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.host=PersistentLuauHost(copy.deepcopy(SNAPSHOT))
        self.addCleanup(self.host.close)

    def execute(self,source,budget=1000):
        return self.host.call({'op':'execute','source':source,'timeout_ms':budget})

    def update(self,actions):
        return self.host.call({'op':'update','delta':{'version':1,'delta':True,'actions':actions},'timeout_ms':100})

    def test_globals_functions_shared_and_instance_identity_survive_commands(self):
        first=self.execute('''
getgenv().held=game:GetService("Players").LocalPlayer.Character:FindFirstChild("HumanoidRootPart")
function add(value)return value+40 end
shared.increment=2
local object=Instance.new("Folder",workspace);object.Name="PersistentObject"
return true
''')
        self.assertTrue(first['ok'],first)
        second=self.execute('return add(shared.increment),held==game:GetService("Players").LocalPlayer.Character:FindFirstChild("HumanoidRootPart"),workspace:FindFirstChild("PersistentObject")~=nil')
        self.assertTrue(second['ok'],second)
        self.assertEqual(second['values'],[42,True,True])

    def test_timers_survive_return_and_run_on_later_poll(self):
        first=self.execute('getgenv().count=0;task.delay(.01,function()count+=1 end);return "armed"')
        self.assertEqual(first['values'],['armed'])
        self.assertEqual(first['pending_tasks'],1)
        time.sleep(.025)
        self.host.call({'op':'poll','timeout_ms':20})
        self.assertEqual(self.execute('return count')['values'],[1])

    def test_waiting_job_completes_from_a_later_command(self):
        first=self.execute('getgenv().channel=Instance.new("BindableEvent");return channel.Event:Wait()')
        self.assertTrue(first['ok'],first)
        self.assertEqual(first['state'],'running')
        self.assertFalse(first['completed'])
        second=self.execute('channel:Fire(17,nil,"done");return "sent"')
        results={r['job_id']:r for r in second['completed_jobs']}
        self.assertEqual(results[first['job_id']]['values'],[17,None,'done'])
        self.assertEqual(second['values'],['sent'])

    def test_received_properties_reassert_values_and_fire_retained_connections(self):
        first=self.execute('''
getgenv().held=game:GetService("Players").LocalPlayer.Character:FindFirstChild("HumanoidRootPart")
getgenv().changes=0
held:GetPropertyChangedSignal("Anchored"):Connect(function()changes+=1 end)
held.Anchored=false
return held.Anchored
''')
        self.assertEqual(first['values'],[False])
        response=self.update([{'sequence':8,'kind':'set','id':'scope:root-1','fields':{'Anchored':True}}])
        self.assertTrue(response['ok'],response)
        second=self.execute('return held.Anchored,changes,client.propertyOrigin(held,"Anchored"),held==game:GetService("Players").LocalPlayer.Character:FindFirstChild("HumanoidRootPart")')
        self.assertEqual(second['values'],[True,2,'received',True])

    def test_ordered_intermediate_values_are_not_coalesced(self):
        response=self.update([{'sequence':8,'kind':'create','id':'scope:value','node':{
            'id':'scope:value','class_name':'IntValue','name':'Value','parent':'scope:workspace',
            'properties':{'Value':0,'Archivable':True}}}])
        self.assertTrue(response['ok'],response)
        self.execute('getgenv().values={};workspace:FindFirstChild("Value").Changed:Connect(function(value)table.insert(values,value)end)')
        response=self.update([{'sequence':9+i,'kind':'set','id':'scope:value','fields':{'Value':i+1}} for i in range(3)])
        self.assertTrue(response['ok'],response)
        self.assertEqual(self.execute('return table.concat(values,",")')['values'],['1,2,3'])

    def test_received_remote_event_reaches_a_previously_registered_handler(self):
        self.update([{'sequence':8,'kind':'create','id':'scope:remote','node':{
            'id':'scope:remote','class_name':'RemoteEvent','name':'Remote','parent':'scope:workspace','properties':{}}}])
        self.execute('getgenv().received=nil;workspace:FindFirstChild("Remote").OnClientEvent:Connect(function(value,empty,part)received={value=value,empty=empty==nil,part=part}end)')
        response=self.update([{'sequence':9,'kind':'event','id':'scope:remote','name':'OnClientEvent',
                               'arguments':[42,None,{'$ref':'scope:root-1'}]}])
        self.assertEqual(response['server_events'],1)
        self.assertEqual(response['unresolved_server_events'],0)
        result=self.execute('return received.value,received.empty,received.part.Name')
        self.assertEqual(result['values'],[42,True,'HumanoidRootPart'])

    def test_received_character_change_and_removal_keep_retained_handles_valid(self):
        self.execute('getgenv().added=nil;game:GetService("Players").LocalPlayer.CharacterAdded:Once(function(character)added=character end)')
        response=self.update([
            {'sequence':8,'kind':'create','id':'scope:new-character','node':{
                'id':'scope:new-character','class_name':'Model','name':'NewCharacter','parent':'scope:workspace','properties':{}}},
            {'sequence':9,'kind':'set','id':'scope:player-1','fields':{'Character':{'$ref':'scope:new-character'}}}])
        self.assertTrue(response['ok'],response)
        self.assertEqual(self.execute('return added.Name,added==game:GetService("Players").LocalPlayer.Character')['values'],['NewCharacter',True])
        self.update([{'sequence':10,'kind':'remove','id':'scope:new-character'}])
        self.assertEqual(self.execute('return added.Name,added.Parent==nil')['values'],['NewCharacter',True])

    def test_source_error_and_cpu_timeout_do_not_recreate_vm(self):
        pid=self.host.process.pid
        self.execute('getgenv().marker=123')
        bad=self.execute('local =')
        self.assertFalse(bad['ok'])
        loop=self.execute('while true do end',budget=25)
        self.assertFalse(loop['ok'],loop)
        self.assertTrue(loop['timed_out'],loop)
        self.assertEqual(self.execute('return marker')['values'],[123])
        self.assertEqual(self.host.process.pid,pid)

    def test_finished_tasks_are_collected_for_long_lived_vms(self):
        result=self.execute('local n=0;for i=1,5000 do task.spawn(function()n+=1 end)end;return n',budget=2000)
        self.assertTrue(result['ok'],result)
        self.assertEqual(result['values'],[5000])

    def drain_tasks(self, response):
        deadline=time.monotonic()+8
        while response['pending_tasks'] and time.monotonic()<deadline:
            self.assertTrue(response['ok'],response)
            self.assertFalse(response['task_errors'],response)
            time.sleep(.002)
            response=self.host.call({'op':'poll','timeout_ms':100})
        self.assertTrue(response['ok'],response)
        self.assertFalse(response['task_errors'],response)
        self.assertEqual(response['pending_tasks'],0,response)

    def test_received_event_burst_drains_in_order_without_exhausting_tasks(self):
        self.update([{'sequence':8,'kind':'create','id':'scope:burst','node':{
            'id':'scope:burst','class_name':'IntValue','name':'Burst','parent':'scope:workspace',
            'properties':{'Value':0}}}])
        armed=self.execute('''getgenv().seen=0
workspace:FindFirstChild("Burst").Changed:Connect(function(value)
    seen+=1;assert(value==seen,"event order changed")
end)''')
        self.assertTrue(armed['ok'],armed)
        response=self.update([{'sequence':9+i,'kind':'set','id':'scope:burst',
                               'fields':{'Value':i+1}} for i in range(5000)])
        self.drain_tasks(response)
        self.assertEqual(self.execute('return seen')['values'],[5000])

    def test_yielding_callback_burst_keeps_foreground_capacity_and_arguments(self):
        pid=self.host.process.pid
        response=self.execute('''getgenv().seen=0;getgenv().total=0
getgenv().burst=Instance.new("BindableEvent")
burst.Event:Connect(function(record,empty,value)
    task.wait(.01)
    assert(empty==nil and record.value==value,"event arguments lost")
    seen+=1;total+=value
end)
for i=1,3000 do burst:Fire({value=i},nil,i)end
return "queued"''',budget=2000)
        self.assertTrue(response['ok'],response)
        self.assertEqual(response['values'],['queued'])
        foreground=self.execute('getgenv().foreground=73;return foreground')
        self.assertTrue(foreground['ok'],foreground)
        self.assertEqual(foreground['values'],[73])
        self.drain_tasks(foreground)
        self.assertEqual(self.execute('return seen,total,foreground')['values'],[3000,4501500,73])
        self.assertEqual(self.host.process.pid,pid)

    def test_cancelled_ready_entries_survive_task_collection(self):
        response=self.execute('''getgenv().ran=0
for i=1,1500 do
    local pending=task.defer(function()error("cancelled task ran")end)
    task.cancel(pending)
    task.spawn(function()ran+=1 end)
end
return ran''',budget=2000)
        self.assertTrue(response['ok'],response)
        self.assertEqual(response['values'],[1500])
        self.drain_tasks(response)

    def test_close_reaps_the_supervisor(self):
        self.host.close()
        self.assertIsNotNone(self.host.process.poll())
        with self.assertRaises(RuntimeError):self.host.call({'op':'poll'})

    def test_wait_for_child_resumes_on_a_later_received_creation(self):
        waiting=self.execute('return workspace:WaitForChild("Arriving",1).Name')
        self.assertEqual(waiting['state'],'running')
        response=self.update([{'sequence':8,'kind':'create','id':'scope:arriving','node':{
            'id':'scope:arriving','class_name':'Folder','name':'Arriving','parent':'scope:workspace','properties':{}}}])
        results={r['job_id']:r for r in response['completed_jobs']}
        self.assertEqual(results[waiting['job_id']]['values'],['Arriving'])

    def test_wait_for_child_timeout_and_native_argument_rules(self):
        invalid=self.execute('return pcall(function()workspace:WaitForChild("Missing",0)end)')
        self.assertEqual(invalid['values'][0],False)
        waiting=self.execute('return workspace:WaitForChild("Missing",.005)==nil')
        job_id=waiting['job_id']
        completed=waiting if waiting.get('completed') else next(
            (item for item in waiting.get('completed_jobs', []) if item['job_id']==job_id), None)
        deadline=time.monotonic()+2
        while completed is None and time.monotonic()<deadline:
            response=self.host.call({'op':'poll','timeout_ms':20})
            completed=next((item for item in response.get('completed_jobs', [])
                            if item['job_id']==job_id), None)
        self.assertIsNotNone(completed, waiting)
        self.assertTrue(completed['ok'],completed)
        self.assertEqual(completed['values'],[True])

    def test_character_event_waits_for_its_instance_reference_to_resolve(self):
        self.execute('getgenv().added=nil;game:GetService("Players").LocalPlayer.CharacterAdded:Connect(function(character)assert(character:IsA("Model"));added=character end)')
        self.update([{'sequence':8,'kind':'set','id':'scope:player-1','fields':{'Character':{'$ref':'scope:later-model'}}}])
        self.assertEqual(self.execute('return added==nil')['values'],[True])
        response=self.update([{'sequence':9,'kind':'create','id':'scope:later-model','node':{
            'id':'scope:later-model','class_name':'Model','name':'Later','parent':'scope:workspace','properties':{}}}])
        self.assertFalse(response['task_errors'])
        self.assertEqual(self.execute('return added.Name')['values'],['Later'])


@unittest.skipUnless(RUST_HOST.is_file(), 'build the Rust host first')
class PersistentAdapterTests(unittest.TestCase):
    def test_update_callback_errors_remain_visible_after_the_following_poll(self):
        world,key=fixture();runtime=PersistentClientScriptRuntime(lambda:world,123)
        self.addCleanup(runtime.close)
        armed=runtime.execute('''
local held=game:GetService("Players").LocalPlayer.Character:FindFirstChild("HumanoidRootPart")
held:GetPropertyChangedSignal("Name"):Connect(function()error("receipt callback failed")end)
''')
        self.assertTrue(armed['ok'],armed)
        world.instances[key]['properties']['Name']=b'UpdatedFromServer'
        world.touch(key,['Name'])
        runtime.poll(force=True)
        self.assertEqual(runtime.stats['task_errors_total'],1)
        runtime.poll(force=True)
        self.assertEqual(runtime.stats['task_errors_total'],1)
        prior_revision=runtime.stats['world_revision']
        runtime._record({'ok':False,'values':[],'error':'example bounded error'})
        self.assertEqual(runtime.stats['world_revision'],prior_revision)
        self.assertEqual(runtime.stats['task_errors_total'],1)

    def test_receipt_journal_forwards_changes_without_mutating_wire_evidence(self):
        world,key=fixture();runtime=PersistentClientScriptRuntime(lambda:world,123)
        self.addCleanup(runtime.close)
        first=runtime.execute('getgenv().held=game:GetService("Players").LocalPlayer.Character:FindFirstChild("HumanoidRootPart");getgenv().names=0;held:GetPropertyChangedSignal("Name"):Connect(function()names+=1 end)')
        self.assertTrue(first['ok'],first)
        world.instances[key]['properties']['Name']=b'UpdatedFromServer'
        world.touch(key,['Name'])
        delta=make_world_delta(world,runtime.revision)
        self.assertEqual(delta['actions'][0]['fields']['Name'],'UpdatedFromServer')
        runtime.poll(force=True)
        second=runtime.execute('return held.Name,names')
        self.assertEqual(second['values'],['UpdatedFromServer',1])
        self.assertEqual(world.instances[key]['properties']['Name'],b'UpdatedFromServer')

    def test_world_update_falls_back_when_single_action_exceeds_delta_byte_budget(self):
        world, key = fixture()
        runtime = PersistentClientScriptRuntime(lambda: world, 123)
        self.addCleanup(runtime.close)
        self.assertTrue(runtime.execute('return 1')['ok'])
        world.instances[key]['properties']['Name'] = b'X' * (5 * 1024 * 1024)
        world.touch(key, ['Name'])
        delta, _, _, _ = runtime._world_update(world)
        self.assertEqual(len(delta['actions']), 1)
        self.assertEqual(delta['sequence'], world.revision)


class PersistentStatusTests(unittest.TestCase):
    @staticmethod
    def runtime():
        runtime=PersistentClientScriptRuntime(lambda:None,123)
        runtime.poll=Mock()
        runtime.host=Mock()
        runtime.results={}
        runtime.submitted={}
        runtime.movement_preview=None
        return runtime

    def test_observational_status_reads_cached_result_without_advancing(self):
        runtime=self.runtime()
        pending={'job_id':7,'ok':True,'completed':False,'state':'running'}
        runtime.submitted[7]=pending
        self.assertEqual(runtime.status(7,advance=False),{
            **pending,'persistent':True,'runtime_backend':'rust-persistent','queue_diagnostic':{}})
        runtime.results[7]={'job_id':7,'ok':True,'completed':True,
                           'state':'completed','values':[42]}
        self.assertEqual(runtime.status(7,advance=False)['values'],[42])
        runtime.poll.assert_not_called()
        runtime.host.call.assert_not_called()

    def test_observational_status_preserves_unknown_job_validation(self):
        runtime=self.runtime()
        with self.assertRaisesRegex(ValueError,'Unknown or expired script job'):
            runtime.status(99,advance=False)
        with self.assertRaisesRegex(ValueError,'job_id must be a positive integer'):
            runtime.status(0,advance=False)
        with self.assertRaisesRegex(ValueError,'advance must be a boolean'):
            runtime.status(1,advance='no')
        runtime.poll.assert_not_called()

    def test_default_status_still_advances_offline_jobs(self):
        runtime=self.runtime()
        runtime.submitted[8]={'job_id':8,'ok':True,'completed':False,'state':'running'}
        def advance(*,force):
            self.assertTrue(force)
            runtime.results[8]={'job_id':8,'ok':True,'completed':True,
                                'state':'completed','values':['done']}
        runtime.poll.side_effect=advance
        result=runtime.status(8)
        self.assertTrue(result['completed'])
        self.assertEqual(result['values'],['done'])
        runtime.poll.assert_called_once_with(force=True)
