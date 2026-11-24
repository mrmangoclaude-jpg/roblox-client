"""Non-flex list layout against the real native VM; expectations from Creator Hub.

These are offline behavior tests, not measurements from Roblox Studio.
"""
import unittest
from persistent_runtime import PersistentLuauHost
from test_display_layout import layout_snapshot


SETUP = '''
local screen=game:GetService("Players").LocalPlayer.Gui.Screen
getgenv().panel=Instance.new("Frame",screen)
panel.Size=UDim2.fromOffset(300,200)
getgenv().list=Instance.new("UIListLayout",panel)
list.SortOrder=Enum.SortOrder.LayoutOrder
getgenv().a=Instance.new("Frame",panel);a.Name="B";a.Size=UDim2.fromOffset(80,20)
getgenv().b=Instance.new("Frame",panel);b.Name="A";b.Size=UDim2.fromOffset(40,30)
getgenv().c=Instance.new("Frame",panel);c.Name="C";c.Size=UDim2.fromOffset(60,10)
'''


class GuiListLayoutTests(unittest.TestCase):
    def setUp(self):
        self.host=PersistentLuauHost(layout_snapshot())
        self.addCleanup(self.host.close)
        self.execute(SETUP)

    def execute(self, source):
        result=self.host.call({'op':'execute','source':source,'timeout_ms':1000})
        self.assertTrue(result['ok'],result.get('error'))
        self.assertEqual(result.get('task_errors',[]),[])
        return result['values']

    def update(self, actions):
        result=self.host.call({'op':'update','timeout_ms':100,'delta':{
            'version':1,'delta':True,'actions':actions}})
        self.assertTrue(result['ok'],result.get('error'))
        self.assertEqual(result.get('task_errors',[]),[])

    def test_vertical_layout_and_padding_ignore_authored_position_rotation_anchor(self):
        self.assertEqual(self.execute('''
list.Padding=UDim.new(0,5)
a.Position=UDim2.fromOffset(200,100);a.AnchorPoint=Vector2.new(.5,1);a.Rotation=45
return a.AbsolutePosition.X,a.AbsolutePosition.Y,a.AbsoluteRotation,
 b.AbsolutePosition.Y,c.AbsolutePosition.Y,list.AbsoluteContentSize.X,list.AbsoluteContentSize.Y,
 a.Position.X.Offset,a.Rotation,a.AnchorPoint.Y
'''),[0,0,0,25,60,80,70,200,45,1])

    def test_horizontal_scale_padding_center_and_bottom_alignment(self):
        self.assertEqual(self.execute('''
list.FillDirection=Enum.FillDirection.Horizontal;list.Padding=UDim.new(.1,0)
list.HorizontalAlignment=Enum.HorizontalAlignment.Center
list.VerticalAlignment=Enum.VerticalAlignment.Bottom
return a.AbsolutePosition.X,a.AbsolutePosition.Y,b.AbsolutePosition.X,b.AbsolutePosition.Y,
 c.AbsolutePosition.X,c.AbsolutePosition.Y,list.AbsoluteContentSize.X,list.AbsoluteContentSize.Y
'''),[30,180,140,170,210,190,240,30])

    def test_vertical_right_center_alignment(self):
        self.assertEqual(self.execute('''
list.HorizontalAlignment=Enum.HorizontalAlignment.Right
list.VerticalAlignment=Enum.VerticalAlignment.Center
return a.AbsolutePosition.X,a.AbsolutePosition.Y,b.AbsolutePosition.X,b.AbsolutePosition.Y,
 c.AbsolutePosition.X,c.AbsolutePosition.Y
'''),[220,70,260,90,240,120])

    def test_sort_order_ties_use_parent_insertion_not_creation(self):
        self.assertEqual(self.execute('''
a.Parent=nil;a.Parent=panel
local first=b.AbsolutePosition.Y
local second=c.AbsolutePosition.Y
local last=a.AbsolutePosition.Y
a.Parent=panel
return first,second,last,a.AbsolutePosition.Y
'''),[0,30,40,40])

    def test_clone_preserves_reparented_sibling_order(self):
        self.assertEqual(self.execute('''
a.Parent=nil;a.Parent=panel
local clone=panel:Clone();clone.Parent=panel.Parent
return clone.A.AbsolutePosition.Y,clone.C.AbsolutePosition.Y,clone.B.AbsolutePosition.Y
'''),[0,30,40])

    def test_name_and_layout_order_changes_rearrange(self):
        self.assertEqual(self.execute('''
list.SortOrder=Enum.SortOrder.Name
local byName=a.AbsolutePosition.Y
c.Name="0"
local renamed=c.AbsolutePosition.Y
list.SortOrder=Enum.SortOrder.LayoutOrder
c.LayoutOrder=-10;a.LayoutOrder=20
return byName,renamed,c.AbsolutePosition.Y,b.AbsolutePosition.Y,a.AbsolutePosition.Y
'''),[30,0,0,10,40])

    def test_hidden_removed_and_non_gui_children_do_not_occupy_slots(self):
        self.assertEqual(self.execute('''
list.Padding=UDim.new(0,10)
Instance.new("Folder",panel)
b.Visible=false
local pos=c.AbsolutePosition.Y
local size=list.AbsoluteContentSize
a:Destroy()
return pos,size.X,size.Y,c.AbsolutePosition.Y,list.AbsoluteContentSize.X,list.AbsoluteContentSize.Y
'''),[30,80,40,0,60,10])

    def test_empty_list_has_no_padding_and_detached_list_has_zero_size(self):
        self.assertEqual(self.execute('''
list.Padding=UDim.new(0,50)
a.Visible=false;b.Visible=false;c.Visible=false
local empty=list.AbsoluteContentSize
list.Parent=nil
return empty.X,empty.Y,list.AbsoluteContentSize.X,list.AbsoluteContentSize.Y
'''),[0,0,0,0])

    def test_container_padding_and_scale_apply_to_children_and_spacing(self):
        self.assertEqual(self.execute('''
local padding=Instance.new("UIPadding",panel)
padding.PaddingLeft=UDim.new(0,10);padding.PaddingTop=UDim.new(0,15)
padding.PaddingBottom=UDim.new(0,5)
Instance.new("UIScale",panel).Scale=2
list.Padding=UDim.new(.1,5)
return a.AbsolutePosition.X,a.AbsolutePosition.Y,b.AbsolutePosition.Y,c.AbsolutePosition.Y,
 list.AbsoluteContentSize.X,list.AbsoluteContentSize.Y
'''),[20,30,116,222,160,212])

    def test_constraints_and_nested_descendants_use_arranged_boxes(self):
        self.assertEqual(self.execute('''
local size=Instance.new("UISizeConstraint",a);size.MinSize=Vector2.new(100,40)
local aspect=Instance.new("UIAspectRatioConstraint",b);aspect.AspectRatio=2
local child=Instance.new("Frame",b);child.Size=UDim2.fromScale(.5,.5)
child.Position=UDim2.fromOffset(3,4)
return b.AbsolutePosition.Y,c.AbsolutePosition.Y,list.AbsoluteContentSize.X,list.AbsoluteContentSize.Y,
 child.AbsoluteSize.X,child.AbsoluteSize.Y,child.AbsolutePosition.X,child.AbsolutePosition.Y
'''),[40,60,100,70,20,10,3,44])

    def test_nested_lists_do_not_use_unarranged_parent_position(self):
        self.assertEqual(self.execute('''
local inner=Instance.new("UIListLayout",b);inner.FillDirection=Enum.FillDirection.Horizontal
inner.SortOrder=Enum.SortOrder.LayoutOrder
local one=Instance.new("Frame",b);one.Size=UDim2.fromOffset(10,5)
local two=Instance.new("Frame",b);two.Size=UDim2.fromOffset(20,7)
return one.AbsolutePosition.X,one.AbsolutePosition.Y,two.AbsolutePosition.X,two.AbsolutePosition.Y,
 inner.AbsoluteContentSize.X,inner.AbsoluteContentSize.Y
'''),[0,20,10,20,30,7])

    def test_content_size_and_child_position_change_signals(self):
        self.execute('''
getgenv().sizes=0;getgenv().positions=0;getgenv().changed=0
list:GetPropertyChangedSignal("AbsoluteContentSize"):Connect(function()sizes+=1 end)
list.Changed:Connect(function(key)if key=="AbsoluteContentSize"then changed+=1 end end)
c:GetPropertyChangedSignal("AbsolutePosition"):Connect(function()positions+=1 end)
a.Size=UDim2.fromOffset(90,25)
''')
        self.assertEqual(self.execute('return sizes,positions,changed'),[1,1,1])
        self.execute('a.Size=UDim2.fromOffset(90,25)')
        self.assertEqual(self.execute('return sizes,positions,changed'),[1,1,1])
        self.execute('b.Visible=false')
        self.assertEqual(self.execute('return sizes,positions,changed'),[2,2,2])

    def test_typed_properties_clone_and_read_only_content_size(self):
        self.assertEqual(self.execute('''
list.FillDirection=Enum.FillDirection.Horizontal
local copy=panel:Clone();copy.Parent=panel.Parent
local cloned=copy:FindFirstChildOfClass("UIListLayout")
local keys={[Enum.FillDirection.Horizontal]=true}
local bad=pcall(function()list.FillDirection=Enum.Axis.X end)
local readonly=pcall(function()list.AbsoluteContentSize=Vector2.new(1,2)end)
local wrap=pcall(function()list.Wraps=1 end)
return keys[cloned.FillDirection],bad,readonly,wrap,cloned.AbsoluteContentSize.X,
 cloned.AbsoluteContentSize.Y,typeof(list.Padding),client.propertyOrigin(list,"AbsoluteContentSize")
'''),[True,False,False,False,180,30,'UDim','local_display'])

    def test_wrap_and_flex_supported_but_duplicate_layouts_are_explicit(self):
        self.assertEqual(self.execute('''
list.Wraps=true
local wrap=pcall(function()return a.AbsolutePosition end)
list.Wraps=false;list.HorizontalFlex=Enum.UIFlexAlignment.Fill
local flex=pcall(function()return list.AbsoluteContentSize end)
list.HorizontalFlex=Enum.UIFlexAlignment.None
Instance.new("UIListLayout",panel)
local duplicate=pcall(function()return a.AbsoluteSize end)
return wrap,flex,duplicate
'''),[True,True,False])

    def test_replicated_create_and_fields_relayout_and_ignore_computed_size(self):
        self.execute('list:Destroy();a:Destroy();b:Destroy();c:Destroy()')
        self.update([{'sequence':100,'kind':'create','node':{
            'id':'received-list','name':'List','class_name':'UIListLayout','parent':'Frame',
            'properties':{'FillDirection':0,'SortOrder':2,'Padding':{'$udim':[0,7]}}}},
            {'sequence':101,'kind':'set','id':'Child','fields':{'Visible':True}}])
        self.assertEqual(self.execute('''
local frame=game:GetService("Players").LocalPlayer.Gui.Screen.Frame
return frame.Child.AbsolutePosition.X,frame.Child.AbsolutePosition.Y,
 frame.List.AbsoluteContentSize.X,frame.List.AbsoluteContentSize.Y
'''),[240,200,250,180])
        self.update([{'sequence':102,'kind':'set','id':'received-list','fields':{
            'HorizontalAlignment':2,'AbsoluteContentSize':{'$vector2':[9999,9999]}}}])
        self.assertEqual(self.execute('''
local frame=game:GetService("Players").LocalPlayer.Gui.Screen.Frame
return frame.Child.AbsolutePosition.X,frame.List.AbsoluteContentSize.X
'''),[490,250])

    def test_received_reparent_and_record_replacement_preserve_tie_order(self):
        layout={'id':'received-list','name':'List','class_name':'UIListLayout','parent':'Frame',
                'properties':{'FillDirection':1,'SortOrder':2}}
        sibling={'id':'sibling','name':'Sibling','class_name':'Frame','parent':'Frame',
                 'properties':{'Visible':True,'Size':{'$udim2':[{'$udim':[0,40]},{'$udim':[0,20]}]}}}
        self.update([{'sequence':100,'kind':'create','node':layout},
                     {'sequence':101,'kind':'set','id':'Child','fields':{'Visible':True}},
                     {'sequence':102,'kind':'create','node':sibling}])
        query='''local f=game:GetService("Players").LocalPlayer.Gui.Screen.Frame
return f.Child.AbsolutePosition.Y,f.Sibling.AbsolutePosition.Y'''
        self.assertEqual(self.execute(query),[200,380])
        self.update([{'sequence':103,'kind':'set','id':'Child','fields':{'Parent':None}},
                     {'sequence':104,'kind':'set','id':'Child','fields':{'Parent':{'$ref':'Frame'}}}])
        self.assertEqual(self.execute(query),[220,200])
        self.update([{'sequence':105,'kind':'create','node':sibling}])
        self.assertEqual(self.execute(query),[220,200])


class GuiListOneShotTests(unittest.TestCase):
    def test_large_received_list_sorts_without_mutating_authored_properties(self):
        snapshot=layout_snapshot()
        snapshot['nodes']=[n for n in snapshot['nodes'] if n['id']!='Child']
        snapshot['nodes'].append({'id':'list','name':'List','class_name':'UIListLayout',
            'parent':'Frame','properties':{'SortOrder':2,'FillDirection':1,'Padding':{'$udim':[0,1]}}})
        for index in range(1000):
            snapshot['nodes'].append({'id':f'item-{index}','name':f'Item{index}',
                'class_name':'Frame','parent':'Frame','properties':{'Visible':True,'LayoutOrder':999-index,
                'Size':{'$udim2':[{'$udim':[0,10]},{'$udim':[0,2]}]}}})
        host=PersistentLuauHost(snapshot)
        self.addCleanup(host.close)
        result=host.call({'op':'execute','timeout_ms':1000,'source':'''
local f=game:GetService("Players").LocalPlayer.Gui.Screen.Frame
return f.List.AbsoluteContentSize.X,f.List.AbsoluteContentSize.Y,
 f.Item999.AbsolutePosition.Y,f.Item0.AbsolutePosition.Y,f.Item0.Position.Y.Offset
'''})
        self.assertTrue(result['ok'],result.get('error'))
        self.assertEqual(result['values'],[10,2999,200,3197,0])
        self.assertEqual(result.get('task_errors',[]),[])

    def test_list_layout_in_both_workers(self):
        from test_cframe_transforms import CFrameTransformTests
        CFrameTransformTests.run_script(self, SETUP.replace('getgenv().','')+'''
list.Padding=UDim.new(0,5)
assert(list.AbsoluteContentSize==Vector2.new(80,70))
assert(b.AbsolutePosition==Vector2.new(0,25))
a.Parent=nil;a.Parent=panel
assert(a.AbsolutePosition==Vector2.new(0,50))
''',layout_snapshot())


if __name__=='__main__':unittest.main()
