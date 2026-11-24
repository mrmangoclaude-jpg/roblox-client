"""Flex behavior through native workers; expectations are documentation-based."""
import unittest
from pathlib import Path
from persistent_runtime import PersistentLuauHost
from test_display_layout import layout_snapshot
import test_gui_list_layout as lists

SETUP=lists.SETUP+'''
panel.Size=UDim2.fromOffset(320,200)
list.FillDirection=Enum.FillDirection.Horizontal;list.Padding=UDim.new(0,10)
'''


class GuiFlexTests(unittest.TestCase):
    execute=lists.GuiListLayoutTests.execute
    update=lists.GuiListLayoutTests.update

    def setUp(self):
        self.host=PersistentLuauHost(layout_snapshot());self.addCleanup(self.host.close)
        self.execute(SETUP)

    def test_fill_grows_from_basis_and_shrinks_on_resize(self):
        self.assertEqual(self.execute('''
list.HorizontalFlex=Enum.UIFlexAlignment.Fill
local aw,bw,cw=a.AbsoluteSize.X,b.AbsoluteSize.X,c.AbsoluteSize.X
panel.Size=UDim2.fromOffset(140,200)
return aw,bw,cw,a.AbsoluteSize.X,b.AbsoluteSize.X,c.AbsoluteSize.X,
b.AbsolutePosition.X,c.AbsolutePosition.X,list.AbsoluteContentSize.X,a.Size.X.Offset
'''),[120,80,100,60,20,40,70,100,140,80])

    def test_main_spacing_modes_and_padding_are_not_added_twice(self):
        self.assertEqual(self.execute('''
panel.Size=UDim2.fromOffset(300,200)
local result={}
for _,mode in {Enum.UIFlexAlignment.SpaceAround,Enum.UIFlexAlignment.SpaceBetween,Enum.UIFlexAlignment.SpaceEvenly} do
 list.HorizontalFlex=mode
 for _,value in {a.AbsolutePosition.X,b.AbsolutePosition.X,c.AbsolutePosition.X,list.AbsoluteContentSize.X} do table.insert(result,value) end
end
return table.unpack(result)
'''),[20,140,220,300,0,140,240,300,30,140,210,300])

    def test_spacing_minimum_and_overflow_preserve_size(self):
        self.assertEqual(self.execute('''
panel.Size=UDim2.fromOffset(190,200)
list.HorizontalFlex=Enum.UIFlexAlignment.SpaceEvenly
return a.AbsolutePosition.X,b.AbsolutePosition.X,c.AbsolutePosition.X,
a.AbsoluteSize.X,b.AbsoluteSize.X,c.AbsoluteSize.X,list.AbsoluteContentSize.X
'''),[10,100,150,80,40,60,220])

    def test_single_item_spacing_and_empty_list(self):
        self.assertEqual(self.execute('''
b:Destroy();c:Destroy();panel.Size=UDim2.fromOffset(100,200)
list.HorizontalFlex=Enum.UIFlexAlignment.SpaceAround
local around=a.AbsolutePosition.X
list.HorizontalFlex=Enum.UIFlexAlignment.SpaceEvenly
local evenly=a.AbsolutePosition.X
list.HorizontalFlex=Enum.UIFlexAlignment.SpaceBetween
local between=a.AbsolutePosition.X
a:Destroy()
return around,evenly,between,list.AbsoluteContentSize.X,list.AbsoluteContentSize.Y
'''),[10,10,0,0,0])

    def test_vertical_fill_and_cross_fill(self):
        self.assertEqual(self.execute('''
list.FillDirection=Enum.FillDirection.Vertical
list.VerticalFlex=Enum.UIFlexAlignment.Fill
list.HorizontalFlex=Enum.UIFlexAlignment.Fill
return a.AbsoluteSize.X,a.AbsoluteSize.Y,b.AbsoluteSize.X,b.AbsoluteSize.Y,
c.AbsoluteSize.X,c.AbsoluteSize.Y,b.AbsolutePosition.Y,c.AbsolutePosition.Y,list.AbsoluteContentSize.Y
'''),[320,60,320,70,320,50,70,150,200])

    def test_wrap_is_packed_before_growth_and_each_line_fills(self):
        self.assertEqual(self.execute('''
panel.Size=UDim2.fromOffset(150,100);list.Wraps=true
list.HorizontalFlex=Enum.UIFlexAlignment.Fill
return a.AbsoluteSize.X,b.AbsoluteSize.X,c.AbsoluteSize.X,
b.AbsolutePosition.X,c.AbsolutePosition.X,c.AbsolutePosition.Y,list.AbsoluteContentSize.X,list.AbsoluteContentSize.Y
'''),[90,50,150,100,0,40,150,50])

    def test_cross_fill_distributes_between_rows_and_stretches_automatic_items(self):
        self.assertEqual(self.execute('''
panel.Size=UDim2.fromOffset(130,100);list.Wraps=true
list.VerticalFlex=Enum.UIFlexAlignment.Fill
return a.AbsoluteSize.Y,b.AbsoluteSize.Y,c.AbsoluteSize.Y,
c.AbsolutePosition.Y,list.AbsoluteContentSize.Y
'''),[55,55,35,65,100])

    def test_cross_spacing_modes_and_explicit_line_alignment(self):
        self.assertEqual(self.execute('''
panel.Size=UDim2.fromOffset(130,100);list.Wraps=true
list.VerticalFlex=Enum.UIFlexAlignment.SpaceEvenly
local first=a.AbsolutePosition.Y;local second=c.AbsolutePosition.Y
local autoHeight=a.AbsoluteSize.Y
list.ItemLineAlignment=Enum.ItemLineAlignment.End
return first,second,autoHeight,a.AbsolutePosition.Y,a.AbsoluteSize.Y,list.AbsoluteContentSize.Y
'''),[20,70,30,30,20,100])

    def test_minimum_and_maximum_caps_redistribute_remaining_space(self):
        self.assertEqual(self.execute('''
list.HorizontalFlex=Enum.UIFlexAlignment.Fill
local bound=Instance.new("UISizeConstraint",a);bound.MaxSize=Vector2.new(90,math.huge)
local aw,bw,cw=a.AbsoluteSize.X,b.AbsoluteSize.X,c.AbsoluteSize.X
bound.MinSize=Vector2.new(70,0)
panel.Size=UDim2.fromOffset(100,200)
return aw,bw,cw,a.AbsoluteSize.X,b.AbsoluteSize.X,c.AbsoluteSize.X,list.AbsoluteContentSize.X
'''),[90,95,115,70,0,10,100])

    def test_insufficient_space_stops_at_minimum_and_reports_overflow(self):
        self.assertEqual(self.execute('''
list.HorizontalFlex=Enum.UIFlexAlignment.Fill
for _,item in {a,b,c} do Instance.new("UISizeConstraint",item).MinSize=Vector2.new(40,0) end
panel.Size=UDim2.fromOffset(100,200)
return a.AbsoluteSize.X,b.AbsoluteSize.X,c.AbsoluteSize.X,list.AbsoluteContentSize.X
'''),[40,40,40,140])

    def test_aspect_size_is_fixed_while_other_items_fill(self):
        self.assertEqual(self.execute('''
Instance.new("UIAspectRatioConstraint",a).AspectRatio=4
list.HorizontalFlex=Enum.UIFlexAlignment.Fill
return a.AbsoluteSize.X,a.AbsoluteSize.Y,b.AbsoluteSize.X,c.AbsoluteSize.X,list.AbsoluteContentSize.X
'''),[80,20,100,120,320])

    def test_flex_none_override_keeps_fixed_item(self):
        self.assertEqual(self.execute('''
list.HorizontalFlex=Enum.UIFlexAlignment.Fill
local flex=Instance.new("UIFlexItem",a)
return flex.FlexMode==Enum.UIFlexMode.None,flex.ItemLineAlignment==Enum.ItemLineAlignment.Automatic,
a.AbsoluteSize.X,b.AbsoluteSize.X,c.AbsoluteSize.X,flex.GrowRatio,flex.ShrinkRatio
'''),[True,True,80,100,120,0,0])

    def test_grow_shrink_and_fill_modes(self):
        self.assertEqual(self.execute('''
local flex=Instance.new("UIFlexItem",b);flex.FlexMode=Enum.UIFlexMode.Grow
local grown=b.AbsoluteSize.X
panel.Size=UDim2.fromOffset(180,200)
local notShrunk=b.AbsoluteSize.X
flex.FlexMode=Enum.UIFlexMode.Shrink
local shrunk=b.AbsoluteSize.X
panel.Size=UDim2.fromOffset(320,200)
local notGrown=b.AbsoluteSize.X
flex.FlexMode=Enum.UIFlexMode.Fill
return grown,notShrunk,shrunk,notGrown,b.AbsoluteSize.X
'''),[160,40,20,40,160])

    def test_custom_ratios_grow_and_shrink_with_zero_cap(self):
        self.assertEqual(self.execute('''
local fa=Instance.new("UIFlexItem",a);fa.FlexMode=Enum.UIFlexMode.Custom;fa.GrowRatio=1;fa.ShrinkRatio=1
local fb=Instance.new("UIFlexItem",b);fb.FlexMode=Enum.UIFlexMode.Custom;fb.GrowRatio=3;fb.ShrinkRatio=3
local aw,bw=a.AbsoluteSize.X,b.AbsoluteSize.X
panel.Size=UDim2.fromOffset(140,200)
return aw,bw,a.AbsoluteSize.X,b.AbsoluteSize.X,c.AbsoluteSize.X,list.AbsoluteContentSize.X
'''),[110,130,60,0,60,140])

    def test_large_and_tiny_weights_after_first_item_hits_cap(self):
        self.assertEqual(self.execute('''
c:Destroy();panel.Size=UDim2.fromOffset(200,200)
local fa=Instance.new("UIFlexItem",a);fa.FlexMode=Enum.UIFlexMode.Custom;fa.GrowRatio=1e20
local fb=Instance.new("UIFlexItem",b);fb.FlexMode=Enum.UIFlexMode.Custom;fb.GrowRatio=1e-20
Instance.new("UISizeConstraint",a).MaxSize=Vector2.new(90,math.huge)
return a.AbsoluteSize.X,b.AbsoluteSize.X,list.AbsoluteContentSize.X
'''),[90,100,200])

    def test_item_alignment_override_and_automatic_inheritance(self):
        self.assertEqual(self.execute('''
list.ItemLineAlignment=Enum.ItemLineAlignment.End
local flex=Instance.new("UIFlexItem",a)
local inherited=a.AbsolutePosition.Y
flex.ItemLineAlignment=Enum.ItemLineAlignment.Start
local start=a.AbsolutePosition.Y
flex.ItemLineAlignment=Enum.ItemLineAlignment.Stretch
return inherited,start,a.AbsoluteSize.Y,a.Size.Y.Offset
'''),[10,0,30,20])

    def test_flex_item_clone_reparent_and_enum_validation(self):
        self.assertEqual(self.execute('''
local flex=Instance.new("UIFlexItem",a);flex.FlexMode=Enum.UIFlexMode.Fill
flex.ItemLineAlignment=Enum.ItemLineAlignment.Center
local clone=panel:Clone();clone.Parent=panel.Parent
local copied=clone.B:FindFirstChildOfClass("UIFlexItem")
local size=clone.B.AbsoluteSize.X
flex.Parent=b
return copied.FlexMode==Enum.UIFlexMode.Fill,copied.ItemLineAlignment==Enum.ItemLineAlignment.Center,
size,a.AbsoluteSize.X,b.AbsoluteSize.X,
pcall(function()flex.FlexMode=Enum.UIFlexAlignment.Fill end),pcall(function()flex.GrowRatio=-1 end),
pcall(function()flex.ShrinkRatio=math.huge end),(pcall(function()flex.GrowRatio="1" end))
'''),[True,True,200,80,160,False,False,False,False])

    def test_flex_change_signals_and_descendants(self):
        self.execute('''
getgenv().sizes=0
a:GetPropertyChangedSignal("AbsoluteSize"):Connect(function()sizes+=1 end)
getgenv().child=Instance.new("Frame",a);child.Size=UDim2.fromScale(1,1)
list.HorizontalFlex=Enum.UIFlexAlignment.Fill
''')
        self.assertEqual(self.execute('return sizes,child.AbsoluteSize.X,child.AbsoluteSize.Y'),[1,120,20])
        self.execute('list.HorizontalFlex=Enum.UIFlexAlignment.Fill')
        self.assertEqual(self.execute('return sizes'),[1])

    def test_scale_and_padding_share_one_coordinate_system(self):
        values=self.execute('''
Instance.new("UIScale",panel).Scale=2
local pad=Instance.new("UIPadding",panel);pad.PaddingLeft=UDim.new(0,10);pad.PaddingRight=UDim.new(0,10)
list.HorizontalFlex=Enum.UIFlexAlignment.Fill
local sum=a.AbsoluteSize.X+b.AbsoluteSize.X+c.AbsoluteSize.X
return sum,b.AbsolutePosition.X-a.AbsolutePosition.X-a.AbsoluteSize.X,
c.AbsolutePosition.X+c.AbsoluteSize.X,list.AbsoluteContentSize.X
''')
        for actual,expected in zip(values,[560,20,620,600]):self.assertAlmostEqual(actual,expected,places=6)

    def test_zero_scale_and_duplicate_flex_items(self):
        self.assertEqual(self.execute('''
list.HorizontalFlex=Enum.UIFlexAlignment.Fill;list.VerticalFlex=Enum.UIFlexAlignment.Fill
Instance.new("UIScale",panel).Scale=0
local size=list.AbsoluteContentSize
Instance.new("UIFlexItem",a);Instance.new("UIFlexItem",a)
return size.X,size.Y,(pcall(function()return a.AbsoluteSize end))
'''),[0,0,False])

    def test_hidden_items_do_not_take_flex_space(self):
        self.assertEqual(self.execute('''
list.HorizontalFlex=Enum.UIFlexAlignment.Fill
b.Visible=false
return a.AbsoluteSize.X,c.AbsoluteSize.X,c.AbsolutePosition.X,list.AbsoluteContentSize.X
'''),[165,145,175,320])

    def test_custom_grow_reserves_minimum_outer_spacing(self):
        self.assertEqual(self.execute('''
local flex=Instance.new("UIFlexItem",a);flex.FlexMode=Enum.UIFlexMode.Grow
list.HorizontalFlex=Enum.UIFlexAlignment.SpaceEvenly
return a.AbsolutePosition.X,a.AbsoluteSize.X,b.AbsolutePosition.X,c.AbsolutePosition.X,
list.AbsoluteContentSize.X
'''),[10,180,200,250,320])

    def test_cross_fill_shrink_respects_item_minima(self):
        self.assertEqual(self.execute('''
panel.Size=UDim2.fromOffset(130,40);list.Wraps=true
list.VerticalFlex=Enum.UIFlexAlignment.Fill
Instance.new("UISizeConstraint",b).MinSize=Vector2.new(0,30)
return a.AbsoluteSize.Y,b.AbsoluteSize.Y,c.AbsoluteSize.Y,c.AbsolutePosition.Y,list.AbsoluteContentSize.Y
'''),[30,30,0,40,40])


class GuiFlexIntegrationTests(unittest.TestCase):
    def test_auto_canvas_uses_constrained_flex_content(self):
        host=PersistentLuauHost(layout_snapshot());self.addCleanup(host.close)
        result=host.call({'op':'execute','timeout_ms':1000,'source':SETUP+'''
local scroll=Instance.new("ScrollingFrame",panel.Parent)
scroll.Size=UDim2.fromOffset(150,20);scroll.CanvasSize=UDim2.fromOffset(0,0)
scroll.ScrollBarThickness=0;scroll.AutomaticCanvasSize=Enum.AutomaticSize.Y
list.Parent=scroll;a.Parent=scroll;b.Parent=scroll;c.Parent=scroll
list.HorizontalFlex=Enum.UIFlexAlignment.Fill;list.VerticalFlex=Enum.UIFlexAlignment.Fill;list.Wraps=true
for _,item in {a,b,c} do Instance.new("UISizeConstraint",item).MinSize=Vector2.new(0,item.Size.Y.Offset) end
local height=scroll.AbsoluteCanvasSize.Y
scroll.CanvasPosition=Vector2.new(0,30)
local position=c.AbsolutePosition.Y
scroll.Size=UDim2.fromOffset(320,20)
return height,position,scroll.AbsoluteCanvasSize.Y,scroll.CanvasPosition.Y,a.AbsoluteSize.X
'''})
        self.assertTrue(result['ok'],result.get('error'))
        self.assertEqual(result.get('task_errors',[]),[])
        self.assertEqual(result['values'],[50,10,30,10,120])

    def test_thousand_items_with_different_caps_share_the_remainder(self):
        snapshot=layout_snapshot()
        snapshot['nodes'] += [
            {'id':'many-panel','name':'Many','class_name':'Frame','parent':'Screen',
             'properties':{'Visible':True,'Size':{'$udim2':[{'$udim':[0,8000]},{'$udim':[0,100]}]}}},
            {'id':'many-list','name':'List','class_name':'UIListLayout','parent':'many-panel',
             'properties':{'FillDirection':0,'HorizontalFlex':1,'SortOrder':2}}]
        for index in range(1000):
            snapshot['nodes'] += [
                {'id':f'many-{index}','name':f'Item{index}','class_name':'Frame','parent':'many-panel',
                 'properties':{'Visible':True,'LayoutOrder':index,
                 'Size':{'$udim2':[{'$udim':[0,1]},{'$udim':[0,10]}]}}},
                {'id':f'max-{index}','name':'Bound','class_name':'UISizeConstraint','parent':f'many-{index}',
                 'properties':{'MaxSize':{'$vector2':[2+(index%10),100]}}}]
        host=PersistentLuauHost(snapshot);self.addCleanup(host.close)
        result=host.call({'op':'execute','timeout_ms':1000,'source':'''
local p=game:GetService("Players").LocalPlayer.Gui.Screen.Many
assert(math.abs(p.List.AbsoluteContentSize.X-6500)<.001)
assert(p.Item0.AbsoluteSize.X==2 and p.Item9.AbsoluteSize.X==11)
assert(p.Item999.AbsolutePosition.X==6489)
p.Size=UDim2.fromOffset(3000,100)
return p.List.AbsoluteContentSize.X,p.Item0.AbsoluteSize.X,p.Item1.AbsoluteSize.X,p.Item9.AbsoluteSize.X
'''})
        self.assertTrue(result['ok'],result.get('error'));self.assertEqual(result.get('task_errors',[]),[])
        for actual,expected in zip(result['values'],[3000,2,3,3.125]):self.assertAlmostEqual(actual,expected,places=6)

    def test_flex_demo_in_both_workers(self):
        from test_cframe_transforms import CFrameTransformTests
        demo=Path(__file__).resolve().parents[2]/'runtime/scripts/flex_list_demo.luau'
        CFrameTransformTests.run_script(self,'local result=(function()\n'+demo.read_text()+'''
end)()
assert(result==Vector2.new(540,48))
assert(game:GetService("Players").LocalPlayer.Gui:FindFirstChild("FlexListDemo")==nil)
''',layout_snapshot())

    def test_flex_modes_and_enum_metadata_in_both_workers(self):
        from test_cframe_transforms import CFrameTransformTests
        CFrameTransformTests.run_script(self,SETUP.replace('getgenv().','')+'''
for index,item in Enum.UIFlexMode:GetEnumItems() do
 assert(item.Value==index-1 and item.EnumType==Enum.UIFlexMode)
 assert(rawequal(item,Enum.UIFlexMode:FromValue(index-1)))
end
list.HorizontalFlex=Enum.UIFlexAlignment.Fill
assert(a.AbsoluteSize.X==120 and b.AbsoluteSize.X==80 and c.AbsoluteSize.X==100)
local flex=Instance.new("UIFlexItem",a);flex.FlexMode=Enum.UIFlexMode.None
assert(a.AbsoluteSize.X==80 and b.AbsoluteSize.X==100 and c.AbsoluteSize.X==120)
list.HorizontalFlex=Enum.UIFlexAlignment.SpaceBetween
assert(a.AbsoluteSize.X==80 and c.AbsolutePosition.X==260)
''',layout_snapshot())

    def test_received_flex_item_ratio_and_layout_updates(self):
        snapshot=layout_snapshot()
        snapshot['nodes'] += [
            {'id':'flex-panel','name':'FlexPanel','class_name':'Frame','parent':'Screen',
             'properties':{'Visible':True,'Size':{'$udim2':[{'$udim':[0,200]},{'$udim':[0,100]}]}}},
            {'id':'flex-list','name':'List','class_name':'UIListLayout','parent':'flex-panel',
             'properties':{'SortOrder':2,'FillDirection':0,'HorizontalFlex':1}},
            {'id':'flex-a','name':'A','class_name':'Frame','parent':'flex-panel',
             'properties':{'Visible':True,'Size':{'$udim2':[{'$udim':[0,50]},{'$udim':[0,20]}]}}},
            {'id':'flex-b','name':'B','class_name':'Frame','parent':'flex-panel',
             'properties':{'Visible':True,'Size':{'$udim2':[{'$udim':[0,50]},{'$udim':[0,40]}]}}},
            {'id':'flex-component','name':'Flex','class_name':'UIFlexItem','parent':'flex-a',
             'properties':{'FlexMode':4,'GrowRatio':3,'ShrinkRatio':1,'ItemLineAlignment':3}}]
        host=PersistentLuauHost(snapshot);self.addCleanup(host.close)
        query='local p=game:GetService("Players").LocalPlayer.Gui.Screen.FlexPanel;return p.A.AbsoluteSize.X,p.B.AbsoluteSize.X,p.A.AbsolutePosition.Y'
        first=host.call({'op':'execute','source':query,'timeout_ms':1000})
        self.assertTrue(first['ok'],first.get('error'));self.assertEqual(first['values'],[125,75,20])
        updated=host.call({'op':'update','delta':{'version':1,'delta':True,'actions':[
            {'sequence':100,'kind':'set','id':'flex-component','fields':{'GrowRatio':1,'ItemLineAlignment':1}}]}})
        self.assertTrue(updated['ok'],updated.get('error'))
        second=host.call({'op':'execute','source':query,'timeout_ms':1000})
        self.assertTrue(second['ok'],second.get('error'));self.assertEqual(second['values'],[100,100,0])


if __name__=='__main__':unittest.main()
