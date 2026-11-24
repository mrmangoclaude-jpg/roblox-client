"""Native layout regression cases; not a Roblox Studio reference capture."""
import unittest
from persistent_runtime import PersistentLuauHost
from test_display_layout import layout_snapshot
import test_gui_list_layout as list_tests

SETUP=list_tests.SETUP


WRAP = '''
panel.Size=UDim2.fromOffset(130,100)
list.FillDirection=Enum.FillDirection.Horizontal
list.Wraps=true;list.Padding=UDim.new(0,10)
'''


class GuiListWrapTests(unittest.TestCase):
    execute=list_tests.GuiListLayoutTests.execute
    update=list_tests.GuiListLayoutTests.update

    def setUp(self):
        self.host=PersistentLuauHost(layout_snapshot())
        self.addCleanup(self.host.close)
        self.execute(SETUP+WRAP)

    def test_exact_fit_and_next_row(self):
        self.assertEqual(self.execute('''
return a.AbsolutePosition.X,a.AbsolutePosition.Y,b.AbsolutePosition.X,b.AbsolutePosition.Y,
c.AbsolutePosition.X,c.AbsolutePosition.Y,list.AbsoluteContentSize.X,list.AbsoluteContentSize.Y
'''),[0,0,90,0,0,40,130,50])

    def test_rows_align_individually_and_items_align_within_row(self):
        self.assertEqual(self.execute('''
list.HorizontalAlignment=Enum.HorizontalAlignment.Right
list.VerticalAlignment=Enum.VerticalAlignment.Bottom
return a.AbsolutePosition.X,a.AbsolutePosition.Y,b.AbsolutePosition.X,b.AbsolutePosition.Y,
c.AbsolutePosition.X,c.AbsolutePosition.Y,list.AbsoluteContentSize.X,list.AbsoluteContentSize.Y
'''),[0,60,90,50,70,90,130,50])

    def test_vertical_wrap_is_transposed(self):
        self.assertEqual(self.execute('''
panel.Size=UDim2.fromOffset(100,130)
a.Size=UDim2.fromOffset(20,80);b.Size=UDim2.fromOffset(30,40);c.Size=UDim2.fromOffset(10,60)
list.FillDirection=Enum.FillDirection.Vertical
list.HorizontalAlignment=Enum.HorizontalAlignment.Right
list.VerticalAlignment=Enum.VerticalAlignment.Center
return a.AbsolutePosition.X,a.AbsolutePosition.Y,b.AbsolutePosition.X,b.AbsolutePosition.Y,
c.AbsolutePosition.X,c.AbsolutePosition.Y,list.AbsoluteContentSize.X,list.AbsoluteContentSize.Y
'''),[60,0,50,90,90,35,50,130])

    def test_explicit_line_alignment_does_not_move_overall_bounds(self):
        self.assertEqual(self.execute('''
list.VerticalAlignment=Enum.VerticalAlignment.Bottom
local positions={}
for _,mode in {Enum.ItemLineAlignment.Start,Enum.ItemLineAlignment.Center,
 Enum.ItemLineAlignment.End,Enum.ItemLineAlignment.Automatic} do
 list.ItemLineAlignment=mode;table.insert(positions,a.AbsolutePosition.Y)
end
return table.unpack(positions)
'''),[50,55,60,60])

    def test_stretch_updates_descendants_without_changing_authored_size(self):
        self.assertEqual(self.execute('''
list.ItemLineAlignment=Enum.ItemLineAlignment.Stretch
local child=Instance.new("Frame",a);child.Size=UDim2.fromScale(1,1)
local height=a.AbsoluteSize.Y;local nested=child.AbsoluteSize.Y
list.ItemLineAlignment=Enum.ItemLineAlignment.Start
return height,nested,a.Size.Y.Offset,a.AbsoluteSize.Y,b.AbsoluteSize.Y,c.AbsoluteSize.Y
'''),[30,30,20,20,30,10])

    def test_stretch_respects_size_and_aspect_constraints(self):
        self.assertEqual(self.execute('''
list.ItemLineAlignment=Enum.ItemLineAlignment.Stretch
local bound=Instance.new("UISizeConstraint",a);bound.MaxSize=Vector2.new(100,24)
local limited=a.AbsoluteSize.Y
bound:Destroy()
local aspect=Instance.new("UIAspectRatioConstraint",a);aspect.AspectRatio=4
return limited,a.AbsoluteSize.X,a.AbsoluteSize.Y,b.AbsolutePosition.X,list.AbsoluteContentSize.Y
'''),[24,80,20,90,50])

    def test_vertical_stretch_and_center_alignment(self):
        self.assertEqual(self.execute('''
list.FillDirection=Enum.FillDirection.Vertical;panel.Size=UDim2.fromOffset(200,60)
list.HorizontalAlignment=Enum.HorizontalAlignment.Center
list.ItemLineAlignment=Enum.ItemLineAlignment.Stretch
local width=b.AbsoluteSize.X;local x=b.AbsolutePosition.X
list.ItemLineAlignment=Enum.ItemLineAlignment.Center
return width,x,b.AbsoluteSize.X,b.AbsolutePosition.X,c.AbsolutePosition.X,list.AbsoluteContentSize.X
'''),[80,25,40,45,115,150])

    def test_zero_extent_wraps_without_empty_lines(self):
        self.assertEqual(self.execute('''
panel.Size=UDim2.fromOffset(0,100)
return a.AbsolutePosition.Y,b.AbsolutePosition.Y,c.AbsolutePosition.Y,
list.AbsoluteContentSize.X,list.AbsoluteContentSize.Y
'''),[0,30,70,80,80])

    def test_resize_visibility_order_and_wrap_toggle_reflow(self):
        self.assertEqual(self.execute('''
panel.Size=UDim2.fromOffset(129,100)
local first=b.AbsolutePosition.Y;local second=c.AbsolutePosition.X
b.Visible=false
local hidden=c.AbsolutePosition.Y
panel.Size=UDim2.fromOffset(150,100)
local fits=c.AbsolutePosition.X
c.LayoutOrder=-1
local sorted=a.AbsolutePosition.X
list.Wraps=false;b.Visible=true
return first,second,hidden,fits,sorted,list.AbsoluteContentSize.X,list.AbsoluteContentSize.Y
'''),[30,50,30,90,70,200,30])

    def test_oversized_items_and_empty_list(self):
        self.assertEqual(self.execute('''
a.Size=UDim2.fromOffset(200,20)
local size=list.AbsoluteContentSize
local nextY=b.AbsolutePosition.Y
a:Destroy();b:Destroy();c:Destroy()
return size.X,size.Y,nextY,list.AbsoluteContentSize.X,list.AbsoluteContentSize.Y
'''),[200,60,30,0,0])

    def test_scaled_padding_and_parent_padding(self):
        self.assertEqual(self.execute('''
panel.Size=UDim2.fromOffset(150,100)
Instance.new("UIScale",panel).Scale=2
local p=Instance.new("UIPadding",panel);p.PaddingLeft=UDim.new(0,10);p.PaddingRight=UDim.new(0,10)
p.PaddingTop=UDim.new(0,5)
list.Padding=UDim.new(1/13,0)
return a.AbsolutePosition.X,a.AbsolutePosition.Y,b.AbsolutePosition.X,c.AbsolutePosition.Y,
 list.AbsoluteContentSize.X,list.AbsoluteContentSize.Y
'''),[20,10,200,90,260,100])

    def test_negative_spacing_bounds_survive_wrap(self):
        self.assertEqual(self.execute('''
panel.Size=UDim2.fromOffset(100,100);list.Padding=UDim.new(0,-10)
return b.AbsolutePosition.X,b.AbsolutePosition.Y,c.AbsolutePosition.X,c.AbsolutePosition.Y,
list.AbsoluteContentSize.X,list.AbsoluteContentSize.Y
'''),[0,10,30,10,90,40])

    def test_resize_emits_effective_content_and_position_events_once(self):
        self.execute('''
getgenv().sizes=0;getgenv().moves=0
list:GetPropertyChangedSignal("AbsoluteContentSize"):Connect(function() sizes+=1 end)
c:GetPropertyChangedSignal("AbsolutePosition"):Connect(function() moves+=1 end)
panel.Size=UDim2.fromOffset(200,100)
''')
        self.execute('''
panel.Size=UDim2.fromOffset(200,100)
''')
        self.assertEqual(self.execute('''
return sizes,moves,c.AbsolutePosition.X,c.AbsolutePosition.Y,list.AbsoluteContentSize.X,list.AbsoluteContentSize.Y
'''),[1,1,140,0,200,30])

    def test_clone_and_nested_wrapped_layout(self):
        self.assertEqual(self.execute('''
list.ItemLineAlignment=Enum.ItemLineAlignment.Stretch
local inner=Instance.new("UIListLayout",a);inner.Wraps=true;inner.FillDirection=Enum.FillDirection.Horizontal
local x=Instance.new("Frame",a);x.Size=UDim2.fromOffset(50,10)
local y=Instance.new("Frame",a);y.Size=UDim2.fromOffset(40,10)
local clone=panel:Clone();clone.Parent=panel.Parent
return inner.AbsoluteContentSize.X,inner.AbsoluteContentSize.Y,y.AbsolutePosition.Y,
clone.C.AbsolutePosition.Y,clone.B.AbsoluteSize.Y,clone:FindFirstChildOfClass("UIListLayout").Wraps
'''),[50,20,10,40,30,True])

    def test_received_resize_and_enum_updates(self):
        records=[{'id':'remote-panel','name':'Remote','class_name':'Frame','parent':'Screen',
                  'properties':{'Visible':True,'Size':{'$udim2':[{'$udim':[0,130]},{'$udim':[0,100]}]}}},
                 {'id':'remote-list','name':'List','class_name':'UIListLayout','parent':'remote-panel',
                  'properties':{'SortOrder':2,'FillDirection':0,'Wraps':True,'Padding':{'$udim':[0,10]}}}]
        for index,(width,height) in enumerate([(80,20),(40,30),(60,10)]):
            records.append({'id':f'remote-{index}','name':f'Item{index}','class_name':'Frame',
                            'parent':'remote-panel','properties':{'Visible':True,'LayoutOrder':index,
                            'Size':{'$udim2':[{'$udim':[0,width]},{'$udim':[0,height]}]}}})
        self.update([{'sequence':100+i,'kind':'create','node':node} for i,node in enumerate(records)])
        self.execute('getgenv().remote=game:GetService("Players").LocalPlayer.Gui.Screen.Remote')
        self.assertEqual(self.execute('return remote.Item2.AbsolutePosition.Y'),[40])
        self.update([{'sequence':110,'kind':'set','id':'remote-panel','fields':{
            'Size':{'$udim2':[{'$udim':[0,200]},{'$udim':[0,100]}]}}},
            {'sequence':111,'kind':'set','id':'remote-list','fields':{'ItemLineAlignment':3}}])
        self.assertEqual(self.execute('return remote.Item0.AbsolutePosition.Y,remote.Item2.AbsolutePosition.X,remote.Item2.AbsolutePosition.Y'),[10,140,20])


class GuiListWrapIntegrationTests(unittest.TestCase):
    def test_large_received_grid_repacks_after_resize(self):
        snapshot=layout_snapshot()
        snapshot['nodes'] += [
            {'id':'wrap-panel','name':'WrapPanel','class_name':'Frame','parent':'Screen',
             'properties':{'Visible':True,'Size':{'$udim2':[{'$udim':[0,100]},{'$udim':[0,200]}]}}},
            {'id':'wrap-list','name':'List','class_name':'UIListLayout','parent':'wrap-panel',
             'properties':{'SortOrder':2,'FillDirection':0,'Wraps':True}}]
        for index in range(1000):
            snapshot['nodes'].append({'id':f'wrap-{index}','name':f'Item{index}',
                'class_name':'Frame','parent':'wrap-panel','properties':{'Visible':True,'LayoutOrder':999-index,
                'Size':{'$udim2':[{'$udim':[0,10]},{'$udim':[0,2]}]}}})
        host=PersistentLuauHost(snapshot);self.addCleanup(host.close)
        result=host.call({'op':'execute','timeout_ms':1000,'source':'''
local p=game:GetService("Players").LocalPlayer.Gui.Screen.WrapPanel
assert(p.List.AbsoluteContentSize==Vector2.new(100,200))
assert(p.Item0.AbsolutePosition==Vector2.new(90,198))
assert(p.Item999.AbsolutePosition==Vector2.zero)
p.Size=UDim2.fromOffset(50,200)
assert(p.List.AbsoluteContentSize==Vector2.new(50,400))
assert(p.Item0.AbsolutePosition==Vector2.new(40,398))
Instance.new("UIScale",p).Scale=0
assert(p.List.AbsoluteContentSize==Vector2.zero)
return true
'''})
        self.assertTrue(result['ok'],result.get('error'))
        self.assertEqual(result.get('task_errors',[]),[])
        self.assertEqual(result['values'],[True])

    def test_wrapped_demo_in_both_workers(self):
        from pathlib import Path
        from test_cframe_transforms import CFrameTransformTests
        path=Path(__file__).resolve().parents[2]/'runtime/scripts/wrapped_list_demo.luau'
        CFrameTransformTests.run_script(self,'local result=(function()\n'+path.read_text()+'''
end)()
assert(result==Vector2.new(496,32))
assert(game:GetService("Players").LocalPlayer.Gui:FindFirstChild("WrappedListDemo")==nil)
''',layout_snapshot())

    def test_wrapped_auto_canvas_shrinks_after_resize_and_clamps_scroll(self):
        host=PersistentLuauHost(layout_snapshot());self.addCleanup(host.close)
        result=host.call({'op':'execute','timeout_ms':1000,'source':SETUP+WRAP+'''
local scroll=Instance.new("ScrollingFrame",panel.Parent)
scroll.Size=UDim2.fromOffset(130,20);scroll.CanvasSize=UDim2.fromOffset(0,0)
scroll.ScrollBarThickness=0;scroll.AutomaticCanvasSize=Enum.AutomaticSize.Y
list.Parent=scroll;a.Parent=scroll;b.Parent=scroll;c.Parent=scroll
local before=scroll.AbsoluteCanvasSize.Y
scroll.CanvasPosition=Vector2.new(0,30)
local offset=c.AbsolutePosition.Y
scroll.Size=UDim2.fromOffset(200,20)
return before,offset,scroll.AbsoluteCanvasSize.Y,scroll.CanvasPosition.Y,c.AbsolutePosition.Y
'''})
        self.assertTrue(result['ok'],result.get('error'))
        self.assertEqual(result.get('task_errors',[]),[])
        self.assertEqual(result['values'],[50,10,30,10,-10])

    def test_wrapping_and_stretch_in_both_workers(self):
        from test_cframe_transforms import CFrameTransformTests
        CFrameTransformTests.run_script(self,(SETUP+WRAP).replace('getgenv().','')+'''
assert(list.AbsoluteContentSize==Vector2.new(130,50))
assert(c.AbsolutePosition==Vector2.new(0,40))
list.ItemLineAlignment=Enum.ItemLineAlignment.Stretch
assert(a.AbsoluteSize==Vector2.new(80,30))
panel.Size=UDim2.fromOffset(200,100)
assert(c.AbsolutePosition==Vector2.new(140,0))
assert(c.AbsoluteSize==Vector2.new(60,30))
''',layout_snapshot())


if __name__=='__main__':unittest.main()
