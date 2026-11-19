"""Constructor-default APIs through both compiled native workers."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import test_cframe_transforms as transforms
from persistent_runtime import PersistentLuauHost

ROOT=Path(__file__).resolve().parents[2]


class PropertyDefaultsTests(unittest.TestCase):
    run_script=transforms.CFrameTransformTests.run_script

    def test_primitives_compare_with_code_defaults_and_reset_normally(self):
        self.run_script('''
local p=Instance.new("Part")
for _,key in ipairs({"Anchored","Transparency","Archivable","CanCollide"})do
 assert(not p:IsPropertyModified(key),key)
end
p.Anchored=true;p.Transparency=.5;p.CanCollide=false
assert(p:IsPropertyModified("Anchored") and p:IsPropertyModified("Transparency"))
assert(p:IsPropertyModified("CanCollide"))
assert(p:ResetPropertyToDefault("Transparency")==nil)
p:ResetPropertyToDefault("Anchored");p:ResetPropertyToDefault("CanCollide")
assert(p.Transparency==0 and not p.Anchored and p.CanCollide)
assert(not p:IsPropertyModified("Transparency") and not p:IsPropertyModified("Anchored"))
p.Transparency=.5;p.Transparency=0
assert(not p:IsPropertyModified("Transparency"))
''')

    def test_transform_resets_keep_position_rotation_and_cframe_consistent(self):
        self.run_script('''
local p=Instance.new("Part")
p.CFrame=CFrame.new(4,5,6)*CFrame.Angles(.2,.4,.1)
assert(p:IsPropertyModified("Position") and p:IsPropertyModified("CFrame"))
local rotation=p.CFrame.Rotation
p:ResetPropertyToDefault("Position")
vec(p.Position,Vector3.zero);frame(p.CFrame.Rotation,rotation)
assert(not p:IsPropertyModified("Position") and p:IsPropertyModified("Orientation"))
p:ResetPropertyToDefault("Orientation")
frame(p.CFrame,CFrame.identity)
assert(not p:IsPropertyModified("CFrame"))
p.CFrame=CFrame.new(20,40,60)*CFrame.Angles(1,2,3)
p:ResetPropertyToDefault("CFrame")
frame(p.CFrame,CFrame.identity);vec(p.Position,Vector3.zero);vec(p.Orientation,Vector3.zero)
''')

    def test_gui_and_color_datatypes_restore_without_using_script_globals(self):
        self.run_script('''
local label=Instance.new("TextLabel")
local size=label.Size
label.Text="Changed";label.Size=UDim2.new(.5,30,.25,20);label.Visible=false;label.Rotation=37
assert(label:IsPropertyModified("Text") and label:IsPropertyModified("Size"))
label:ResetPropertyToDefault("Text");label:ResetPropertyToDefault("Size")
label:ResetPropertyToDefault("Visible");label:ResetPropertyToDefault("Rotation")
assert(label.Text=="Label" and label.Size==size and label.Visible and label.Rotation==0)
assert(not label:IsPropertyModified("Size") and not label:IsPropertyModified("Text"))
local p=Instance.new("Part");local original=p.Color
p.Color=Color3.new(1,0,0)
assert(p:IsPropertyModified("Color"))
Color3=nil;UDim2=nil
p:ResetPropertyToDefault("Color");label:ResetPropertyToDefault("Size")
assert(p.Color==original and not p:IsPropertyModified("Color"))
''')

    def test_name_parent_and_deprecated_archivable_alias(self):
        self.run_script('''
local folder=Instance.new("Folder",workspace)
assert(not folder:IsPropertyModified("Name") and folder:IsPropertyModified("Parent"))
folder.Name="Changed";folder.archivable=false
assert(folder:IsPropertyModified("Name") and folder:IsPropertyModified("archivable"))
folder:ResetPropertyToDefault("Name");folder:ResetPropertyToDefault("archivable")
assert(folder.Name=="Folder" and folder.Archivable)
assert(not folder:IsPropertyModified("Name") and not folder:IsPropertyModified("Archivable"))
folder:ResetPropertyToDefault("Parent")
assert(folder.Parent==nil and not folder:IsPropertyModified("Parent"))
''')

    def test_instance_reference_defaults_restore_nil(self):
        self.run_script('''
local model=Instance.new("Model")
local part=Instance.new("Part",model)
assert(not model:IsPropertyModified("PrimaryPart"))
model.PrimaryPart=part
assert(model:IsPropertyModified("PrimaryPart"))
model:ResetPropertyToDefault("PrimaryPart")
assert(model.PrimaryPart==nil and not model:IsPropertyModified("PrimaryPart"))
''')

    def test_reset_uses_normal_change_signals_and_equal_reset_does_not_repeat_them(self):
        self.run_script('''
local p=Instance.new("Part");p.Transparency=.5
local changed=0
p:GetPropertyChangedSignal("Transparency"):Connect(function()changed+=1 end)
p:ResetPropertyToDefault("Transparency");task.wait(0)
assert(changed==1 and p.Transparency==0)
p:ResetPropertyToDefault("Transparency");task.wait(0)
assert(changed==1)
''')

    def test_queries_are_read_only_and_received_values_use_the_code_default(self):
        baseline=self.run_script('')
        result=self.run_script('''
local p=game:GetService("Players").LocalPlayer.Character.HumanoidRootPart
assert(p:IsPropertyModified("Anchored"))
assert(p:IsPropertyModified("Name"))
assert(not p:IsPropertyModified("ClassName"))
''')
        for before,after in zip(baseline,result):self.assertEqual(before.get('mutations'),after.get('mutations'))

    def test_unreceived_current_value_stays_unknown_but_reset_creates_a_local_override(self):
        snapshot=copy.deepcopy(transforms.SNAPSHOT)
        root=next(node for node in snapshot['nodes'] if node['id']=='scope:root-1')
        root['properties'].pop('Anchored',None)
        self.run_script('''
local p=game:GetService("Players").LocalPlayer.Character.HumanoidRootPart
assert(not pcall(p.IsPropertyModified,p,"Anchored"))
p:ResetPropertyToDefault("Anchored")
assert(not p.Anchored and not p:IsPropertyModified("Anchored"))
assert(client.propertyOrigin(p,"Anchored")=="local")
''',snapshot)

    def test_unavailable_defaults_readonly_fields_and_bad_arguments_are_rejected(self):
        self.run_script('''
local p=Instance.new("Part")
for _,method in ipairs({p.IsPropertyModified,p.ResetPropertyToDefault})do
 for _,key in ipairs({"", "MissingProperty", "Name"..string.char(0).."bad", "OnClientInvoke"})do
  assert(not pcall(method,p,key))
 end
 assert(not pcall(method,{},"Name"))
 assert(not pcall(method,p,{}))
 -- Studio ignores surplus arguments to IsPropertyModified
 if method==p.ResetPropertyToDefault then assert(not pcall(method,p,"Name",true)) else assert(pcall(method,p,"Name",true)) end
end
assert(not pcall(p.ResetPropertyToDefault,p,"ClassName"))
assert(not pcall(p.ResetPropertyToDefault,p,"Mass"))
local trail=Instance.new("Trail")
assert(not pcall(trail.ResetPropertyToDefault,trail,"Color"))
assert(not pcall(workspace.ResetPropertyToDefault,workspace,"Gravity"))
assert(p.ClassName=="Part" and p.Name=="Part")
''')

    def test_copied_methods_use_the_passed_receiver_and_clones_keep_values(self):
        self.run_script('''
local first=Instance.new("Part");local second=Instance.new("Part")
second.Transparency=.7
assert(first.IsPropertyModified(second,"Transparency"))
local clone=second:Clone()
assert(clone:IsPropertyModified("Transparency"))
first.ResetPropertyToDefault(clone,"Transparency")
assert(not clone:IsPropertyModified("Transparency"))
assert(second:IsPropertyModified("Transparency") and not first:IsPropertyModified("Transparency"))
''')

    def test_received_updates_refresh_results_in_the_existing_vm(self):
        host=PersistentLuauHost(copy.deepcopy(transforms.SNAPSHOT));self.addCleanup(host.close)
        def execute(source):
            result=host.call({'op':'execute','source':source,'timeout_ms':1000})
            self.assertTrue(result['ok'],result);self.assertFalse(result.get('task_errors'),result)
        execute('p=game:GetService("Players").LocalPlayer.Character.HumanoidRootPart;assert(p:IsPropertyModified("Anchored"))')
        result=host.call({'op':'update','delta':{'version':1,'delta':True,'sequence':8,'actions':[
            {'sequence':8,'kind':'set','id':'scope:root-1','fields':{'Anchored':False}}]}})
        self.assertTrue(result['ok'],result)
        execute('assert(not p:IsPropertyModified("Anchored"));p:ResetPropertyToDefault("Transparency");assert(not p:IsPropertyModified("Transparency"))')
        result=host.call({'op':'update','delta':{'version':1,'delta':True,'sequence':9,'actions':[
            {'sequence':9,'kind':'set','id':'scope:root-1','fields':{'Transparency':.2}}]}})
        self.assertTrue(result['ok'],result)
        execute('assert(p.Transparency==.2 and p:IsPropertyModified("Transparency"))')

    def test_demo_runs_in_both_workers(self):
        with tempfile.TemporaryDirectory(prefix='property-defaults-demo-') as directory:
            snapshot=Path(directory)/'snapshot.json';snapshot.write_text(json.dumps(transforms.SNAPSHOT))
            for host in transforms.HOSTS:
                with self.subTest(host=host.name):
                    result=subprocess.run([str(host),'--source',str(ROOT/'runtime/scripts/property_defaults_demo.luau'),
                                           '--world-snapshot',str(snapshot)],capture_output=True,text=True,timeout=10)
                    self.assertEqual(result.returncode,0,result.stderr)
                    body=json.loads(result.stdout);self.assertTrue(body['ok'],body)
                    self.assertEqual(body['values'],['Property defaults restored'])


if __name__=='__main__':unittest.main()
