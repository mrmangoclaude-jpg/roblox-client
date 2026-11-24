"""GUI modifier behavior through ordinary Luau scripts and replicated updates."""
import unittest

from persistent_runtime import PersistentLuauHost
from test_display_layout import layout_snapshot


class GuiModifierTests(unittest.TestCase):
    def setUp(self):
        self.host = PersistentLuauHost(layout_snapshot())
        self.addCleanup(self.host.close)
        self.execute('getgenv().screen=game:GetService("Players").LocalPlayer.Gui.Screen')

    def execute(self, source):
        r = self.host.call({'op': 'execute', 'source': source, 'timeout_ms': 1000})
        self.assertTrue(r['ok'], r.get('error'))
        self.assertEqual(r.get('task_errors', []), [])
        return r['values']

    def update(self, actions):
        r = self.host.call({'op': 'update', 'timeout_ms': 100, 'delta': {
            'version': 1, 'delta': True, 'actions': actions}})
        self.assertTrue(r['ok'], r.get('error'))
        return r

    def test_authored_gui_properties_can_be_set_without_received_defaults(self):
        self.assertEqual(self.execute('''
local f=Instance.new("Frame",screen)
getgenv().writes=0
f:GetPropertyChangedSignal("Size"):Connect(function()writes+=1 end)
f.Size=UDim2.new(0,200,0,100)
f.Position=UDim2.new(.5,10,.5,20)
f.AnchorPoint=Vector2.new(.5,.5)
getgenv().authored=f
return f.AbsoluteSize.X,f.AbsoluteSize.Y,f.AbsolutePosition.X,f.AbsolutePosition.Y,
 typeof(f.Position),typeof(f.AnchorPoint),f.SizeConstraint==Enum.SizeConstraint.RelativeXY,
 f.AutomaticSize==Enum.AutomaticSize.None,client.propertyOrigin(f,"Size")
'''), [200, 100, 400, 350, 'UDim2', 'Vector2', True, True, 'local'])
        self.assertEqual(self.execute('return writes'), [1])

    def test_uniform_scale_preserves_anchor_and_scales_child_offsets(self):
        self.assertEqual(self.execute('''
local f=Instance.new("Frame",screen)
f.Size=UDim2.new(0,200,0,100);f.Position=UDim2.new(.5,10,.5,20);f.AnchorPoint=Vector2.new(.5,.5)
local s=Instance.new("UIScale",f);s.Scale=2
local child=Instance.new("Frame",f)
child.Size=UDim2.new(.5,10,.5,20);child.Position=UDim2.new(0,15,0,25)
return f.AbsoluteSize.X,f.AbsoluteSize.Y,f.AbsolutePosition.X,f.AbsolutePosition.Y,
 child.AbsoluteSize.X,child.AbsoluteSize.Y,child.AbsolutePosition.X,child.AbsolutePosition.Y
'''), [400, 200, 300, 300, 220, 140, 330, 350])

    def test_nested_scale_multiplies_without_double_scaling_positions(self):
        self.assertEqual(self.execute('''
local f=Instance.new("Frame",screen);f.Size=UDim2.new(0,200,0,100)
Instance.new("UIScale",f).Scale=2
local c=Instance.new("Frame",f);c.Size=UDim2.new(.5,10,.5,20);c.Position=UDim2.new(0,15,0,25)
Instance.new("UIScale",c).Scale=.5
local g=Instance.new("Frame",c);g.Size=UDim2.new(0,10,0,20);g.Position=UDim2.new(0,3,0,4)
return c.AbsoluteSize.X,c.AbsoluteSize.Y,c.AbsolutePosition.X,c.AbsolutePosition.Y,
 g.AbsoluteSize.X,g.AbsoluteSize.Y,g.AbsolutePosition.X,g.AbsolutePosition.Y
'''), [110, 70, 30, 50, 10, 20, 33, 54])

    def test_zero_scale_and_detached_subtrees_have_zero_geometry(self):
        self.assertEqual(self.execute('''
local f=screen.Frame
local s=Instance.new("UIScale",f);s.Scale=0
local a,b=f.AbsoluteSize,f.Child.AbsoluteSize
screen.Parent=nil
return a.X,a.Y,b.X,b.Y,f.Child.AbsoluteSize.X,f.Child.AbsoluteSize.Y,
 f.Child.AbsolutePosition.X,f.Child.AbsolutePosition.Y
'''), [0] * 8)

    def test_padding_uses_normal_parent_size_and_scales_offsets(self):
        self.assertEqual(self.execute('''
local f=Instance.new("Frame",screen);f.Size=UDim2.new(0,200,0,100)
Instance.new("UIScale",f).Scale=2
local p=Instance.new("UIPadding",f)
p.PaddingLeft=UDim.new(.1,5);p.PaddingRight=UDim.new(.2,0)
p.PaddingTop=UDim.new(0,10);p.PaddingBottom=UDim.new(.1,0)
local c=Instance.new("Frame",f);c.Size=UDim2.new(1,0,1,0)
return f.AbsoluteSize.X,f.AbsoluteSize.Y,c.AbsoluteSize.X,c.AbsoluteSize.Y,
 c.AbsolutePosition.X,c.AbsolutePosition.Y,typeof(p.PaddingTop),p.PaddingTop.Offset
'''), [400, 200, 270, 160, 50, 20, 'UDim', 10])

    def test_padding_defaults_negative_padding_and_consumed_content_area(self):
        self.assertEqual(self.execute('''
local f=Instance.new("Frame",screen);f.Size=UDim2.new(0,200,0,100)
local p=Instance.new("UIPadding",f)
local c=Instance.new("Frame",f);c.Size=UDim2.new(1,0,1,0)
local zero=p.PaddingBottom==UDim.new(0,0)
p.PaddingLeft=UDim.new(0,-10)
local width,x=c.AbsoluteSize.X,c.AbsolutePosition.X
p.PaddingLeft=UDim.new(0,300)
return zero,width,x,c.AbsoluteSize.X,c.AbsoluteSize.Y
'''), [True, 210, -10, 0, 100])

    def test_size_constraint_changes_size_axes_but_not_position_axes(self):
        self.assertEqual(self.execute('''
local f=screen.Frame
f.SizeConstraint=Enum.SizeConstraint.RelativeXX
local a,b=f.AbsoluteSize,f.AbsolutePosition
f.SizeConstraint=Enum.SizeConstraint.RelativeYY
return a.X,a.Y,b.X,b.Y,f.AbsoluteSize.X,f.AbsoluteSize.Y,f.AbsolutePosition.X,f.AbsolutePosition.Y,
 typeof(f.SizeConstraint),f.SizeConstraint.Name,f.SizeConstraint.Value
'''), [500, 470, 240, 145, 390, 360, 295, 200, 'EnumItem', 'RelativeYY', 2])

    def test_gui_enum_identity_clone_roundtrip_and_wrong_type_rejection(self):
        self.assertEqual(self.execute('''
local f=Instance.new("Frame",screen)
f.Size=UDim2.new(0,200,0,100)
f.SizeConstraint=Enum.SizeConstraint.RelativeXX
local copy=f:Clone();copy.Parent=screen
local lookup={[Enum.SizeConstraint.RelativeXX]=true}
local ok=pcall(function()f.SizeConstraint=Enum.Axis.X end)
local bad=pcall(function()f.AnchorPoint=Color3.new()end)
return not ok,not bad,copy.SizeConstraint==f.SizeConstraint,lookup[copy.SizeConstraint],
 #Enum.SizeConstraint:GetEnumItems(),#Enum.AutomaticSize:GetEnumItems(),
 Enum.AutomaticSize:FromValue(3)==Enum.AutomaticSize.XY,
 client.propertyOrigin(Instance.new("Frame"),"Position")
'''), [True, True, True, True, 3, 4, True, 'class_default'])

    def test_scale_changes_reparent_and_destroy_notify_computed_watchers(self):
        self.execute('''
getgenv().s=Instance.new("UIScale",screen.Frame)
getgenv().calls=0;getgenv().changed=0
screen.Frame.Child:GetPropertyChangedSignal("AbsoluteSize"):Connect(function()calls+=1 end)
screen.Frame.Changed:Connect(function(k)if k=="AbsoluteSize"then changed+=1 end end)
s.Scale=2
''')
        self.assertEqual(self.execute('return calls,changed,screen.Frame.Child.AbsoluteSize.X'), [1, 1, 500])
        self.execute('s.Scale=2')
        self.assertEqual(self.execute('return calls,changed'), [1, 1])
        self.execute('s.Parent=screen.Frame.Child')
        self.assertEqual(self.execute('return calls,changed,screen.Frame.AbsoluteSize.X,screen.Frame.Child.AbsoluteSize.X'),
                         [1, 2, 500, 500])
        self.execute('s:Destroy()')
        self.assertEqual(self.execute('return calls,changed,screen.Frame.Child.AbsoluteSize.X'), [2, 2, 250])

    def test_server_modifiers_and_enum_updates_override_local_values(self):
        self.execute('screen.Frame.SizeConstraint=Enum.SizeConstraint.RelativeXX')
        self.update([{'sequence': 8, 'kind': 'create', 'node': {
            'id': 'received-scale', 'name': 'Scale', 'class_name': 'UIScale', 'parent': 'Frame', 'properties': {}}},
            {'sequence': 9, 'kind': 'set', 'id': 'Frame', 'fields': {'SizeConstraint': 2}}])
        self.assertEqual(self.execute('''
local f=screen.Frame
return f.Scale.Scale,client.propertyOrigin(f.Scale,"Scale"),f.SizeConstraint==Enum.SizeConstraint.RelativeYY,
 f.AbsoluteSize.X,f.AbsoluteSize.Y
'''), [1, 'class_default', True, 390, 360])
        self.update([{'sequence': 10, 'kind': 'set', 'id': 'received-scale', 'fields': {'Scale': 2}}])
        self.assertEqual(self.execute('return screen.Frame.AbsoluteSize.X,screen.Frame.Child.AbsoluteSize.X'), [780, 390])

    def test_content_layout_blocks_children_but_not_its_container_box(self):
        self.assertEqual(self.execute('''
local f=screen.Frame
Instance.new("UITableLayout",f)
local ok,err=pcall(function()return f.Child.AbsoluteSize end)
return f.AbsoluteSize.X,f.AbsoluteSize.Y,ok,string.find(err,"content layout",1,true)~=nil
'''), [500, 360, False, True])

    def test_invalid_scale_is_atomic_and_duplicate_modifiers_are_explicit(self):
        self.assertEqual(self.execute('''
local f=screen.Frame;local s=Instance.new("UIScale",f)
s.Scale=2
local bad=pcall(function()s.Scale=0/0 end)
local negative=pcall(function()s.Scale=-1 end)
local preserved=s.Scale
Instance.new("UIScale",f)
local ok,err=pcall(function()return f.AbsoluteSize end)
return not bad,not negative,preserved,ok,string.find(err,"multiple active GUI components",1,true)~=nil
'''), [True, True, 2, False, True])


class GuiModifierOneShotTests(unittest.TestCase):
    def test_authored_layout_in_each_compiled_worker(self):
        from test_cframe_transforms import CFrameTransformTests
        CFrameTransformTests.run_script(self, '''
local screen=game:GetService("Players").LocalPlayer.Gui.Screen
local f=Instance.new("Frame",screen);f.Size=UDim2.new(0,200,0,100)
Instance.new("UIScale",f).Scale=2
local padding=Instance.new("UIPadding",f)
padding.PaddingLeft=UDim.new(.1,5);padding.PaddingTop=UDim.new(0,10)
local c=Instance.new("Frame",f);c.Size=UDim2.new(.5,0,.25,0)
c.SizeConstraint=Enum.SizeConstraint.RelativeXX
assert(c.AbsoluteSize==Vector2.new(175,87.5))
assert(c.AbsolutePosition==Vector2.new(50,20))
assert(c.AutomaticSize==Enum.AutomaticSize.None)
local clone=c:Clone();clone.Parent=f
assert(clone.SizeConstraint==Enum.SizeConstraint.RelativeXX)
assert(clone.AbsoluteSize==c.AbsoluteSize)
''', layout_snapshot())


if __name__ == '__main__':
    unittest.main()
