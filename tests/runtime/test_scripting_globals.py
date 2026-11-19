"""Scripting compatibility through the compiled Luau scheduler and VM."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import test_motion_math as motion
import test_script_execution as script_execution

ROOT=Path(__file__).resolve().parents[2]


@unittest.skipUnless(motion.RUST_HOST.is_file(),'build the persistent worker first')
class ScriptingGlobalsTests(unittest.TestCase):
    setUp=motion.MotionMathTests.setUp
    execute=motion.MotionMathTests.execute

    def test_legacy_callbacks_are_deferred_return_nothing_and_receive_timing_arguments(self):
        self.execute('''
local results={}
local started=time()
local function callback(name)
 return function(...)
  local values=table.pack(...)
  assert(values.n==2 and type(values[1])=="number" and type(values[2])=="number")
  assert(values[1]>=.02 and values[2]>=values[1])
  results[name]=values
 end
end
assert(table.pack(spawn(callback("spawn"),1,nil,3)).n==0)
assert(table.pack(delay(.05,callback("delay"),4,nil,6)).n==0)
assert(next(results)==nil)
for _=1,100 do if results.spawn and results.delay then break end;task.wait(.005)end
assert(results.spawn and results.delay and time()>started)
''')

    def test_legacy_callback_waits_keep_normal_task_wait_return_count(self):
        self.execute('''
local finished=false
spawn(function(...)
 assert(select("#",...)==2)
 local result=table.pack(task.wait(.005));assert(result.n==1 and result[1]>=.005)
 local legacy=table.pack(wait(.005));assert(legacy.n==2)
 finished=true
end)
for _=1,100 do if finished then break end;task.wait(.005)end
assert(finished)
''')

    def test_ypcall_is_real_yieldable_pcall_and_preserves_nil_results(self):
        self.execute('''
assert(ypcall==pcall)
local result=table.pack(ypcall(function(a,b,c)
 task.wait(.005);return a,b,c
end,7,nil,9))
assert(result.n==4 and result[1] and result[2]==7 and result[3]==nil and result[4]==9)
local marker={}
local ok,errorValue=ypcall(function()task.wait(.005);error(marker)end)
assert(not ok and errorValue==marker)
assert(type(debug.info)=="function" and type(debug.traceback)=="function")
''')

    def test_time_advances_across_persistent_requests(self):
        first=self.execute('savedTime=time();return savedTime')['values'][0]
        second=self.execute('task.wait(.03);assert(time()>savedTime);return time()')['values'][0]
        self.assertGreater(second-first,.02)

    def test_cancel_plain_suspended_completed_and_failed_coroutines(self):
        self.execute('''
local ran=false
local suspended=coroutine.create(function()ran=true end)
assert(select("#",task.cancel(suspended))==0)
assert(coroutine.status(suspended)=="dead" and not coroutine.resume(suspended) and not ran)
assert(pcall(task.cancel,suspended))
local completed=coroutine.create(function()return 42 end);assert(coroutine.resume(completed))
assert(pcall(task.cancel,completed) and coroutine.status(completed)=="dead")
local failed=coroutine.create(function()error("expected coroutine failure")end)
assert(not coroutine.resume(failed));assert(pcall(task.cancel,failed))
assert(not pcall(task.cancel,coroutine.running()))
local parent=coroutine.running()
local child=coroutine.create(function()assert(not pcall(task.cancel,parent))end)
assert(coroutine.resume(child))
''')

    def test_cancel_scheduled_and_signal_waiting_tasks_keeps_them_stopped(self):
        self.execute('''
local ran=false
local deferred=task.defer(function()ran=true end);task.cancel(deferred)
local timer=task.delay(.03,function()ran=true end);task.cancel(timer)
local event=Instance.new("BindableEvent")
local waiter=task.spawn(function()event.Event:Wait();ran=true end)
task.cancel(waiter);event:Fire();task.wait(.05)
assert(not ran)
event:Destroy()
''')

    def test_memory_categories_accept_strings_and_numbers_without_losing_debug_functions(self):
        self.execute('''
assert(type(debug.info)=="function" and type(debug.traceback)=="function")
assert(select("#",debug.setmemorycategory("Worker"))==1) -- returns the previous tag, as in Roblox
local retained=table.create(1024,1)
task.wait(.005)
assert(select("#",debug.resetmemorycategory())==0)
assert(pcall(debug.setmemorycategory,17));debug.resetmemorycategory()
assert(not pcall(debug.setmemorycategory,true))
assert(not pcall(debug.setmemorycategory,{}))
assert(not pcall(debug.setmemorycategory,string.rep("x",257)))
assert(retained[1024]==1)
''')

    def test_invalid_legacy_arguments_are_rejected_before_scheduling(self):
        self.execute('''
-- Roblox accepts any callback here and schedules nothing when it is not a function; only a missing argument is an error.
for _,value in ipairs({true,{},coroutine.create(function()end)})do
 assert(pcall(spawn,value))
 assert(pcall(delay,.01,value))
end
assert(not pcall(spawn))
assert(not pcall(delay,.01))
local done=false;delay(-1,function()done=true end)
for _=1,100 do if done then break end;task.wait(.005)end
assert(done)
''')

    def test_require_accepts_relative_string_paths(self):
        self.execute('''
local root=Instance.new("Folder");root.Name="Pkg"
local sub=Instance.new("Folder");sub.Name="Sub";sub.Parent=root
local function module(name,parent,source)
 local m=Instance.new("ModuleScript");m.Name=name;m.Source=source;m.Parent=parent;return m
end
module("Sibling",sub,"return {tag='sibling'}")
module("Uncle",root,"return {tag='uncle'}")
local main=module("Main",sub,[[return {
 sibling=require("./Sibling"), uncle=require("../Uncle"), nested=require("../Sub/Sibling"),
 child=pcall(require,"@self/Missing"), absent=pcall(require,"./Absent"), alias=pcall(require,"@alias/x")}]])
module("Leaf",main,"return {tag='leaf'}")
local value=require(main)
assert(value.sibling.tag=="sibling" and value.uncle.tag=="uncle" and value.nested==value.sibling)
assert(not value.child and not value.absent and not value.alias)
local selfy=module("Selfy",sub,"return require('@self/Leaf')")
module("Leaf",selfy,"return {tag='selfleaf'}")
assert(require(selfy).tag=="selfleaf")
assert(not pcall(require,"./Sibling")) -- no calling module to resolve against here
''')

    def test_new_functions_are_available_inside_modules(self):
        self.execute('''
local module=Instance.new("ModuleScript")
module.Source=[[debug.setmemorycategory("ModuleWork")
local ok,value=ypcall(function()task.wait(.005);return 42 end)
assert(ok)
local result={answer=value,started=time()}
delay(.035,function(elapsed,stamp)result.ready=elapsed>0 and stamp>=elapsed end)
debug.resetmemorycategory()
return result]]
local value=require(module)
assert(value.answer==42 and require(module)==value)
for _=1,100 do if value.ready then break end;task.wait(.005)end
assert(value.ready)
module:Destroy()
''')

    def test_disabling_local_script_cancels_legacy_children(self):
        data=script_execution.snapshot()
        script_execution.add_script(data,'LegacyLifecycle','''
shared.legacyGate=Instance.new("BindableEvent")
spawn(function()shared.spawnReady=true;shared.legacyGate.Event:Wait();shared.spawnFinished=true end)
delay(.2,function()shared.delayFinished=true end)
task.wait(10)
''',kind='LocalScript',parent='gui')
        self.host.close();self.host=motion.PersistentLuauHost(data);self.addCleanup(self.host.close)
        self.execute('''
for _=1,100 do if shared.spawnReady then break end;task.wait(.005)end
assert(shared.spawnReady)
game:GetService("Players").LocalPlayer.PlayerGui.LegacyLifecycle.Disabled=true
task.wait(.015);shared.legacyGate:Fire();task.wait(.23)
assert(shared.spawnFinished==nil and shared.delayFinished==nil)
''')

    def test_authored_scripting_demo(self):
        result=self.execute((ROOT/'runtime/scripts/scripting_globals_demo.luau').read_text())
        self.assertEqual(result['values'][:3],['Scripting APIs completed',2,True])
        self.assertGreater(result['values'][3],0)

    @unittest.skipUnless(motion.STANDALONE.is_file(),'build the standalone worker first')
    def test_standalone_scripting_demo(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            (path/'source.luau').write_text((ROOT/'runtime/scripts/scripting_globals_demo.luau').read_text())
            (path/'world.json').write_text(json.dumps(motion.SNAPSHOT))
            result=subprocess.run([str(motion.STANDALONE),'--source',str(path/'source.luau'),
                '--world-snapshot',str(path/'world.json'),'--timeout-ms','2000'],capture_output=True,timeout=10)
            body=json.loads(result.stdout)
            self.assertEqual(result.returncode,0,body.get('error'))
            self.assertTrue(body['ok'],body.get('error'))
            self.assertFalse(body.get('task_errors'),body.get('task_errors'))
            self.assertEqual(body['values'][:3],['Scripting APIs completed',2,True])


if __name__=='__main__':unittest.main()
