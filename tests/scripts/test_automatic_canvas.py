"""Automatic canvas geometry, dependency bounds, and persistent local updates."""
import unittest
import test_scrolling_layout as scrolling
from persistent_runtime import PersistentLuauHost
from test_display_layout import layout_snapshot


class AutomaticCanvasTests(unittest.TestCase):
    execute=scrolling.ScrollingLayoutTests.execute

    def setUp(self):
        self.host=PersistentLuauHost(layout_snapshot())
        self.addCleanup(self.host.close)
        self.execute(scrolling.SETUP+'''
child:Destroy();scroll.CanvasSize=UDim2.fromOffset(0,0)
scroll.ScrollBarThickness=0;scroll.ScrollingDirection=Enum.ScrollingDirection.Y
scroll.AutomaticCanvasSize=Enum.AutomaticSize.Y
''')

    def test_free_children_resize_selected_axes_and_keep_authored_minimum(self):
        self.assertEqual(self.execute('''
scroll.CanvasSize=UDim2.fromOffset(500,100)
a=Instance.new("Frame",scroll);a.Size=UDim2.fromOffset(600,250)
a.Position=UDim2.fromOffset(20,20)
local y=scroll.AbsoluteCanvasSize
scroll.AutomaticCanvasSize=Enum.AutomaticSize.X
local x=scroll.AbsoluteCanvasSize
scroll.AutomaticCanvasSize=Enum.AutomaticSize.XY
local both=scroll.AbsoluteCanvasSize
scroll.AutomaticCanvasSize=Enum.AutomaticSize.None
return y.X,y.Y,x.X,x.Y,both.X,both.Y,scroll.AbsoluteCanvasSize.X,scroll.AbsoluteCanvasSize.Y,
 scroll.CanvasSize.X.Offset,scroll.CanvasSize.Y.Offset
'''),[500,270,620,100,620,270,500,100,500,100])

    def test_list_growth_hidden_removal_and_scroll_clamping(self):
        self.assertEqual(self.execute('''
list=Instance.new("UIListLayout",scroll);list.SortOrder=Enum.SortOrder.LayoutOrder
list.Padding=UDim.new(0,5)
a=Instance.new("Frame",scroll);a.Size=UDim2.fromOffset(100,40)
b=Instance.new("Frame",scroll);b.Size=UDim2.fromOffset(120,60)
local initial=scroll.AbsoluteCanvasSize.Y
a.Size=UDim2.fromOffset(100,300)
local grown=scroll.AbsoluteCanvasSize.Y
scroll.CanvasPosition=Vector2.new(0,160)
a.Visible=false
local shrunk=scroll.AbsoluteCanvasSize.Y
local offset=scroll.CanvasPosition.Y
b:Destroy()
return initial,grown,shrunk,offset,scroll.AbsoluteCanvasSize.Y,list.AbsoluteContentSize.Y
'''),[105,365,60,0,0,0])

    def test_list_alignment_and_scroll_do_not_feed_back_into_content_size(self):
        self.assertEqual(self.execute('''
list=Instance.new("UIListLayout",scroll)
list.VerticalAlignment=Enum.VerticalAlignment.Bottom
a=Instance.new("Frame",scroll);a.Size=UDim2.fromOffset(100,400)
local before=scroll.AbsoluteCanvasSize.Y
scroll.CanvasPosition=Vector2.new(0,100)
return before,scroll.AbsoluteCanvasSize.Y,list.AbsoluteContentSize.Y,a.AbsolutePosition.Y
'''),[400,400,400,-50])

    def test_offset_padding_and_scale_are_included_once(self):
        self.assertEqual(self.execute('''
Instance.new("UIScale",scroll).Scale=2
local padding=Instance.new("UIPadding",scroll)
padding.PaddingTop=UDim.new(0,10);padding.PaddingBottom=UDim.new(0,20)
list=Instance.new("UIListLayout",scroll);list.Padding=UDim.new(0,5)
a=Instance.new("Frame",scroll);a.Size=UDim2.fromOffset(100,40)
b=Instance.new("Frame",scroll);b.Size=UDim2.fromOffset(100,60)
return scroll.AbsoluteCanvasSize.Y,list.AbsoluteContentSize.Y,a.AbsolutePosition.Y,
 scroll.CanvasSize.Y.Offset
'''),[270,210,70,0])

    def test_insets_do_not_clip_automatic_content_or_count_left_gutter_twice(self):
        self.assertEqual(self.execute('''
scroll.ScrollBarThickness=10;scroll.AutomaticCanvasSize=Enum.AutomaticSize.XY
scroll.VerticalScrollBarInset=Enum.ScrollBarInset.ScrollBar
scroll.VerticalScrollBarPosition=Enum.VerticalScrollBarPosition.Left
a=Instance.new("Frame",scroll);a.Size=UDim2.fromOffset(100,400)
return scroll.AbsoluteCanvasSize.X,scroll.AbsoluteCanvasSize.Y,
 scroll.AbsoluteWindowSize.X,scroll.AbsoluteWindowSize.Y,a.AbsolutePosition.X
'''),[100,400,290,200,110])

    def test_parent_resize_recomputes_scale_content_and_fires_size_event(self):
        self.execute('''
a=Instance.new("Frame",scroll);a.Size=UDim2.new(0,100,.5,0)
sizes=0
scroll:GetPropertyChangedSignal("AbsoluteCanvasSize"):Connect(function()sizes+=1 end)
scroll.Size=UDim2.fromOffset(300,400)
''')
        self.assertEqual(self.execute('return sizes,scroll.AbsoluteCanvasSize.Y,a.AbsoluteSize.Y'),[1,200,200])

    def test_zero_scale_and_detached_automatic_canvas(self):
        self.assertEqual(self.execute('''
a=Instance.new("Frame",scroll);a.Size=UDim2.fromOffset(100,400)
local scale=Instance.new("UIScale",scroll);scale.Scale=0
local zero=scroll.AbsoluteCanvasSize
scroll.Parent=nil
return zero.X,zero.Y,scroll.AbsoluteCanvasSize.X,scroll.AbsoluteCanvasSize.Y
'''),[0,0,0,0])

    def test_convergent_scale_dependency_is_solved(self):
        values=self.execute('''
a=Instance.new("Frame",scroll);a.Size=UDim2.new(0,100,.5,200)
return scroll.AbsoluteCanvasSize.Y,a.AbsoluteSize.Y
''')
        for value in values:self.assertAlmostEqual(value,400,places=4)

    def test_scale_padding_dependency_is_solved(self):
        values=self.execute('''
local padding=Instance.new("UIPadding",scroll)
padding.PaddingTop=UDim.new(.1,0);padding.PaddingBottom=UDim.new(.1,0)
a=Instance.new("Frame",scroll);a.Size=UDim2.fromOffset(100,400)
return scroll.AbsoluteCanvasSize.Y,a.AbsolutePosition.Y-scroll.AbsolutePosition.Y
''')
        self.assertAlmostEqual(values[0],500,places=4)
        self.assertAlmostEqual(values[1],50,places=4)

    def test_divergent_dependency_is_bounded_and_recoverable(self):
        self.assertEqual(self.execute('''
a=Instance.new("Frame",scroll);a.Size=UDim2.new(0,100,1,1)
local ok,err=pcall(function()return scroll.AbsoluteCanvasSize end)
a.Size=UDim2.fromOffset(100,20)
return ok,string.find(err,"cyclic size dependency",1,true)~=nil,scroll.AbsoluteCanvasSize.Y
'''),[False,True,20])

    def test_hidden_divergent_child_does_not_affect_canvas(self):
        self.assertEqual(self.execute('''
a=Instance.new("Frame",scroll);a.Size=UDim2.new(0,100,1,1);a.Visible=false
b=Instance.new("Frame",scroll);b.Size=UDim2.fromOffset(100,80)
return scroll.AbsoluteCanvasSize.Y
'''),[80])

    def test_anchor_and_size_constraints_are_measured_after_layout(self):
        self.assertEqual(self.execute('''
a=Instance.new("Frame",scroll);a.Size=UDim2.fromOffset(100,40)
a.Position=UDim2.fromOffset(0,100);a.AnchorPoint=Vector2.new(0,.5)
Instance.new("UISizeConstraint",a).MinSize=Vector2.new(100,80)
return scroll.AbsoluteCanvasSize.Y,a.AbsolutePosition.Y
'''),[140,110])

    def test_nested_scroller_contributes_its_outer_size_only(self):
        self.assertEqual(self.execute('''
local inner=Instance.new("ScrollingFrame",scroll)
inner.Size=UDim2.fromOffset(100,80);inner.Position=UDim2.fromOffset(0,20)
inner.CanvasSize=UDim2.fromOffset(0,0);inner.AutomaticCanvasSize=Enum.AutomaticSize.Y
a=Instance.new("Frame",inner);a.Size=UDim2.fromOffset(80,500)
return scroll.AbsoluteCanvasSize.Y,inner.AbsoluteCanvasSize.Y,a.AbsoluteSize.Y
'''),[100,500,500])

    def test_changes_fire_once_without_repeated_layout_drift(self):
        self.execute('''
a=Instance.new("Frame",scroll);a.Size=UDim2.fromOffset(100,300)
sizes=0;positions=0
scroll:GetPropertyChangedSignal("AbsoluteCanvasSize"):Connect(function()sizes+=1 end)
scroll:GetPropertyChangedSignal("CanvasPosition"):Connect(function()positions+=1 end)
scroll.CanvasPosition=Vector2.new(0,100)
''')
        self.assertEqual(self.execute('return sizes,positions'),[0,1])
        self.execute('a.Size=UDim2.fromOffset(100,50)')
        self.assertEqual(self.execute('return sizes,positions,scroll.CanvasPosition.Y'),[1,2,0])
        self.assertEqual(self.execute('return sizes,positions,scroll.AbsoluteCanvasSize.Y'),[1,2,50])

    def test_content_clone_reparent_and_destroy_remeasure(self):
        self.assertEqual(self.execute('''
list=Instance.new("UIListLayout",scroll)
a=Instance.new("Frame",scroll);a.Size=UDim2.fromOffset(100,70)
local clone=a:Clone();clone.Parent=scroll
local two=scroll.AbsoluteCanvasSize.Y
clone.Parent=scroll.Parent
local one=scroll.AbsoluteCanvasSize.Y
a:Destroy()
return two,one,scroll.AbsoluteCanvasSize.Y
'''),[140,70,0])


class AutomaticCanvasOneShotTests(unittest.TestCase):
    def test_large_received_list_and_updates_remeasure_the_same_host(self):
        snapshot=layout_snapshot()
        snapshot['nodes'] += [
            {'id':'auto','name':'Auto','class_name':'ScrollingFrame','parent':'Screen','properties':{
                'Size':{'$udim2':[{'$udim':[0,300]},{'$udim':[0,200]}]},
                'CanvasSize':{'$udim2':[{'$udim':[0,0]},{'$udim':[0,0]}]},
                'AutomaticCanvasSize':2,'ScrollingDirection':2,'ScrollBarThickness':0}},
            {'id':'list','name':'List','class_name':'UIListLayout','parent':'auto','properties':{
                'FillDirection':1,'SortOrder':2,'Padding':{'$udim':[0,1]}}}]
        for index in range(1000):
            snapshot['nodes'].append({'id':f'item-{index}','name':f'Item{index}',
                'class_name':'Frame','parent':'auto','properties':{'Visible':True,'LayoutOrder':index,
                'Size':{'$udim2':[{'$udim':[0,100]},{'$udim':[0,2]}]}}})
        host=PersistentLuauHost(snapshot)
        self.addCleanup(host.close)
        source='''local s=game:GetService("Players").LocalPlayer.Gui.Screen.Auto
return s.AbsoluteCanvasSize.Y,s.List.AbsoluteContentSize.Y,s.Item999.AbsolutePosition.Y'''
        result=host.call({'op':'execute','source':source,'timeout_ms':1000})
        self.assertTrue(result['ok'],result.get('error'))
        self.assertEqual(result['values'],[2999,2999,2997])
        update=host.call({'op':'update','timeout_ms':100,'delta':{'version':1,'delta':True,'actions':[
            {'sequence':101,'kind':'set','id':'item-0','fields':{'Visible':False}},
            {'sequence':102,'kind':'set','id':'item-1','fields':{
                'Size':{'$udim2':[{'$udim':[0,100]},{'$udim':[0,20]}]}}}]}})
        self.assertTrue(update['ok'],update.get('error'))
        result=host.call({'op':'execute','source':source,'timeout_ms':1000})
        self.assertTrue(result['ok'],result.get('error'))
        self.assertEqual(result['values'],[3014,3014,3012])

    def test_automatic_list_canvas_in_both_workers(self):
        from test_cframe_transforms import CFrameTransformTests
        CFrameTransformTests.run_script(self,scrolling.SETUP+'''
child.Position=UDim2.fromOffset(0,0);child.Size=UDim2.fromOffset(100,400)
scroll.CanvasSize=UDim2.fromOffset(0,0);scroll.AutomaticCanvasSize=Enum.AutomaticSize.Y
local list=Instance.new("UIListLayout",scroll)
assert(scroll.AbsoluteCanvasSize.Y==400)
scroll.CanvasPosition=Vector2.new(0,100)
assert(child.AbsolutePosition.Y==-50)
child.Visible=false
assert(scroll.AbsoluteCanvasSize.Y==0)
assert(scroll.CanvasPosition.Y==0)
''',layout_snapshot())

if __name__=='__main__':unittest.main()
