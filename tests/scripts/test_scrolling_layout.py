"""Authored scrolling geometry in the real VM; no live input or Studio capture."""
import time
import unittest
from persistent_runtime import PersistentLuauHost
from test_display_layout import layout_snapshot

SETUP='''
local screen=game:GetService("Players").LocalPlayer.Gui.Screen
scroll=Instance.new("ScrollingFrame",screen)
scroll.Size=UDim2.fromOffset(300,200);scroll.Position=UDim2.fromOffset(100,50)
scroll.CanvasSize=UDim2.fromOffset(600,500);scroll.ScrollBarThickness=10
child=Instance.new("Frame",scroll)
child.Size=UDim2.fromScale(.5,.5);child.Position=UDim2.fromScale(.25,.2)
'''

class ScrollingLayoutTests(unittest.TestCase):
    def setUp(self):
        self.host=PersistentLuauHost(layout_snapshot())
        self.addCleanup(self.host.close)
        self.execute(SETUP)

    def execute(self,source):
        result=self.host.call({'op':'execute','source':source,'timeout_ms':1000})
        self.assertTrue(result['ok'],result.get('error'))
        self.assertEqual(result.get('task_errors',[]),[])
        if result.get('state')=='running':
            job=result['job_id'];deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                result=self.host.call({'op':'poll','timeout_ms':100})
                self.assertEqual(result.get('task_errors',[]),[])
                done=next((x for x in result.get('completed_jobs',[]) if x['job_id']==job),None)
                if done:
                    self.assertTrue(done['ok'],done.get('error'))
                    return done['values']
                time.sleep(.005)
            self.fail('scrolling script did not finish')
        return result['values']

    def test_canvas_window_and_child_coordinates(self):
        self.assertEqual(self.execute('''
return scroll.AbsoluteSize.X,scroll.AbsoluteSize.Y,
 scroll.AbsoluteCanvasSize.X,scroll.AbsoluteCanvasSize.Y,
 scroll.AbsoluteWindowSize.X,scroll.AbsoluteWindowSize.Y,
 child.AbsoluteSize.X,child.AbsoluteSize.Y,child.AbsolutePosition.X,child.AbsolutePosition.Y
'''),[300,200,600,500,290,190,300,250,250,150])

    def test_scroll_moves_descendants_without_resizing_them(self):
        self.assertEqual(self.execute('''
local nested=Instance.new("Frame",child);nested.Position=UDim2.fromOffset(3,4)
nested.Size=UDim2.fromOffset(10,20)
scroll.CanvasPosition=Vector2.new(50,75)
return child.AbsoluteSize.X,child.AbsoluteSize.Y,child.AbsolutePosition.X,child.AbsolutePosition.Y,
 nested.AbsolutePosition.X,nested.AbsolutePosition.Y,scroll.CanvasPosition.X,scroll.CanvasPosition.Y
'''),[300,250,200,75,203,79,50,75])

    def test_nonsequential_direction_enum_values_and_axis_limits(self):
        self.assertEqual(self.execute('''
scroll.ScrollingDirection=Enum.ScrollingDirection.Y;scroll.CanvasPosition=Vector2.new(50,75)
local pos=scroll.CanvasPosition;local window=scroll.AbsoluteWindowSize
scroll.ScrollingDirection=Enum.ScrollingDirection.X
scroll.CanvasPosition=Vector2.new(50,75)
return Enum.ScrollingDirection.X.Value,Enum.ScrollingDirection.Y.Value,Enum.ScrollingDirection.XY.Value,
 pos.X,pos.Y,window.X,window.Y,scroll.CanvasPosition.X,scroll.CanvasPosition.Y,
 scroll.AbsoluteWindowSize.X,scroll.AbsoluteWindowSize.Y
'''),[1,2,4,0,75,290,200,50,0,300,190])

    def test_scroll_offsets_clamp_at_bounds(self):
        self.assertEqual(self.execute('''
scroll.CanvasPosition=Vector2.new(-20,10000)
return scroll.CanvasPosition.X,scroll.CanvasPosition.Y,child.AbsolutePosition.Y
'''),[0,310,-160])

    def test_clamped_write_does_not_resurface_when_canvas_grows(self):
        self.assertEqual(self.execute('''
scroll.CanvasPosition=Vector2.new(0,10000)
scroll.CanvasSize=UDim2.fromOffset(600,1000)
return scroll.CanvasPosition.Y
'''),[310])

    def test_resize_clamps_retained_position_before_later_growth(self):
        self.execute('scroll.CanvasPosition=Vector2.new(0,250)')
        self.execute('scroll.CanvasSize=UDim2.fromOffset(100,100)')
        self.execute('scroll.CanvasSize=UDim2.fromOffset(600,1000)')
        self.assertEqual(self.execute('return scroll.CanvasPosition.Y'),[0])

    def test_smaller_canvas_has_no_scroll_and_children_still_have_window_space(self):
        self.assertEqual(self.execute('''
scroll.CanvasSize=UDim2.fromOffset(100,100);scroll.CanvasPosition=Vector2.new(50,50)
return scroll.CanvasPosition.X,scroll.CanvasPosition.Y,
 scroll.AbsoluteWindowSize.X,scroll.AbsoluteWindowSize.Y,child.AbsoluteSize.X,child.AbsoluteSize.Y
'''),[0,0,300,200,150,100])

    def test_insets_reduce_canvas_and_left_scrollbar_shifts_its_origin(self):
        self.assertEqual(self.execute('''
scroll.VerticalScrollBarInset=Enum.ScrollBarInset.ScrollBar
scroll.HorizontalScrollBarInset=Enum.ScrollBarInset.Always
scroll.VerticalScrollBarPosition=Enum.VerticalScrollBarPosition.Left
child.Size=UDim2.fromScale(1,1);child.Position=UDim2.fromOffset(0,0)
return scroll.AbsoluteCanvasSize.X,scroll.AbsoluteCanvasSize.Y,child.AbsoluteSize.X,
 child.AbsoluteSize.Y,child.AbsolutePosition.X,child.AbsolutePosition.Y
'''),[590,490,590,490,110,50])

    def test_always_inset_and_conditional_inset_differ_without_scrollbars(self):
        self.assertEqual(self.execute('''
scroll.CanvasSize=UDim2.fromScale(0,0)
scroll.VerticalScrollBarInset=Enum.ScrollBarInset.ScrollBar
child.Size=UDim2.fromScale(1,1)
local width=child.AbsoluteSize.X
scroll.VerticalScrollBarInset=Enum.ScrollBarInset.Always
return width,child.AbsoluteSize.X,scroll.AbsoluteWindowSize.X
'''),[300,290,300])

    def test_scrollbar_visibility_resolves_perpendicular_overflow(self):
        self.assertEqual(self.execute('''
scroll.CanvasSize=UDim2.fromOffset(295,500)
local both=scroll.AbsoluteWindowSize
scroll.VerticalScrollBarInset=Enum.ScrollBarInset.ScrollBar
return both.X,both.Y,scroll.AbsoluteWindowSize.X,scroll.AbsoluteWindowSize.Y
'''),[290,190,290,200])

    def test_scrolling_container_occupies_its_outer_size_in_an_ancestor_list(self):
        self.assertEqual(self.execute('''
local parent=Instance.new("Frame",scroll.Parent);parent.Size=UDim2.fromOffset(400,400)
local list=Instance.new("UIListLayout",parent);list.SortOrder=Enum.SortOrder.LayoutOrder
scroll.Parent=parent
local footer=Instance.new("Frame",parent);footer.Size=UDim2.fromOffset(100,20)
scroll.CanvasPosition=Vector2.new(0,75)
return footer.AbsolutePosition.Y,list.AbsoluteContentSize.X,list.AbsoluteContentSize.Y,
 child.AbsolutePosition.Y
'''),[200,300,220,25])

    def test_scale_multiplies_canvas_gutters_and_pixel_scroll_offsets_once(self):
        self.assertEqual(self.execute('''
Instance.new("UIScale",scroll).Scale=2
scroll.CanvasPosition=Vector2.new(50,75)
return scroll.AbsoluteCanvasSize.X,scroll.AbsoluteCanvasSize.Y,
 scroll.AbsoluteWindowSize.X,scroll.AbsoluteWindowSize.Y,
 child.AbsolutePosition.X,child.AbsolutePosition.Y,scroll.CanvasPosition.X,scroll.CanvasPosition.Y
'''),[1200,1000,580,380,300,100,50,75])

    def test_zero_scale_and_detached_scroll_geometry(self):
        self.assertEqual(self.execute('''
Instance.new("UIScale",scroll).Scale=0
scroll.CanvasPosition=Vector2.new(100,100)
local a,b=scroll.AbsoluteCanvasSize,scroll.AbsoluteWindowSize
scroll.Parent=nil
return a.X,a.Y,b.X,b.Y,scroll.CanvasPosition.X,scroll.CanvasPosition.Y,
 child.AbsoluteSize.X,child.AbsoluteSize.Y
'''),[0]*8)

    def test_list_size_is_independent_of_scroll_offset(self):
        self.assertEqual(self.execute('''
child.Size=UDim2.fromOffset(100,40)
local second=Instance.new("Frame",scroll);second.Size=UDim2.fromOffset(100,40)
local layout=Instance.new("UIListLayout",scroll);layout.SortOrder=Enum.SortOrder.LayoutOrder
layout.Padding=UDim.new(0,5)
local size=layout.AbsoluteContentSize
scroll.CanvasPosition=Vector2.new(0,30)
return size.X,size.Y,layout.AbsoluteContentSize.X,layout.AbsoluteContentSize.Y,
 child.AbsolutePosition.Y,second.AbsolutePosition.Y
'''),[100,85,100,85,20,65])

    def test_list_content_size_callback_can_drive_canvas_size(self):
        self.execute('''
child.Size=UDim2.fromOffset(100,40)
list=Instance.new("UIListLayout",scroll);list.SortOrder=Enum.SortOrder.LayoutOrder
calls=0
list:GetPropertyChangedSignal("AbsoluteContentSize"):Connect(function()
 calls+=1;scroll.CanvasSize=UDim2.fromOffset(0,list.AbsoluteContentSize.Y)
end)
child.Size=UDim2.fromOffset(100,400)
''')
        self.assertEqual(self.execute('return calls,scroll.AbsoluteCanvasSize.Y,list.AbsoluteContentSize.Y'),[1,400,400])
        self.assertEqual(self.execute('return calls'),[1])

    def test_clone_preserves_scroll_and_enum_identity(self):
        self.assertEqual(self.execute('''
scroll.CanvasPosition=Vector2.new(50,75)
scroll.ScrollingDirection=Enum.ScrollingDirection.XY
local copy=scroll:Clone();copy.Parent=scroll.Parent
local same=copy.ScrollingDirection==Enum.ScrollingDirection.XY
return same,copy.CanvasPosition.X,copy.CanvasPosition.Y,
 copy.Frame.AbsolutePosition.X,copy.Frame.AbsolutePosition.Y
'''),[True,50,75,200,75])

    def test_received_canvas_updates_recompute_and_do_not_overwrite_output_geometry(self):
        self.execute('scroll:Destroy()')
        result=self.host.call({'op':'update','timeout_ms':100,'delta':{
            'version':1,'delta':True,'actions':[
                {'sequence':101,'kind':'create','node':{'id':'scroll','name':'Scroll',
                 'class_name':'ScrollingFrame','parent':'Screen','properties':{
                 'Size':{'$udim2':[{'$udim':[0,300]},{'$udim':[0,200]}]},
                 'CanvasSize':{'$udim2':[{'$udim':[0,600]},{'$udim':[0,500]}]},
                 'CanvasPosition':{'$vector2':[40,50]},'ScrollingDirection':4,'ScrollBarThickness':10}}},
                {'sequence':102,'kind':'set','id':'scroll','fields':{
                 'AbsoluteCanvasSize':{'$vector2':[9999,9999]},'AbsoluteWindowSize':{'$vector2':[9999,9999]}}}]}})
        self.assertTrue(result['ok'],result.get('error'))
        self.assertEqual(self.execute('''
local s=game:GetService("Players").LocalPlayer.Gui.Screen.Scroll
return s.AbsoluteCanvasSize.X,s.AbsoluteWindowSize.X,s.CanvasPosition.X,s.CanvasPosition.Y,
 s.ScrollingDirection==Enum.ScrollingDirection.XY
'''),[600,290,40,50,True])

    def test_zero_thickness_and_disabled_scrolling(self):
        self.assertEqual(self.execute('''
scroll.ScrollBarThickness=0;scroll.CanvasPosition=Vector2.new(50,75)
local window=scroll.AbsoluteWindowSize
local position=scroll.CanvasPosition
scroll.ScrollingEnabled=false
return window.X,window.Y,position.X,position.Y,
 scroll.CanvasPosition.X,scroll.CanvasPosition.Y,child.AbsolutePosition.X,child.AbsolutePosition.Y
'''),[300,200,50,75,0,0,250,150])

    def test_nested_scrollers_use_their_own_canvas(self):
        self.assertEqual(self.execute('''
child:Destroy()
local inner=Instance.new("ScrollingFrame",scroll)
inner.Size=UDim2.fromOffset(100,80);inner.Position=UDim2.fromOffset(20,40)
inner.CanvasSize=UDim2.fromOffset(200,300);inner.ScrollBarThickness=0
local leaf=Instance.new("Frame",inner);leaf.Size=UDim2.fromScale(.5,.5)
leaf.Position=UDim2.fromOffset(10,20)
scroll.CanvasPosition=Vector2.new(0,30);inner.CanvasPosition=Vector2.new(5,15)
return leaf.AbsolutePosition.X,leaf.AbsolutePosition.Y,leaf.AbsoluteSize.X,leaf.AbsoluteSize.Y
'''),[125,65,100,150])

    def test_scroll_signals_track_effective_position_once(self):
        self.execute('''
positions=0;changed=0;canvas=0;descendants=0
scroll:GetPropertyChangedSignal("CanvasPosition"):Connect(function()positions+=1 end)
scroll.Changed:Connect(function(k)if k=="CanvasPosition"then changed+=1 end end)
scroll:GetPropertyChangedSignal("AbsoluteCanvasSize"):Connect(function()canvas+=1 end)
child:GetPropertyChangedSignal("AbsolutePosition"):Connect(function()descendants+=1 end)
scroll.CanvasPosition=Vector2.new(0,50)
''')
        self.assertEqual(self.execute('return positions,changed,canvas,descendants'),[1,1,0,1])
        self.execute('scroll.CanvasPosition=Vector2.new(0,50)')
        self.assertEqual(self.execute('return positions,changed,canvas,descendants'),[1,1,0,1])
        self.execute('scroll.CanvasSize=UDim2.fromOffset(100,100)')
        self.assertEqual(self.execute('return positions,changed,canvas,descendants'),[2,2,1,2])

    def test_tween_can_target_canvas_position_and_complete(self):
        self.assertEqual(self.execute('''
local tween=game:GetService("TweenService"):Create(scroll,TweenInfo.new(.02),{CanvasPosition=Vector2.new(0,100)})
tween:Play();local state=tween.Completed:Wait()
return state==Enum.PlaybackState.Completed,scroll.CanvasPosition.Y,child.AbsolutePosition.Y
'''),[True,100,50])

    def test_invalid_assignments_and_computed_geometry_are_protected(self):
        self.assertEqual(self.execute('''
local wrong=pcall(function()scroll.CanvasPosition=Vector3.zero end)
local finite=pcall(function()scroll.CanvasPosition=Vector2.new(math.huge,0)end)
local number=pcall(function()scroll.ScrollBarThickness=-1 end)
local enum=pcall(function()scroll.ScrollingDirection=Enum.Axis.X end)
local read=pcall(function()scroll.AbsoluteCanvasSize=Vector2.zero end)
return wrong,finite,number,enum,read,scroll.CanvasPosition.X,scroll.ScrollBarThickness
'''),[False,False,False,False,False,0,10])

    def test_automatic_canvas_keeps_authored_size_as_a_minimum(self):
        self.assertEqual(self.execute('''
scroll.AutomaticCanvasSize=Enum.AutomaticSize.Y
return scroll.AbsoluteCanvasSize.Y,scroll.CanvasSize.Y.Offset
'''),[500,500])


class ScrollingOneShotTests(unittest.TestCase):
    def test_unobserved_snapshot_scroller_retires_overscroll_on_resize(self):
        snapshot=layout_snapshot()
        snapshot['nodes'].append({'id':'scroll','name':'Scroll','class_name':'ScrollingFrame',
            'parent':'Screen','properties':{
            'Size':{'$udim2':[{'$udim':[0,300]},{'$udim':[0,200]}]},
            'CanvasSize':{'$udim2':[{'$udim':[0,600]},{'$udim':[0,500]}]},
            'CanvasPosition':{'$vector2':[0,250]}}})
        host=PersistentLuauHost(snapshot)
        self.addCleanup(host.close)
        for seq,height in [(101,100),(102,500)]:
            result=host.call({'op':'update','timeout_ms':100,'delta':{
                'version':1,'delta':True,'actions':[{'sequence':seq,'kind':'set','id':'scroll',
                'fields':{'CanvasSize':{'$udim2':[{'$udim':[0,600]},{'$udim':[0,height]}]}}}]}})
            self.assertTrue(result['ok'],result.get('error'))
        result=host.call({'op':'execute','timeout_ms':1000,'source':
            'return game:GetService("Players").LocalPlayer.Gui.Screen.Scroll.CanvasPosition.Y'})
        self.assertTrue(result['ok'],result.get('error'))
        self.assertEqual(result['values'],[0])

    def test_authored_scroll_in_both_workers(self):
        from test_cframe_transforms import CFrameTransformTests
        CFrameTransformTests.run_script(self,SETUP+'''
scroll.CanvasPosition=Vector2.new(50,75)
assert(scroll.AbsoluteWindowSize==Vector2.new(290,190))
assert(child.AbsolutePosition==Vector2.new(200,75))
assert(scroll.CanvasPosition==Vector2.new(50,75))
''',layout_snapshot())

if __name__=='__main__':unittest.main()
