"""Public Font scripting and text-property integration in native Luau workers."""
import copy
import json
import subprocess
from pathlib import Path
import unittest

import test_cframe_transforms as transforms
import test_motion_math as motion

ROOT=Path(__file__).resolve().parents[2]
FAMILIES=json.loads((ROOT/'tests/fixtures/references/font-families.json').read_text())


def font(family='SourceSansPro',weight=400,style=0):
    return {'$font':{'family':'rbxasset://fonts/families/'+family+'.json','weight':weight,'style':style}}


class FontValueTests(unittest.TestCase):
    run_script=transforms.CFrameTransformTests.run_script

    def snapshot(self,properties):
        data=copy.deepcopy(transforms.SNAPSHOT)
        data['nodes'].append({'id':'font:label','class_name':'TextLabel','name':'FontLabel',
                              'parent':'scope:workspace','properties':properties})
        return data

    def test_all_legacy_families_match_the_published_family_table(self):
        cases=','.join('['+json.dumps(key)+']='+json.dumps(value) for key,value in FAMILIES.items())
        self.run_script('local expected={'+cases+'''}
local count=0
for _,item in ipairs(Enum.Font:GetEnumItems())do
 if item~=Enum.Font.Unknown then
  local value=Font.fromEnum(item)
  assert(typeof(value)=="Font" and value.Family==expected[item.Name],item.Name)
  count+=1
 end
end
assert(count==52)
assert(not pcall(Font.fromEnum,Enum.Font.Unknown))
''')

    def test_legacy_weight_and_style_variants(self):
        self.run_script('''
local expected={SourceSansLight=Enum.FontWeight.Light,SourceSansSemibold=Enum.FontWeight.SemiBold,
 SourceSansBold=Enum.FontWeight.Bold,GothamMedium=Enum.FontWeight.Medium,GothamBlack=Enum.FontWeight.Heavy,
 BuilderSansMedium=Enum.FontWeight.Medium,BuilderSansBold=Enum.FontWeight.Bold,
 BuilderSansExtraBold=Enum.FontWeight.ExtraBold,ArimoBold=Enum.FontWeight.Bold,ArialBold=Enum.FontWeight.Bold}
for name,weight in pairs(expected)do assert(Font.fromEnum(Enum.Font[name]).Weight==weight,name)end
assert(Font.fromEnum(Enum.Font.SourceSansItalic).Style==Enum.FontStyle.Italic)
assert(Font.fromEnum(Enum.Font.SourceSans).Style==Enum.FontStyle.Normal)
assert(Font.fromEnum(Enum.Font.SourceSansItalic).Weight==Enum.FontWeight.Regular)
''')

    def test_constructors_defaults_and_exact_asset_ids(self):
        self.run_script('''
local f=Font.new("rbxasset://fonts/families/BuilderSans.json")
assert(f.Family=="rbxasset://fonts/families/BuilderSans.json")
assert(f.Weight==Enum.FontWeight.Regular and f.Style==Enum.FontStyle.Normal and not f.Bold)
assert(f==Font.fromName("BuilderSans"))
assert(Font.new(f.Family,nil,nil)==f)
local bold=Font.fromName("BuilderSans",Enum.FontWeight.Bold,Enum.FontStyle.Italic)
assert(bold.Weight==Enum.FontWeight.Bold and bold.Style==Enum.FontStyle.Italic)
assert(Font.fromId(1234567890123).Family=="rbxassetid://1234567890123")
assert(Font.fromId(9007199254740991).Family=="rbxassetid://9007199254740991")
assert(Font.fromId(0).Family=="rbxassetid://0")
assert(Font.fromId(42,Enum.FontWeight.Heavy,Enum.FontStyle.Italic)==Font.new("rbxassetid://42",Enum.FontWeight.Heavy,Enum.FontStyle.Italic))
assert(Font.fromName("A-z_09").Family=="rbxasset://fonts/families/A-z_09.json")
''')

    def test_all_weight_style_pairs_and_bold_threshold(self):
        self.run_script('''
local names={"Thin","ExtraLight","Light","Regular","Medium","SemiBold","Bold","ExtraBold","Heavy"}
for i,name in ipairs(names)do
 local weight=Enum.FontWeight[name];assert(weight.Value==i*100)
 assert(Enum.FontWeight:FromValue(i*100)==weight and Enum.FontWeight:FromName(name)==weight)
 for _,style in ipairs(Enum.FontStyle:GetEnumItems())do
  local value=Font.new("rbxassetid://1",weight,style)
  assert(value.Weight==weight and value.Style==style and value.Bold==(i>=6))
 end
end
assert(Enum.FontStyle.Normal.Value==0 and Enum.FontStyle.Italic.Value==1)
''')

    def test_font_members_are_mutable_and_bold_updates_weight(self):
        self.run_script('''
local value=Font.fromName("BuilderSans")
local alias=value
alias.Weight=Enum.FontWeight.SemiBold;assert(value.Bold)
value.Bold=false;assert(value.Weight==Enum.FontWeight.Regular)
value.Bold=true;assert(value.Weight==Enum.FontWeight.Bold)
value.Weight=Enum.FontWeight.Heavy;assert(value.Bold)
value.Style=Enum.FontStyle.Italic;assert(value.Style==Enum.FontStyle.Italic)
value.Family="rbxassetid://7";assert(value.Family=="rbxassetid://7")
assert(value==Font.new("rbxassetid://7",Enum.FontWeight.Heavy,Enum.FontStyle.Italic))
assert(value~=Font.new("rbxassetid://7",Enum.FontWeight.Regular,Enum.FontStyle.Italic))
assert(not pcall(function()Font.new=function()end end))
''')

    def test_invalid_constructors_are_rejected(self):
        self.run_script('''
assert(not pcall(Font.new))
-- Real clients coerce a numeric family argument to its string form.
assert(Font.new(1).Family=="1")
for _,bad in ipairs({false,{},Enum.Font.SourceSans})do assert(not pcall(Font.new,bad))end
for _,bad in ipairs({"two words","../BuilderSans","A/B","A.B","A\\0B","",string.rep("a",5000)})do
 assert(not pcall(Font.fromName,bad))
end
for _,bad in ipairs({-1,1.5,math.huge,-math.huge,0/0,9007199254740992,"42",true,{}})do
 assert(not pcall(Font.fromId,bad))
end
for _,bad in ipairs({1,"SourceSans",{},Enum.Axis.X,Enum.FontWeight.Bold})do assert(not pcall(Font.fromEnum,bad))end
assert(not pcall(Font.fromEnum,nil))
for _,ctor in ipairs({Font.new,Font.fromName,Font.fromId})do
 local first=ctor==Font.fromId and 42 or "BuilderSans"
 assert(not pcall(ctor,first,700))
 assert(not pcall(ctor,first,Enum.FontStyle.Italic))
 assert(not pcall(ctor,first,Enum.FontWeight.Bold,Enum.FontWeight.Bold))
end
''')

    def test_bad_member_writes_do_not_change_the_font(self):
        self.run_script('''
local value=Font.fromName("BuilderSans")
local expected=Font.fromName("BuilderSans")
-- Real clients coerce numeric Family writes to their string form.
assert(pcall(function()value.Family=42 end))
assert(value.Family=="42")
value=Font.fromName("BuilderSans")
assert(value==expected)
-- Real clients accept NUL-containing and very long families (truncating at
-- NUL); Rove still rejects them, so those cases are tracked separately.
for _,write in ipairs({function()value.Family="A\\0B"end,
 function()value.Family=string.rep("a",5000)end,function()value.Weight=700 end,
 function()value.Weight=Enum.FontStyle.Normal end,function()value.Style=Enum.FontWeight.Bold end,
 function()value.Bold=1 end,function()value.Unknown=true end,
 function()value["Family\\0ignored"]="rbxassetid://9"end})do
 assert(not pcall(write));assert(value==expected)
end
assert(not pcall(function()return value.Unknown end))
''')

    def test_legacy_assignment_updates_all_three_text_classes(self):
        self.run_script('''
for _,class in ipairs({"TextLabel","TextButton","TextBox"})do
 local label=Instance.new(class)
 for _,item in ipairs(Enum.Font:GetEnumItems())do
  if item~=Enum.Font.Unknown then
   label.Font=item
   assert(label.Font==item and label.FontFace==Font.fromEnum(item),class.." "..item.Name)
  end
 end
end
''')

    def test_fontface_updates_legacy_enum_or_unknown(self):
        self.run_script('''
local label=Instance.new("TextLabel")
label.FontFace=Font.fromEnum(Enum.Font.BuilderSansBold)
assert(label.Font==Enum.Font.BuilderSansBold)
label.FontFace=Font.fromEnum(Enum.Font.SourceSansItalic)
assert(label.Font==Enum.Font.SourceSansItalic)
label.FontFace=Font.fromId(12345,Enum.FontWeight.Bold)
assert(label.Font==Enum.Font.Unknown and label.FontFace.Family=="rbxassetid://12345")
label.FontFace=Font.fromName("BuilderSans",Enum.FontWeight.Thin)
assert(label.Font==Enum.Font.Unknown)
''')

    def test_font_assignments_are_copied_and_clones_do_not_share_values(self):
        self.run_script('''
local label=Instance.new("TextLabel")
local original=Font.fromName("BuilderSans")
label.FontFace=original
original.Bold=true;assert(not label.FontFace.Bold)
local fetched=label.FontFace;fetched.Bold=true;assert(not label.FontFace.Bold)
label.FontFace=fetched;assert(label.FontFace.Bold and label.Font==Enum.Font.BuilderSansBold)
local clone=label:Clone()
assert(clone.FontFace==label.FontFace and clone.Font==label.Font)
local changed=clone.FontFace;changed.Family="rbxassetid://1";clone.FontFace=changed
assert(label.FontFace.Family~=clone.FontFace.Family)
''')

    def test_font_attributes_copy_and_clone_values(self):
        self.run_script('''
local folder=Instance.new("Folder")
local value=Font.fromName("BuilderSans")
folder:SetAttribute("Typeface",value);value.Bold=true
local stored=folder:GetAttribute("Typeface");assert(not stored.Bold)
stored.Bold=true;assert(not folder:GetAttribute("Typeface").Bold)
folder:SetAttribute("Typeface",stored)
local clone=folder:Clone();assert(clone:GetAttribute("Typeface")==stored)
assert(folder:GetAttributes().Typeface==stored)
''')

    def test_property_signals_see_a_coherent_pair_and_equal_writes_do_not_fire(self):
        self.run_script('''
local label=Instance.new("TextButton");label.Font=Enum.Font.BuilderSans
local face_changes,font_changes=0,0
label:GetPropertyChangedSignal("FontFace"):Connect(function()
 face_changes+=1;assert(label.FontFace==Font.fromEnum(label.Font))
end)
label:GetPropertyChangedSignal("Font"):Connect(function()
 font_changes+=1;assert(label.FontFace==Font.fromEnum(label.Font))
end)
label.Font=Enum.Font.BuilderSansBold;task.wait(0)
assert(face_changes==1 and font_changes==1)
label.FontFace=Font.fromName("BuilderSans",Enum.FontWeight.Bold);task.wait(0)
assert(face_changes==1 and font_changes==1)
''')

    def test_bad_property_writes_leave_both_properties_intact(self):
        self.run_script('''
local label=Instance.new("TextBox");label.Font=Enum.Font.BuilderSans
for _,bad in ipairs({700,"SourceSans",{},Enum.FontWeight.Bold,Font.fromName("Arimo")})do
 assert(not pcall(function()label.Font=bad end))
 assert(label.Font==Enum.Font.BuilderSans)
end
for _,bad in ipairs({42,"SourceSans",{},Enum.Font.SourceSans,Color3.new()})do
 assert(not pcall(function()label.FontFace=bad end))
 assert(label.FontFace==Font.fromEnum(Enum.Font.BuilderSans))
end
assert(not pcall(function()label.FontFace=nil end))
assert(not pcall(function()label.Font=Enum.Font.Unknown end))
''')

    def test_received_face_derives_legacy_font_without_global_constructors(self):
        self.run_script('''
local expected=Font.fromEnum(Enum.Font.SourceSansItalic)
local italic=Enum.FontStyle.Italic
Font={new=function()error("script constructor")end}
Enum={FontStyle={Italic=false},FontWeight={Regular=false}}
assert(workspace.FontLabel.FontFace==expected)
assert(workspace.FontLabel.FontFace.Style==italic)
assert(client.propertyOrigin(workspace.FontLabel,"Font")=="derived_received")
''',self.snapshot({'FontFace':font(style=1)}))

    def test_received_legacy_enum_derives_face(self):
        for value in [4,{'$enum':{'type':'Font','name':'SourceSansBold','value':4}}]:
            self.run_script('''
assert(workspace.FontLabel.Font==Enum.Font.SourceSansBold)
assert(workspace.FontLabel.FontFace==Font.fromEnum(Enum.Font.SourceSansBold))
assert(client.propertyOrigin(workspace.FontLabel,"FontFace")=="derived_received")
''',self.snapshot({'Font':value}))

    def test_received_unknown_enum_does_not_invent_a_font_family(self):
        self.run_script('''
assert(workspace.FontLabel.Font==Enum.Font.Unknown)
assert(not pcall(function()return workspace.FontLabel.FontFace end))
assert(client.propertyOrigin(workspace.FontLabel,"FontFace")=="unavailable")
''',self.snapshot({'Font':100}))

    def test_uncaptured_initial_font_is_unavailable(self):
        self.run_script('''
local label=Instance.new("TextLabel")
assert(not pcall(function()return label.FontFace end))
assert(not pcall(function()return label.Font end))
assert(not pcall(function()label:ResetPropertyToDefault("FontFace")end))
label.FontFace=Font.fromName("BuilderSans");assert(label.Font==Enum.Font.BuilderSans)
''')

    def test_invalid_snapshot_fonts_raise_and_valid_assignments_repair_them(self):
        invalid=[{'$font':[]},font(weight=450),font(style=3),font(weight=2**64-1),
                 {'$font':{'family':42,'weight':400,'style':0}},
                 {'$font':{'family':'x','weight':True,'style':0}},
                 {'$font':{'family':'x','weight':400,'style':0,'extra':1}}]
        for value in invalid:
            with self.subTest(value=value):
                self.run_script('''
assert(not pcall(function()return workspace.FontLabel.FontFace end))
workspace.FontLabel.FontFace=Font.fromName("BuilderSans")
assert(workspace.FontLabel.Font==Enum.Font.BuilderSans)
''',self.snapshot({'FontFace':value}))

    def test_plain_source_cli_has_the_required_enums_without_a_world(self):
        for host in transforms.HOSTS:
            with self.subTest(host=host.name):
                result=subprocess.run([str(host),'--source',str(ROOT/'runtime/scripts/font_values_demo.luau')],
                                      capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stderr)
                body=json.loads(result.stdout);self.assertTrue(body['ok'],body)
                self.assertEqual(body['values'],['rbxasset://fonts/families/BuilderSans.json',700,1,True])


@unittest.skipUnless(motion.RUST_HOST.is_file(),'build the persistent worker first')
class FontPersistentTests(unittest.TestCase):
    setUp=motion.MotionMathTests.setUp
    execute=motion.MotionMathTests.execute

    def test_bindable_callback_values_are_typed_independent_copies(self):
        result=self.execute('''
local original=Font.fromName("BuilderSans")
local event=Instance.new("BindableEvent");local seen
event.Event:Connect(function(payload)payload.font.Bold=true;seen=payload.font end)
event:Fire({font=original});task.wait(0)
assert(seen and seen.Bold and not original.Bold)
local fn=Instance.new("BindableFunction")
fn.OnInvoke=function(value)value.Style=Enum.FontStyle.Italic;return value end
local returned=fn:Invoke(original)
assert(returned.Style==Enum.FontStyle.Italic and original.Style==Enum.FontStyle.Normal)
return returned
''')
        self.assertEqual(result['values'],[font('BuilderSans',style=1)])

    def test_received_font_updates_replace_both_local_overrides(self):
        create=self.host.call({'op':'update','delta':{'version':1,'delta':True,'actions':[
            {'sequence':100,'kind':'create','id':'font:label','node':{
                'id':'font:label','class_name':'TextLabel','name':'FontLabel',
                'parent':'scope:workspace','properties':{'FontFace':font()}}}]},'timeout_ms':100})
        self.assertTrue(create['ok'],create)
        self.execute('''
getgenv().label=workspace.FontLabel
label.Font=Enum.Font.BuilderSansBold
getgenv().seen={}
label:GetPropertyChangedSignal("Font"):Connect(function()table.insert(seen,label.Font)end)
''')
        for sequence,fields,expected in [(101,{'FontFace':font('SourceSansPro',300)},'SourceSansLight'),
                                         (102,{'Font':49},'BuilderSansExtraBold')]:
            update=self.host.call({'op':'update','delta':{'version':1,'delta':True,'actions':[
                {'sequence':sequence,'kind':'set','id':'font:label','fields':fields}]},'timeout_ms':100})
            self.assertTrue(update['ok'],update);self.assertFalse(update.get('task_errors'),update)
            self.execute('assert(label.Font==Enum.Font.'+expected+');assert(label.FontFace==Font.fromEnum(label.Font))')
        self.execute('assert(#seen==2 and seen[1]==Enum.Font.SourceSansLight and seen[2]==Enum.Font.BuilderSansExtraBold)')

    def test_unknown_received_legacy_font_clears_stale_local_family(self):
        snapshot=copy.deepcopy(motion.SNAPSHOT)
        snapshot['defaults'].setdefault('TextLabel',{})['FontFace']=font()
        snapshot['default_origins'].setdefault('TextLabel',{})['FontFace']='class_default'
        self.host.close();self.host=motion.PersistentLuauHost(snapshot);self.addCleanup(self.host.close)
        result=self.execute('''
getgenv().label=Instance.new("TextLabel",workspace);label.Name="LiveFont"
label.Font=Enum.Font.BuilderSans
''')
        node=next(m['node']['id'] for m in result['mutations'] if m.get('kind')=='create' and m['node']['class_name']=='TextLabel')
        update=self.host.call({'op':'update','delta':{'version':1,'delta':True,'actions':[
            {'sequence':100,'kind':'set','id':node,'fields':{'Font':100}}]},'timeout_ms':100})
        self.assertTrue(update['ok'],update)
        self.execute('''
assert(label.Font==Enum.Font.Unknown)
assert(not pcall(function()return label.FontFace end))
assert(client.propertyOrigin(label,"FontFace")=="unavailable")
label.Font=Enum.Font.BuilderSansBold
assert(label.FontFace==Font.fromEnum(Enum.Font.BuilderSansBold))
assert(label:Clone().FontFace==label.FontFace)
''')


if __name__=='__main__':unittest.main()
