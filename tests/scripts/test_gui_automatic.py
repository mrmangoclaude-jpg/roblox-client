"""Automatic Frame sizes using real native layout passes, without Studio parity claims."""
import unittest
from pathlib import Path
from persistent_runtime import PersistentLuauHost
from test_display_layout import layout_snapshot
import test_gui_list_layout as lists

SETUP=lists.SETUP+'''
panel.Size=UDim2.fromOffset(0,0);panel.AutomaticSize=Enum.AutomaticSize.XY
list.Padding=UDim.new(0,5)
'''


class GuiAutomaticTests(unittest.TestCase):
    execute=lists.GuiListLayoutTests.execute
    update=lists.GuiListLayoutTests.update

    def setUp(self):
        self.host=PersistentLuauHost(layout_snapshot());self.addCleanup(self.host.close)
        self.execute(SETUP)

    def test_list_content_grows_hides_and_shrinks_without_changing_size(self):
        self.assertEqual(self.execute('''
local initial=panel.AbsoluteSize
b.Visible=false;local hidden=panel.AbsoluteSize
a:Destroy();local removed=panel.AbsoluteSize
return initial.X,initial.Y,hidden.X,hidden.Y,removed.X,removed.Y,panel.Size.X.Offset,panel.Size.Y.Offset
'''),[80,70,80,35,60,10,0,0])

    def test_selected_axes_and_authored_minimum(self):
        self.assertEqual(self.execute('''
panel.AutomaticSize=Enum.AutomaticSize.Y;panel.Size=UDim2.fromOffset(120,100)
local minimum=panel.AbsoluteSize
panel.Size=UDim2.fromOffset(120,10)
local vertical=panel.AbsoluteSize
panel.AutomaticSize=Enum.AutomaticSize.X
list.FillDirection=Enum.FillDirection.Horizontal
return minimum.X,minimum.Y,vertical.X,vertical.Y,panel.AbsoluteSize.X,panel.AbsoluteSize.Y
'''),[120,100,120,70,190,10])

    def test_wrap_remeasures_height_after_width_change(self):
        self.assertEqual(self.execute('''
panel.AutomaticSize=Enum.AutomaticSize.Y;panel.Size=UDim2.fromOffset(130,0)
list.FillDirection=Enum.FillDirection.Horizontal;list.Wraps=true;list.Padding=UDim.new(0,10)
local before=panel.AbsoluteSize.Y
panel.Size=UDim2.fromOffset(200,0)
return before,panel.AbsoluteSize.Y,c.AbsolutePosition.X,c.AbsolutePosition.Y
'''),[50,30,140,0])

    def test_max_width_is_applied_during_measurement(self):
        self.assertEqual(self.execute('''
panel.Size=UDim2.fromOffset(130,0)
list.FillDirection=Enum.FillDirection.Horizontal;list.Wraps=true;list.Padding=UDim.new(0,10)
local limit=Instance.new("UISizeConstraint",panel);limit.MaxSize=Vector2.new(90,math.huge)
return panel.AbsoluteSize.X,panel.AbsoluteSize.Y,b.AbsolutePosition.Y,c.AbsolutePosition.Y
'''),[90,80,30,70])

    def test_padding_scaling_and_automatic_anchor_position(self):
        self.assertEqual(self.execute('''
Instance.new("UIScale",panel).Scale=2
local padding=Instance.new("UIPadding",panel)
padding.PaddingLeft=UDim.new(0,10);padding.PaddingRight=UDim.new(0,15)
padding.PaddingTop=UDim.new(0,3);padding.PaddingBottom=UDim.new(0,7)
panel.Position=UDim2.fromOffset(200,150);panel.AnchorPoint=Vector2.new(.5,.5)
return panel.AbsoluteSize.X,panel.AbsoluteSize.Y,panel.AbsolutePosition.X,panel.AbsolutePosition.Y,
a.AbsolutePosition.X,a.AbsolutePosition.Y
'''),[210,160,95,70,115,76])

    def test_flex_fill_cannot_erase_intrinsic_content_of_zero_size_parent(self):
        self.assertEqual(self.execute('''
list.VerticalFlex=Enum.UIFlexAlignment.Fill;list.HorizontalFlex=Enum.UIFlexAlignment.Fill
local initial=panel.AbsoluteSize
panel.Size=UDim2.fromOffset(120,100)
return initial.X,initial.Y,panel.AbsoluteSize.X,panel.AbsoluteSize.Y,a.AbsoluteSize.X,
list.AbsoluteContentSize.X,list.AbsoluteContentSize.Y
'''),[80,70,120,100,120,120,100])

    def test_individual_flex_shrink_does_not_collapse_automatic_parent(self):
        self.assertEqual(self.execute('''
for _,item in {a,b,c} do Instance.new("UIFlexItem",item).FlexMode=Enum.UIFlexMode.Fill end
return panel.AbsoluteSize.X,panel.AbsoluteSize.Y,a.AbsoluteSize.Y,b.AbsoluteSize.Y,c.AbsoluteSize.Y
'''),[80,70,20,30,10])

    def test_free_children_support_anchors_scale_constraints_and_visibility(self):
        self.assertEqual(self.execute('''
list:Destroy();b:Destroy();c:Destroy()
a.Size=UDim2.fromOffset(120,80);a.Position=UDim2.fromOffset(100,100);a.AnchorPoint=Vector2.new(.5,.5)
Instance.new("UIScale",a).Scale=2
Instance.new("UISizeConstraint",a).MaxSize=Vector2.new(100,60)
local extent=panel.AbsoluteSize
a.Visible=false
return extent.X,extent.Y,panel.AbsoluteSize.X,panel.AbsoluteSize.Y
'''),[200,160,0,0])

    def test_scale_content_converges(self):
        values=self.execute('''
list:Destroy();b:Destroy();c:Destroy()
a.Size=UDim2.new(.5,40,.5,10)
return panel.AbsoluteSize.X,panel.AbsoluteSize.Y,a.AbsoluteSize.X,a.AbsoluteSize.Y
''')
        for actual,expected in zip(values,[80,20,80,20]):self.assertAlmostEqual(actual,expected,places=4)

    def test_scale_padding_converges_without_double_counting(self):
        values=self.execute('''
local padding=Instance.new("UIPadding",panel)
padding.PaddingLeft=UDim.new(.1,0);padding.PaddingRight=UDim.new(.1,0)
return panel.AbsoluteSize.X,a.AbsolutePosition.X,panel.AbsoluteSize.Y
''')
        for actual,expected in zip(values,[100,10,70]):self.assertAlmostEqual(actual,expected,places=4)

    def test_divergent_size_dependency_is_bounded_and_next_query_recovers(self):
        self.assertEqual(self.execute('''
list:Destroy();b:Destroy();c:Destroy()
a.Size=UDim2.new(1,10,0,20)
local ok,err=pcall(function()return panel.AbsoluteSize end)
a.Size=UDim2.fromOffset(40,20)
return ok,string.find(err,"did not converge",1,true)~=nil,panel.AbsoluteSize.X,panel.AbsoluteSize.Y
'''),[False,True,40,20])

    def test_own_maximum_caps_a_divergent_dependency(self):
        self.assertEqual(self.execute('''
list:Destroy();b:Destroy();c:Destroy()
a.Size=UDim2.new(1,10,0,20)
Instance.new("UISizeConstraint",panel).MaxSize=Vector2.new(100,100)
return panel.AbsoluteSize.X,panel.AbsoluteSize.Y,a.AbsoluteSize.X
'''),[100,20,110])

    def test_nested_automatic_lists_and_clone(self):
        self.assertEqual(self.execute('''
b:Destroy();c:Destroy();a.Size=UDim2.fromOffset(0,0);a.AutomaticSize=Enum.AutomaticSize.XY
local inner=Instance.new("UIListLayout",a);inner.FillDirection=Enum.FillDirection.Horizontal;inner.Padding=UDim.new(0,3)
local first=Instance.new("Frame",a);first.Size=UDim2.fromOffset(30,10)
local second=Instance.new("Frame",a);second.Size=UDim2.fromOffset(50,20)
local clone=panel:Clone();clone.Parent=panel.Parent
return panel.AbsoluteSize.X,panel.AbsoluteSize.Y,clone.AbsoluteSize.X,clone.AbsoluteSize.Y,
second.AbsolutePosition.X
'''),[83,20,83,20,33])

    def test_flexed_width_remeasures_wrapped_automatic_height(self):
        self.assertEqual(self.execute('''
c:Destroy();panel.Size=UDim2.fromOffset(200,0);panel.AutomaticSize=Enum.AutomaticSize.Y
list.FillDirection=Enum.FillDirection.Horizontal;list.Padding=UDim.new(0,10);list.HorizontalFlex=Enum.UIFlexAlignment.Fill
a.Size=UDim2.fromOffset(80,0);a.AutomaticSize=Enum.AutomaticSize.Y;b.Size=UDim2.fromOffset(40,5)
a.Rotation=45;a.AnchorPoint=Vector2.new(.5,.5)
local inner=Instance.new("UIListLayout",a);inner.FillDirection=Enum.FillDirection.Horizontal;inner.Wraps=true
for i=1,2 do local item=Instance.new("Frame",a);item.Size=UDim2.fromOffset(50,10) end
return panel.AbsoluteSize.Y,a.AbsoluteSize.X,a.AbsoluteSize.Y,b.AbsoluteSize.X,inner.AbsoluteContentSize.Y
'''),[10,115,10,75,10])

    def test_automatic_cross_content_is_minimum_for_stretch(self):
        self.assertEqual(self.execute('''
b:Destroy();c:Destroy();panel.AutomaticSize=Enum.AutomaticSize.None;panel.Size=UDim2.fromOffset(200,20)
list.FillDirection=Enum.FillDirection.Horizontal;list.VerticalFlex=Enum.UIFlexAlignment.Fill
a.Size=UDim2.fromOffset(100,0);a.AutomaticSize=Enum.AutomaticSize.Y
local child=Instance.new("Frame",a);child.Size=UDim2.fromOffset(50,60)
return a.AbsoluteSize.Y,list.AbsoluteContentSize.Y
'''),[60,60])

    def test_effective_size_events_and_same_value_assignment(self):
        self.execute('''
getgenv().changes=0
panel:GetPropertyChangedSignal("AbsoluteSize"):Connect(function()changes+=1 end)
a.Size=UDim2.fromOffset(90,25)
''')
        self.assertEqual(self.execute('return changes,panel.AbsoluteSize.X,panel.AbsoluteSize.Y'),[1,90,75])
        self.execute('a.Size=UDim2.fromOffset(90,25)')
        self.assertEqual(self.execute('return changes'),[1])

    def test_zero_scale_detach_and_empty_list(self):
        self.assertEqual(self.execute('''
local scale=Instance.new("UIScale",panel);scale.Scale=0
local zero=panel.AbsoluteSize
scale:Destroy();panel.Parent=nil;local detached=panel.AbsoluteSize
panel.Parent=game:GetService("Players").LocalPlayer.Gui.Screen
a:Destroy();b:Destroy();c:Destroy()
return zero.X,zero.Y,detached.X,detached.Y,panel.AbsoluteSize.X,panel.AbsoluteSize.Y
'''),[0,0,0,0,0,0])


class GuiAutomaticIntegrationTests(unittest.TestCase):
    def test_excessive_measurement_depth_is_bounded(self):
        snapshot=layout_snapshot()
        for index in range(70):
            snapshot['nodes'].append({'id':f'deep-{index}','name':f'Deep{index}','class_name':'Frame',
                'parent':f'deep-{index-1}' if index else 'Screen','properties':{'Visible':True,'AutomaticSize':3,
                'Size':{'$udim2':[{'$udim':[0,0]},{'$udim':[0,0]}]}}})
        snapshot['nodes'].append({'id':'deep-leaf','name':'Leaf','class_name':'Frame','parent':'deep-69',
            'properties':{'Visible':True,'Size':{'$udim2':[{'$udim':[0,20]},{'$udim':[0,20]}]}}})
        host=PersistentLuauHost(snapshot);self.addCleanup(host.close)
        result=host.call({'op':'execute','timeout_ms':1000,'source':'''
local root=game:GetService("Players").LocalPlayer.Gui.Screen.Deep0
local ok,err=pcall(function()return root.AbsoluteSize end)
root:Destroy()
return ok,string.find(err,"depth limit",1,true)~=nil
'''})
        self.assertTrue(result['ok'],result.get('error'));self.assertEqual(result.get('task_errors',[]),[])
        self.assertEqual(result['values'],[False,True])

    def test_received_automatic_frame_and_child_resize(self):
        snapshot=layout_snapshot()
        snapshot['nodes'] += [
            {'id':'auto-panel','name':'Auto','class_name':'Frame','parent':'Screen',
             'properties':{'Visible':True,'AutomaticSize':3,'Size':{'$udim2':[{'$udim':[0,0]},{'$udim':[0,0]}]}}},
            {'id':'auto-list','name':'List','class_name':'UIListLayout','parent':'auto-panel','properties':{'SortOrder':2}},
            {'id':'auto-child','name':'Item','class_name':'Frame','parent':'auto-panel',
             'properties':{'Visible':True,'Size':{'$udim2':[{'$udim':[0,50]},{'$udim':[0,20]}]}}}]
        host=PersistentLuauHost(snapshot);self.addCleanup(host.close)
        query='local p=game:GetService("Players").LocalPlayer.Gui.Screen.Auto;return p.AbsoluteSize.X,p.AbsoluteSize.Y'
        first=host.call({'op':'execute','source':query,'timeout_ms':1000})
        self.assertTrue(first['ok'],first.get('error'));self.assertEqual(first['values'],[50,20])
        update=host.call({'op':'update','delta':{'version':1,'delta':True,'actions':[
            {'sequence':100,'kind':'set','id':'auto-child','fields':{
             'Size':{'$udim2':[{'$udim':[0,80]},{'$udim':[0,40]}]}}}]}})
        self.assertTrue(update['ok'],update.get('error'))
        second=host.call({'op':'execute','source':query,'timeout_ms':1000})
        self.assertTrue(second['ok'],second.get('error'));self.assertEqual(second['values'],[80,40])

    def test_automatic_frame_drives_scrolling_canvas(self):
        host=PersistentLuauHost(layout_snapshot());self.addCleanup(host.close)
        result=host.call({'op':'execute','timeout_ms':1000,'source':SETUP+'''
local scroll=Instance.new("ScrollingFrame",panel.Parent)
scroll.Size=UDim2.fromOffset(100,30);scroll.CanvasSize=UDim2.fromOffset(0,0)
scroll.AutomaticCanvasSize=Enum.AutomaticSize.Y;scroll.ScrollBarThickness=0
panel.Parent=scroll
local initial=scroll.AbsoluteCanvasSize.Y
scroll.CanvasPosition=Vector2.new(0,40)
a:Destroy();b:Destroy()
return initial,scroll.AbsoluteCanvasSize.Y,scroll.CanvasPosition.Y,panel.AbsoluteSize.Y
'''})
        self.assertTrue(result['ok'],result.get('error'));self.assertEqual(result.get('task_errors',[]),[])
        self.assertEqual(result['values'],[70,10,0,10])

    def test_large_received_automatic_list(self):
        snapshot=layout_snapshot()
        snapshot['nodes'] += [
            {'id':'large-auto','name':'LargeAuto','class_name':'Frame','parent':'Screen',
             'properties':{'Visible':True,'AutomaticSize':3,'Size':{'$udim2':[{'$udim':[0,0]},{'$udim':[0,0]}]}}},
            {'id':'large-auto-list','name':'List','class_name':'UIListLayout','parent':'large-auto',
             'properties':{'SortOrder':2,'Padding':{'$udim':[0,1]}}}]
        for index in range(1000):
            snapshot['nodes'].append({'id':f'auto-item-{index}','name':f'Item{index}','class_name':'Frame',
                'parent':'large-auto','properties':{'Visible':True,'LayoutOrder':index,
                'Size':{'$udim2':[{'$udim':[0,20]},{'$udim':[0,2]}]}}})
        host=PersistentLuauHost(snapshot);self.addCleanup(host.close)
        result=host.call({'op':'execute','timeout_ms':1000,'source':'''
local panel=game:GetService("Players").LocalPlayer.Gui.Screen.LargeAuto
return panel.AbsoluteSize.X,panel.AbsoluteSize.Y,panel.Item999.AbsolutePosition.Y
'''})
        self.assertTrue(result['ok'],result.get('error'));self.assertEqual(result.get('task_errors',[]),[])
        self.assertEqual(result['values'],[20,2999,2997])

    def test_automatic_list_demo_in_both_workers(self):
        from test_cframe_transforms import CFrameTransformTests
        demo=Path(__file__).resolve().parents[2]/'runtime/scripts/automatic_list_demo.luau'
        CFrameTransformTests.run_script(self,'local result=(function()\n'+demo.read_text()+'''
end)()
assert(result==Vector2.new(120,164))
assert(game:GetService("Players").LocalPlayer.Gui:FindFirstChild("AutomaticListDemo")==nil)
''',layout_snapshot())

    def test_nested_automatic_tree_uses_shared_measurements(self):
        host=PersistentLuauHost(layout_snapshot());self.addCleanup(host.close)
        result=host.call({'op':'execute','timeout_ms':1000,'source':'''
local screen=game:GetService("Players").LocalPlayer.Gui.Screen
local root=Instance.new("Frame",screen);root.Size=UDim2.fromOffset(0,0);root.AutomaticSize=Enum.AutomaticSize.XY
local parent=root
for i=1,32 do
 local frame=Instance.new("Frame",parent);frame.Size=UDim2.fromOffset(0,0);frame.AutomaticSize=Enum.AutomaticSize.XY
 local padding=Instance.new("UIPadding",frame);padding.PaddingRight=UDim.new(0,1);padding.PaddingBottom=UDim.new(0,1)
 parent=frame
end
local leaf=Instance.new("Frame",parent);leaf.Size=UDim2.fromOffset(50,20)
return root.AbsoluteSize.X,root.AbsoluteSize.Y
'''})
        self.assertTrue(result['ok'],result.get('error'));self.assertEqual(result.get('task_errors',[]),[])
        self.assertEqual(result['values'],[82,52])

    def test_automatic_lists_in_both_workers(self):
        from test_cframe_transforms import CFrameTransformTests
        CFrameTransformTests.run_script(self,SETUP.replace('getgenv().','')+'''
assert(panel.AbsoluteSize==Vector2.new(80,70))
list.FillDirection=Enum.FillDirection.Horizontal
assert(panel.AbsoluteSize==Vector2.new(190,30))
list.HorizontalFlex=Enum.UIFlexAlignment.Fill
assert(panel.AbsoluteSize==Vector2.new(190,30))
''',layout_snapshot())


if __name__=='__main__':unittest.main()
