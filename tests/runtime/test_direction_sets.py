"""Axes/Faces scripting, local transport, and handle properties in both workers."""
import copy
import json
import subprocess
from pathlib import Path
import unittest

import test_cframe_transforms as transforms
import test_motion_math as motion

ROOT=Path(__file__).resolve().parents[2]


class DirectionSetTests(unittest.TestCase):
    run_script=transforms.CFrameTransformTests.run_script

    def snapshot(self,axes=5,faces=33):
        data=copy.deepcopy(transforms.SNAPSHOT)
        for name,cls,key,value in [('Arcs','ArcHandles','Axes',{'$axes':axes}),
                                    ('Handles','Handles','Faces',{'$faces':faces})]:
            data['nodes'].append({'id':'direction:'+name,'class_name':cls,'name':name,
                                  'parent':'scope:workspace','properties':{key:value}})
        return data

    def test_every_axis_subset_and_face_alias(self):
        self.run_script('''
local axes={Enum.Axis.X,Enum.Axis.Y,Enum.Axis.Z}
local names={"X","Y","Z"}
local handles=Instance.new("ArcHandles")
for mask=0,7 do
 local args={}
 for i=1,3 do if bit32.btest(mask,2^(i-1))then table.insert(args,axes[i])end end
 local value=Axes.new(table.unpack(args))
 assert(typeof(value)=="Axes")
 for i,name in ipairs(names)do assert(value[name]==bit32.btest(mask,2^(i-1)))end
 assert(value.Left==value.X and value.Right==value.X)
 assert(value.Top==value.Y and value.Bottom==value.Y)
 assert(value.Front==value.Z and value.Back==value.Z)
 assert(value==Axes.new(table.unpack(args)))
 handles.Axes=value;assert(handles.Axes==value)
end
assert(Axes.new()~=Axes.new(Enum.Axis.X))
''')

    def test_every_face_subset_has_independent_components(self):
        self.run_script('''
local names={"Right","Top","Back","Left","Bottom","Front"}
local handles=Instance.new("Handles")
for mask=0,63 do
 local args={}
 for i,name in ipairs(names)do if bit32.btest(mask,2^(i-1))then table.insert(args,Enum.NormalId[name])end end
 local value=Faces.new(table.unpack(args))
 assert(typeof(value)=="Faces")
 for i,name in ipairs(names)do assert(value[name]==bit32.btest(mask,2^(i-1)))end
 assert(value==Faces.new(table.unpack(args)))
 handles.Faces=value;assert(handles.Faces==value)
end
assert(Faces.new()~=Faces.new(Enum.NormalId.Front))
assert(Axes.new()~=Faces.new())
''')

    def test_normal_ids_convert_to_axes_and_duplicate_inputs_are_idempotent(self):
        self.run_script('''
for _,face in ipairs(Enum.NormalId:GetEnumItems())do
 local axis=Enum.Axis:GetEnumItems()[face.Value%3+1]
 assert(Axes.new(face)==Axes.new(axis))
 assert(Axes.new(axis,face,axis,face)==Axes.new(axis))
 assert(Faces.new(face,face)==Faces.new(face))
end
assert(Axes.new(Enum.NormalId.Top,Enum.Axis.Z,Enum.NormalId.Left)==Axes.new(Enum.Axis.X,Enum.Axis.Y,Enum.Axis.Z))
''')

    def test_faces_silently_ignores_non_normal_ids(self):
        self.run_script('''
-- Verified on a live client: non-enum values are ignored, but an enum item
-- from the WRONG enum is an error ("Faces.new expects Enum.NormalId inputs").
local expected=Faces.new(Enum.NormalId.Top,Enum.NormalId.Left)
assert(Faces.new(nil,false,1,"Top",{},Vector3.zero,Enum.NormalId.Top,
 Enum.NormalId.Left)==expected)
for _,wrong in ipairs({Enum.Axis.Y,Enum.EasingStyle.Linear})do
 local ok,err=pcall(Faces.new,wrong)
 assert(not ok and tostring(err):find('Faces.new expects Enum.NormalId inputs',1,true))
end
local many=table.create(100,Enum.NormalId.Top)
assert(Faces.new(table.unpack(many))==Faces.new(Enum.NormalId.Top))
''')

    def test_axes_validation_and_immutable_libraries_and_members(self):
        self.run_script('''
-- Real clients silently ignore arguments that are not Enum.Axis/Enum.NormalId
-- items, and accept repeated items past six (deduplicated into the bit mask).
for _,ignored in ipairs({false,1,"X",{},Vector3.zero,Faces.new(),nil})do
 local value=Axes.new(ignored)
 assert(typeof(value)=="Axes" and not value.X and not value.Y and not value.Z)
end
assert(Axes.new(Enum.Axis.X,Enum.Axis.X,Enum.Axis.X,Enum.Axis.X,Enum.Axis.X,Enum.Axis.X,Enum.Axis.X)==Axes.new(Enum.Axis.X))
-- Real clients reject EnumItems of a different enum type with
-- "Axes.new expects Enum.Axis or Enum.NormalId inputs"; Rove currently ignores
-- those, so that case is tracked separately and is not asserted here.
for _,value in ipairs({Axes.new(),Faces.new()})do
 assert(not pcall(function()value.Top=true end))
 assert(not pcall(function()return value.Unknown end))
 assert(not pcall(function()return value["Top\\0suffix"]end))
end
assert(not pcall(function()Axes.new=function()end end))
assert(not pcall(function()Faces.new=function()end end))
''')

    def test_handle_properties_validate_type_and_clone(self):
        results=self.run_script('''
local arcs,handles=Instance.new("ArcHandles"),Instance.new("Handles")
local axes,faces=Axes.new(Enum.Axis.Y),Faces.new(Enum.NormalId.Front,Enum.NormalId.Left)
arcs.Axes=axes;handles.Faces=faces
assert(arcs.Axes==axes and handles.Faces==faces)
assert(arcs:Clone().Axes==axes and handles:Clone().Faces==faces)
for _,bad in ipairs({faces,1,"Y",{},Enum.Axis.Y})do
 assert(not pcall(function()arcs.Axes=bad end));assert(arcs.Axes==axes)
end
for _,bad in ipairs({axes,1,"Front",{},Enum.NormalId.Front})do
 assert(not pcall(function()handles.Faces=bad end));assert(handles.Faces==faces)
end
assert(not pcall(function()arcs.Axes=nil end))
assert(not pcall(function()handles.Faces=nil end))
''')
        for result in results:
            writes={m['property']:m['value'] for m in result['mutations'] if m.get('kind')=='set'}
            self.assertEqual(writes['Axes'],{'$axes':2})
            self.assertEqual(writes['Faces'],{'$faces':40})

    def test_handle_property_change_signals_preserve_typed_values(self):
        self.run_script('''
local arcs=Instance.new("ArcHandles");arcs.Axes=Axes.new()
local count=0
arcs:GetPropertyChangedSignal("Axes"):Connect(function()
 count+=1;assert(arcs.Axes==Axes.new(Enum.Axis.X))
end)
arcs.Axes=Axes.new(Enum.Axis.X);task.wait(0)
assert(count==1)
arcs.Axes=Axes.new(Enum.Axis.X);task.wait(0)
assert(count==1)
''')

    def test_uncaptured_handle_defaults_stay_unavailable(self):
        self.run_script('''
local arcs,handles=Instance.new("ArcHandles"),Instance.new("Handles")
assert(not pcall(function()return arcs.Axes end))
assert(not pcall(function()return handles.Faces end))
assert(client.propertyOrigin(arcs,"Axes")=="unavailable")
assert(not pcall(function()arcs:ResetPropertyToDefault("Axes")end))
arcs.Axes=Axes.new();assert(client.propertyOrigin(arcs,"Axes")=="local")
''')

    def test_attributes_reject_unsupported_direction_sets(self):
        results=self.run_script('''
local folder=Instance.new("Folder")
for _,value in ipairs({Axes.new(),Faces.new()})do
 assert(not pcall(function()folder:SetAttribute("Direction",value)end))
 assert(folder:GetAttribute("Direction")==nil)
end
''')
        for result in results:
            self.assertFalse([m for m in result['mutations'] if m.get('kind')=='attribute'])

    def test_received_values_restore_even_after_global_replacement(self):
        self.run_script('''
local axes,faces=Axes.new(Enum.Axis.X,Enum.Axis.Z),Faces.new(Enum.NormalId.Right,Enum.NormalId.Front)
Axes={new=function()error("overridden")end};Faces={new=function()error("overridden")end}
assert(workspace.Arcs.Axes==axes)
assert(workspace.Handles.Faces==faces)
assert(typeof(workspace.Arcs.Axes)=="Axes" and typeof(workspace.Handles.Faces)=="Faces")
''',self.snapshot())

    def test_malformed_received_masks_fail_without_forging_values(self):
        for axes,faces in [(-1,64),(8,-1),(1.5,2.5),("1",True),([],{}),(2**64-1,2**64-1)]:
            with self.subTest(axes=axes,faces=faces):
                self.run_script('''
assert(not pcall(function()return workspace.Arcs.Axes end))
assert(not pcall(function()return workspace.Handles.Faces end))
local a=Axes.new(Enum.Axis.Y);workspace.Arcs.Axes=a;assert(workspace.Arcs.Axes==a)
''',self.snapshot(axes,faces))

    def test_demo_runs_in_both_workers(self):
        for host in transforms.HOSTS:
            with self.subTest(host=host.name):
                result=subprocess.run([str(host),'--source',str(ROOT/'runtime/scripts/direction_sets_demo.luau'),
                    '--world-snapshot',str(ROOT/'tests/fixtures/world_snapshot.json')],capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stderr)
                body=json.loads(result.stdout)
                self.assertTrue(body['ok'],body)
                self.assertEqual(body['values'],[True,True,False,True])


@unittest.skipUnless(motion.RUST_HOST.is_file(),'build the persistent worker first')
class DirectionSetPersistentTests(unittest.TestCase):
    setUp=motion.MotionMathTests.setUp
    execute=motion.MotionMathTests.execute

    def test_bindable_arguments_and_nested_return_values_remain_typed(self):
        result=self.execute('''
local a,f=Axes.new(Enum.Axis.X,Enum.Axis.Z),Faces.new(Enum.NormalId.Bottom)
local fn=Instance.new("BindableFunction")
fn.OnInvoke=function(payload)
 assert(payload.axes==a and payload.faces[1]==f)
 return payload.faces[1],{axes=payload.axes}
end
local returned,nested=fn:Invoke({axes=a,faces={f}})
assert(typeof(returned)=="Faces" and returned==f and nested.axes==a)
return a,f
''')
        self.assertEqual(result['values'],[{'$axes':5},{'$faces':16}])

    def test_local_values_survive_later_script_jobs(self):
        self.execute('''getgenv().arcs=Instance.new("ArcHandles")
arcs.Axes=Axes.new(Enum.Axis.X,Enum.Axis.Y)''')
        result=self.execute('assert(arcs.Axes==Axes.new(Enum.Axis.X,Enum.Axis.Y));return arcs.Axes')
        self.assertEqual(result['values'],[{'$axes':3}])

    def test_received_delta_replaces_local_value_and_emits_typed_change(self):
        created=self.host.call({'op':'update','delta':{'version':1,'delta':True,'actions':[
            {'sequence':100,'kind':'create','id':'direction:arcs','node':{
                'id':'direction:arcs','class_name':'ArcHandles','name':'Arcs',
                'parent':'scope:workspace','properties':{'Axes':{'$axes':1}}}}]},'timeout_ms':100})
        self.assertTrue(created['ok'],created)
        self.execute('''
getgenv().arcs=workspace.Arcs
assert(arcs.Axes==Axes.new(Enum.Axis.X))
arcs.Axes=Axes.new(Enum.Axis.Y)
getgenv().seen={}
arcs:GetPropertyChangedSignal("Axes"):Connect(function()table.insert(seen,arcs.Axes)end)
''')
        update=self.host.call({'op':'update','delta':{'version':1,'delta':True,'actions':[
            {'sequence':101,'kind':'set','id':'direction:arcs','fields':{'Axes':{'$axes':5}}}]},'timeout_ms':100})
        self.assertTrue(update['ok'],update)
        self.assertFalse(update.get('task_errors'),update)
        self.execute('''
assert(arcs.Axes==Axes.new(Enum.Axis.X,Enum.Axis.Z))
assert(#seen==1 and seen[1]==arcs.Axes)
assert(client.propertyOrigin(arcs,"Axes")=="received")
''')


if __name__=='__main__':unittest.main()
