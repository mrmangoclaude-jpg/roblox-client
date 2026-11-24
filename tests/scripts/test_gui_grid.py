"""Native grid layout tests; Studio geometry parity has not been captured."""
import unittest
from pathlib import Path
from persistent_runtime import PersistentLuauHost
from test_display_layout import layout_snapshot
import test_gui_list_layout as lists

SETUP='''
local screen=game:GetService("Players").LocalPlayer.Gui.Screen
getgenv().panel=Instance.new("Frame",screen);panel.Size=UDim2.fromOffset(130,100)
getgenv().grid=Instance.new("UIGridLayout",panel)
grid.CellSize=UDim2.fromOffset(40,20);grid.CellPadding=UDim2.fromOffset(5,10)
getgenv().items={}
for i=1,5 do
 local item=Instance.new("Frame",panel);item.Name="Item"..i
 item.Size=UDim2.fromOffset(999,999);item.Position=UDim2.fromOffset(100,100)
 table.insert(items,item)
end
'''


class GuiGridTests(unittest.TestCase):
    execute=lists.GuiListLayoutTests.execute
    update=lists.GuiListLayoutTests.update

    def setUp(self):
        self.host=PersistentLuauHost(layout_snapshot());self.addCleanup(self.host.close)
        self.execute(SETUP)

    def test_horizontal_cells_and_computed_fields(self):
        self.assertEqual(self.execute('''
items[1].AnchorPoint=Vector2.new(.5,.5);items[1].Rotation=45
return items[1].AbsoluteSize.X,items[1].AbsoluteSize.Y,items[1].AbsolutePosition.X,items[1].AbsoluteRotation,
items[3].AbsolutePosition.X,items[4].AbsolutePosition.Y,items[5].AbsolutePosition.X,
grid.AbsoluteContentSize.X,grid.AbsoluteContentSize.Y,grid.AbsoluteCellCount.X,grid.AbsoluteCellCount.Y,
grid.AbsoluteCellSize.X,grid.AbsoluteCellSize.Y,items[1].Size.X.Offset,items[1].Rotation
'''),[40,20,0,0,90,30,45,130,50,3,2,40,20,999,45])

    def test_vertical_fill_and_maximum_cells(self):
        self.assertEqual(self.execute('''
grid.FillDirection=Enum.FillDirection.Vertical
local x,y=items[4].AbsolutePosition.X,items[3].AbsolutePosition.Y
local size=grid.AbsoluteContentSize
grid.FillDirectionMaxCells=2
return x,y,size.X,size.Y,items[3].AbsolutePosition.X,items[3].AbsolutePosition.Y,
grid.AbsoluteCellCount.X,grid.AbsoluteCellCount.Y
'''),[45,60,85,80,45,0,3,2])

    def test_all_start_corners(self):
        self.assertEqual(self.execute('''
local result={}
for _,corner in Enum.StartCorner:GetEnumItems() do
 grid.StartCorner=corner
 for _,v in {items[1].AbsolutePosition.X,items[1].AbsolutePosition.Y,items[4].AbsolutePosition.X,items[4].AbsolutePosition.Y} do table.insert(result,v) end
end
return table.unpack(result)
'''),[0,0,0,30,90,0,90,30,0,30,0,0,90,30,90,0])

    def test_alignment_positions_whole_grid(self):
        self.assertEqual(self.execute('''
panel.Size=UDim2.fromOffset(200,100);grid.FillDirectionMaxCells=3
grid.HorizontalAlignment=Enum.HorizontalAlignment.Center;grid.VerticalAlignment=Enum.VerticalAlignment.Center
local x,y=items[1].AbsolutePosition.X,items[1].AbsolutePosition.Y
grid.HorizontalAlignment=Enum.HorizontalAlignment.Right;grid.VerticalAlignment=Enum.VerticalAlignment.Bottom
return x,y,items[1].AbsolutePosition.X,items[1].AbsolutePosition.Y,grid.AbsoluteContentSize.X,grid.AbsoluteContentSize.Y
'''),[35,25,70,50,130,50])

    def test_limit_resize_and_one_cell_list(self):
        self.assertEqual(self.execute('''
grid.FillDirectionMaxCells=2
local width,height=grid.AbsoluteContentSize.X,grid.AbsoluteContentSize.Y
grid.FillDirectionMaxCells=1
local one=grid.AbsoluteContentSize.Y
grid.FillDirectionMaxCells=0;panel.Size=UDim2.fromOffset(175,100)
return width,height,one,grid.AbsoluteCellCount.X,grid.AbsoluteCellCount.Y,items[5].AbsolutePosition.Y
'''),[85,80,140,4,2,30])

    def test_sorting_stable_ties_and_reparent(self):
        self.assertEqual(self.execute('''
grid.SortOrder=Enum.SortOrder.Name;items[5].Name="A"
local first=items[5].AbsolutePosition
grid.SortOrder=Enum.SortOrder.LayoutOrder
items[1].Parent=nil;items[1].Parent=panel
return first.X,first.Y,items[1].AbsolutePosition.X,items[1].AbsolutePosition.Y
'''),[0,0,45,30])

    def test_hidden_non_gui_removed_and_empty(self):
        self.assertEqual(self.execute('''
Instance.new("Folder",panel);items[2].Visible=false
local pos=items[4].AbsolutePosition
for _,item in items do item:Destroy() end
return pos.X,pos.Y,grid.AbsoluteContentSize.X,grid.AbsoluteContentSize.Y,
grid.AbsoluteCellCount.X,grid.AbsoluteCellCount.Y,grid.AbsoluteCellSize.X,grid.AbsoluteCellSize.Y
'''),[90,0,0,0,0,0,40,20])

    def test_scale_cell_size_padding_and_container_padding(self):
        self.assertEqual(self.execute('''
panel.Size=UDim2.fromOffset(150,100);Instance.new("UIScale",panel).Scale=2
local p=Instance.new("UIPadding",panel);p.PaddingLeft=UDim.new(0,10);p.PaddingRight=UDim.new(0,10)
grid.CellSize=UDim2.new(.25,0,0,20);grid.CellPadding=UDim2.new(0,5,0,10)
return grid.AbsoluteCellSize.X,grid.AbsoluteCellSize.Y,items[1].AbsolutePosition.X,
items[2].AbsolutePosition.X,items[4].AbsolutePosition.Y,grid.AbsoluteContentSize.X,grid.AbsoluteContentSize.Y
'''),[65,40,20,95,60,215,100])

    def test_child_scale_and_constraints_do_not_change_absolute_cell_size(self):
        self.assertEqual(self.execute('''
Instance.new("UIScale",items[1]).Scale=2
local bound=Instance.new("UISizeConstraint",items[2]);bound.MaxSize=Vector2.new(20,10)
Instance.new("UIAspectRatioConstraint",items[3]).AspectRatio=1
return items[1].AbsoluteSize.X,items[1].AbsoluteSize.Y,items[2].AbsoluteSize.X,items[2].AbsoluteSize.Y,
items[3].AbsoluteSize.X,items[3].AbsoluteSize.Y,grid.AbsoluteCellSize.X,grid.AbsoluteCellSize.Y
'''),[80,40,20,10,20,20,40,20])

    def test_minimum_spans_multiple_cells_and_reserves_occupied_rows(self):
        self.assertEqual(self.execute('''
Instance.new("UISizeConstraint",items[1]).MinSize=Vector2.new(65,50)
return items[1].AbsoluteSize.X,items[1].AbsoluteSize.Y,
items[2].AbsolutePosition.X,items[2].AbsolutePosition.Y,items[3].AbsolutePosition.X,items[3].AbsolutePosition.Y,
items[4].AbsolutePosition.X,items[4].AbsolutePosition.Y,grid.AbsoluteCellCount.X,grid.AbsoluteCellCount.Y,
grid.AbsoluteContentSize.X,grid.AbsoluteContentSize.Y
'''),[65,50,90,0,90,30,0,60,3,3,130,80])

    def test_oversized_span_does_not_make_an_empty_first_row(self):
        self.assertEqual(self.execute('''
Instance.new("UISizeConstraint",items[1]).MinSize=Vector2.new(200,0)
return items[1].AbsolutePosition.Y,items[2].AbsolutePosition.Y,
grid.AbsoluteCellCount.X,grid.AbsoluteCellCount.Y,grid.AbsoluteContentSize.X
'''),[0,30,5,3,220])

    def test_negative_and_zero_stride_are_bounded(self):
        self.assertEqual(self.execute('''
grid.CellPadding=UDim2.fromOffset(-10,0);panel.Size=UDim2.fromOffset(100,100)
local count=grid.AbsoluteCellCount.X;local pos=items[3].AbsolutePosition.X
grid.CellSize=UDim2.fromOffset(0,0);grid.CellPadding=UDim2.fromOffset(0,0)
return count,pos,grid.AbsoluteCellCount.X,grid.AbsoluteCellCount.Y,grid.AbsoluteContentSize.X,grid.AbsoluteContentSize.Y
'''),[3,60,5,1,0,0])

    def test_descendants_use_grid_controlled_size(self):
        self.assertEqual(self.execute('''
items[1].AutomaticSize=Enum.AutomaticSize.XY
local child=Instance.new("Frame",items[1]);child.Size=UDim2.fromScale(1,1)
return child.AbsoluteSize.X,child.AbsoluteSize.Y,items[1].AbsoluteSize.X,items[1].AbsoluteSize.Y
'''),[40,20,40,20])

    def test_clone_preserves_grid_enums_and_geometry(self):
        self.assertEqual(self.execute('''
grid.StartCorner=Enum.StartCorner.BottomRight
local clone=panel:Clone();clone.Parent=panel.Parent
local copied=clone:FindFirstChildOfClass("UIGridLayout")
return copied.StartCorner==Enum.StartCorner.BottomRight,copied.CellSize==grid.CellSize,
clone.Item1.AbsolutePosition.X,clone.Item1.AbsolutePosition.Y
'''),[True,True,90,30])

    def test_cell_defaults_and_validation(self):
        self.assertEqual(self.execute('''
local fresh=Instance.new("UIGridLayout")
local failures=0
for _,v in {-1,1.5,math.huge,"2"} do if not pcall(function()grid.FillDirectionMaxCells=v end) then failures+=1 end end
for _,key in {"AbsoluteCellSize","AbsoluteCellCount","AbsoluteContentSize"} do
 if not pcall(function()grid[key]=Vector2.new(1,2)end)then failures+=1 end
end
if not pcall(function()grid.StartCorner=Enum.FillDirection.Horizontal end)then failures+=1 end
if not pcall(function()grid.CellSize=Vector2.new(1,2)end)then failures+=1 end
return fresh.CellSize.X.Offset,fresh.CellPadding.Y.Offset,fresh.FillDirection==Enum.FillDirection.Horizontal,
fresh.SortOrder==Enum.SortOrder.LayoutOrder,fresh.StartCorner==Enum.StartCorner.TopLeft,failures
'''),[100,5,True,True,True,9])

    def test_computed_grid_events(self):
        self.execute('''
getgenv().counts=0;getgenv().changed=0
grid:GetPropertyChangedSignal("AbsoluteCellCount"):Connect(function()counts+=1 end)
grid.Changed:Connect(function(key)if key=="AbsoluteCellCount" then changed+=1 end end)
panel.Size=UDim2.fromOffset(85,100)
''')
        self.assertEqual(self.execute('return counts,changed,grid.AbsoluteCellCount.X,grid.AbsoluteCellCount.Y'),[1,1,2,3])
        self.execute('panel.Size=UDim2.fromOffset(85,100)')
        self.assertEqual(self.execute('return counts,changed'),[1,1])

    def test_automatic_frame_and_detached_grid(self):
        self.assertEqual(self.execute('''
panel.Size=UDim2.fromOffset(130,0);panel.AutomaticSize=Enum.AutomaticSize.Y
local height=panel.AbsoluteSize.Y
panel.Size=UDim2.fromOffset(85,0);local resized=panel.AbsoluteSize.Y
panel.Parent=nil
return height,resized,grid.AbsoluteContentSize.X,grid.AbsoluteCellSize.X,grid.AbsoluteCellCount.Y
'''),[50,80,0,0,0])

    def test_conflicting_layouts_are_explicit(self):
        self.assertEqual(self.execute('''
Instance.new("UIListLayout",panel)
local ok,err=pcall(function()return items[1].AbsoluteSize end)
return ok,string.find(err,"multiple active GUI components",1,true)~=nil
'''),[False,True])

    def test_apply_layout_and_invalid_receiver(self):
        self.assertEqual(self.execute('''
panel.Size=UDim2.fromOffset(85,100)
local count=select("#",grid:ApplyLayout())
local method=grid.ApplyLayout
local bad=pcall(function()method(panel)end)
local list=Instance.new("UIListLayout")
return count,bad,select("#",list:ApplyLayout()),grid.AbsoluteCellCount.X,grid.AbsoluteCellCount.Y
'''),[0,False,0,2,3])


class GuiGridIntegrationTests(unittest.TestCase):
    def test_received_cell_properties_and_read_only_fields(self):
        snapshot=layout_snapshot()
        for node in snapshot['nodes']:
            if node['id']=='Child':node['properties']['Visible']=True
        snapshot['nodes'].append({'id':'received-grid','name':'Grid','class_name':'UIGridLayout','parent':'Frame',
            'properties':{'CellSize':{'$udim2':[{'$udim':[0,100]},{'$udim':[0,50]}]},'StartCorner':1}})
        host=PersistentLuauHost(snapshot);self.addCleanup(host.close)
        query='local f=game:GetService("Players").LocalPlayer.Gui.Screen.Frame;return f.Child.AbsoluteSize.X,f.Child.AbsoluteSize.Y,f.Grid.AbsoluteCellSize.X,f.Grid.AbsoluteCellCount.X'
        before=host.call({'op':'execute','source':query,'timeout_ms':1000})
        self.assertTrue(before['ok'],before.get('error'));self.assertEqual(before['values'],[100,50,100,1])
        updated=host.call({'op':'update','delta':{'version':1,'delta':True,'actions':[
            {'sequence':100,'kind':'set','id':'received-grid','fields':{
             'CellSize':{'$udim2':[{'$udim':[0,50]},{'$udim':[0,20]}]},
             'AbsoluteCellSize':{'$vector2':[999,999]},'AbsoluteCellCount':{'$vector2':[999,999]}}}]}})
        self.assertTrue(updated['ok'],updated.get('error'))
        after=host.call({'op':'execute','source':query,'timeout_ms':1000})
        self.assertTrue(after['ok'],after.get('error'));self.assertEqual(after['values'],[50,20,50,1])

    def test_thousand_received_cells(self):
        snapshot=layout_snapshot()
        snapshot['nodes'] += [
            {'id':'grid-panel','name':'GridPanel','class_name':'Frame','parent':'Screen',
             'properties':{'Visible':True,'Size':{'$udim2':[{'$udim':[0,100]},{'$udim':[0,200]}]}}},
            {'id':'grid','name':'Grid','class_name':'UIGridLayout','parent':'grid-panel',
             'properties':{'CellSize':{'$udim2':[{'$udim':[0,10]},{'$udim':[0,2]}]},
                           'CellPadding':{'$udim2':[{'$udim':[0,0]},{'$udim':[0,0]}]}}}]
        for i in range(1000):
            snapshot['nodes'].append({'id':f'cell-{i}','name':f'Cell{i}','class_name':'Frame','parent':'grid-panel',
                'properties':{'Visible':True,'LayoutOrder':i}})
        host=PersistentLuauHost(snapshot);self.addCleanup(host.close)
        result=host.call({'op':'execute','timeout_ms':1000,'source':'''
local p=game:GetService("Players").LocalPlayer.Gui.Screen.GridPanel
assert(p.Grid.AbsoluteCellCount==Vector2.new(10,100))
assert(p.Grid.AbsoluteContentSize==Vector2.new(100,200))
assert(p.Cell999.AbsolutePosition==Vector2.new(90,198))
p.Size=UDim2.fromOffset(50,200)
assert(p.Grid.AbsoluteCellCount==Vector2.new(5,200))
assert(p.Cell999.AbsolutePosition==Vector2.new(40,398))
return true
'''})
        self.assertTrue(result['ok'],result.get('error'));self.assertEqual(result.get('task_errors',[]),[])
        self.assertEqual(result['values'],[True])

    def test_grid_demo_in_both_workers(self):
        from test_cframe_transforms import CFrameTransformTests
        demo=Path(__file__).resolve().parents[2]/'runtime/scripts/grid_layout_demo.luau'
        CFrameTransformTests.run_script(self,'local result=(function()\n'+demo.read_text()+'''
end)()
assert(result==Vector2.new(3,3))
assert(game:GetService("Players").LocalPlayer.Gui:FindFirstChild("GridLayoutDemo")==nil)
''',layout_snapshot())

    def test_automatic_scrolling_grid_clamps_after_resize(self):
        host=PersistentLuauHost(layout_snapshot());self.addCleanup(host.close)
        result=host.call({'op':'execute','timeout_ms':1000,'source':SETUP+'''
local scroll=Instance.new("ScrollingFrame",panel.Parent)
scroll.Size=UDim2.fromOffset(130,30);scroll.CanvasSize=UDim2.fromOffset(0,0)
scroll.ScrollBarThickness=0;scroll.AutomaticCanvasSize=Enum.AutomaticSize.Y
grid.Parent=scroll;for _,item in items do item.Parent=scroll end
local initial=scroll.AbsoluteCanvasSize.Y
scroll.CanvasPosition=Vector2.new(0,20)
local moved=items[4].AbsolutePosition.Y
scroll.Size=UDim2.fromOffset(220,30)
return initial,moved,scroll.AbsoluteCanvasSize.Y,scroll.CanvasPosition.Y
'''})
        self.assertTrue(result['ok'],result.get('error'));self.assertEqual(result.get('task_errors',[]),[])
        self.assertEqual(result['values'],[50,10,20,0])

    def test_grid_in_both_workers(self):
        from test_cframe_transforms import CFrameTransformTests
        CFrameTransformTests.run_script(self,SETUP.replace('getgenv().','')+'''
assert(grid.AbsoluteCellSize==Vector2.new(40,20))
assert(grid.AbsoluteCellCount==Vector2.new(3,2))
assert(grid.AbsoluteContentSize==Vector2.new(130,50))
grid.StartCorner=Enum.StartCorner.BottomRight
assert(items[1].AbsolutePosition==Vector2.new(90,30))
''',layout_snapshot())


if __name__=='__main__':unittest.main()
