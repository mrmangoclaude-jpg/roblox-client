"""Aspect layout through the persistent Luau worker.

Parent-scaling expectations follow the documented parent limit and dominant
axis contract. They are offline regressions, not a captured Studio reference.
"""
import unittest
from persistent_runtime import PersistentLuauHost
from test_display_layout import layout_snapshot


class GuiAspectTests(unittest.TestCase):
    def setUp(self):
        snapshot = layout_snapshot()
        for node in snapshot['nodes']:
            if node['id'] in ('Frame', 'Child'):
                node['properties']['Archivable'] = True
        self.host = PersistentLuauHost(snapshot)
        self.addCleanup(self.host.close)
        self.run_luau('''
getgenv().s=game:GetService("Players").LocalPlayer.Gui.Screen
getgenv().f=s.Frame
getgenv().a=Instance.new("UIAspectRatioConstraint",f)
''')

    def run_luau(self, source):
        result = self.host.call({'op': 'execute', 'source': source, 'timeout_ms': 1000})
        self.assertTrue(result['ok'], result.get('error'))
        self.assertEqual(result.get('task_errors', []), [])
        return result['values']

    def test_default_square_anchor_and_descendants(self):
        self.assertEqual(self.run_luau('''
return f.AbsoluteSize.X,f.AbsoluteSize.Y,f.AbsolutePosition.X,f.AbsolutePosition.Y,
 f.Child.AbsoluteSize.X,f.Child.AbsoluteSize.Y,a.AspectRatio,
 a.AspectType==Enum.AspectType.FitWithinMaxSize,a.DominantAxis==Enum.DominantAxis.Width
'''), [360, 360, 310, 200, 180, 180, 1, True, True])

    def test_wide_tall_and_zero_boxes(self):
        self.assertEqual(self.run_luau('''
a.AspectRatio=2
local w,h=f.AbsoluteSize.X,f.AbsoluteSize.Y
a.AspectRatio=.5
local x,y=f.AbsoluteSize.X,f.AbsoluteSize.Y
f.Size=UDim2.fromOffset(100,0)
return w,h,x,y,f.AbsoluteSize.X,f.AbsoluteSize.Y
'''), [500, 250, 180, 360, 0, 0])

    def test_scale_clone_and_canonical_enum_identity(self):
        self.assertEqual(self.run_luau('''
a.AspectRatio=2;a.DominantAxis=Enum.DominantAxis.Height
Instance.new("UIScale",f).Scale=2
local clone=f:Clone();clone.Parent=s
local c=clone:FindFirstChildOfClass("UIAspectRatioConstraint")
local keys={[a.DominantAxis]=true}
return f.AbsoluteSize.X,f.AbsoluteSize.Y,clone.AbsoluteSize.X,clone.AbsoluteSize.Y,
 c.AspectRatio,keys[c.DominantAxis],#Enum.AspectType:GetEnumItems()
'''), [1000, 500, 1000, 500, 2, True, 2])

    def test_invalid_assignments_preserve_existing_value(self):
        self.assertEqual(self.run_luau('''
local failures=0
for _,v in ipairs({0,-1,math.huge,0/0,"two"})do
 if not pcall(function()a.AspectRatio=v end)then failures+=1 end
end
local wrong=pcall(function()a.AspectType=Enum.DominantAxis.Width end)
return failures,wrong,a.AspectRatio,f.AbsoluteSize.X
'''), [5, False, 1, 360])

    def test_changes_destroy_and_resize_notify_computed_size(self):
        self.run_luau('''
getgenv().calls=0
f:GetPropertyChangedSignal("AbsoluteSize"):Connect(function()calls+=1 end)
a.AspectRatio=2
''')
        self.assertEqual(self.run_luau('return calls'), [1])
        self.run_luau('a.AspectRatio=2')
        self.assertEqual(self.run_luau('return calls'), [1])
        result = self.host.call({'op': 'update', 'timeout_ms': 100, 'delta': {
            'version': 1, 'delta': True, 'actions': [], 'display': {'size': [800, 600]}}})
        self.assertTrue(result['ok'], result.get('error'))
        self.assertEqual(self.run_luau('return calls,f.AbsoluteSize.X,f.AbsoluteSize.Y'), [2,410,205])
        self.run_luau('a:Destroy()')
        self.assertEqual(self.run_luau('return calls,f.AbsoluteSize.X,f.AbsoluteSize.Y'), [3,410,280])

    def test_replicated_constraint_and_parent_scaling(self):
        self.run_luau('a:Destroy()')
        result = self.host.call({'op': 'update', 'timeout_ms': 100, 'delta': {
            'version': 1, 'delta': True, 'actions': [{'sequence': 50, 'kind': 'create', 'node': {
                'id': 'aspect', 'name': 'Aspect', 'class_name': 'UIAspectRatioConstraint',
                'parent': 'Frame', 'properties': {'AspectRatio': 2, 'AspectType': 0, 'DominantAxis': 1}}}]}})
        self.assertTrue(result['ok'], result.get('error'))
        self.assertEqual(self.run_luau('''
local aspect=f.Aspect
local width,height=f.AbsoluteSize.X,f.AbsoluteSize.Y
aspect.AspectType=Enum.AspectType.ScaleWithParentSize
return width,height,aspect.DominantAxis==Enum.DominantAxis.Height,
 f.AbsoluteSize.X,f.AbsoluteSize.Y
'''), [500,250,True,720,360])

    def test_parent_scaling_uses_dominant_dimension_not_other_authored_dimension(self):
        self.assertEqual(self.run_luau('''
a.AspectType=Enum.AspectType.ScaleWithParentSize;a.AspectRatio=2
f.Size=UDim2.fromOffset(300,0)
local width,height=f.AbsoluteSize.X,f.AbsoluteSize.Y
a.DominantAxis=Enum.DominantAxis.Height
f.Size=UDim2.fromOffset(0,200)
return width,height,f.AbsoluteSize.X,f.AbsoluteSize.Y,
 f.Child.AbsoluteSize.X,f.Child.AbsoluteSize.Y
'''), [300,150,400,200,200,100])

    def test_parent_scaling_limits_both_axes_and_preserves_anchor(self):
        self.assertEqual(self.run_luau('''
a.AspectType=Enum.AspectType.ScaleWithParentSize;a.AspectRatio=2
f.Size=UDim2.fromOffset(2000,2000)
local wide=f.AbsoluteSize
local p=f.AbsolutePosition
a.AspectRatio=.5
local tall=f.AbsoluteSize
a.DominantAxis=Enum.DominantAxis.Height
return wide.X,wide.Y,p.X,p.Y,tall.X,tall.Y,
 f.AbsoluteSize.X,f.AbsoluteSize.Y
'''), [980,490,0,135,380,760,380,760])

    def test_parent_padding_and_cumulative_ui_scale(self):
        self.assertEqual(self.run_luau('''
a:Destroy()
f.Size=UDim2.fromOffset(400,300)
Instance.new("UIScale",f).Scale=2
local padding=Instance.new("UIPadding",f)
padding.PaddingLeft=UDim.new(0,10);padding.PaddingRight=UDim.new(0,30)
padding.PaddingTop=UDim.new(0,20);padding.PaddingBottom=UDim.new(0,40)
local child=f.Child
child.Size=UDim2.fromOffset(2000,0)
local aspect=Instance.new("UIAspectRatioConstraint",child)
aspect.AspectType=Enum.AspectType.ScaleWithParentSize;aspect.AspectRatio=2
local before=child.AbsoluteSize
local scale=Instance.new("UIScale",child);scale.Scale=.5
local after=child.AbsoluteSize
scale.Scale=0
return before.X,before.Y,after.X,after.Y,child.AbsoluteSize.X,child.AbsoluteSize.Y
'''), [720,360,360,180,0,0])

    def test_parent_resize_and_axis_changes_notify_dependents(self):
        self.run_luau('''
a.AspectType=Enum.AspectType.ScaleWithParentSize;a.AspectRatio=2
getgenv().calls=0;getgenv().childCalls=0
f:GetPropertyChangedSignal("AbsoluteSize"):Connect(function()calls+=1 end)
f.Child:GetPropertyChangedSignal("AbsoluteSize"):Connect(function()childCalls+=1 end)
a.DominantAxis=Enum.DominantAxis.Height
''')
        self.assertEqual(self.run_luau('return calls,childCalls,f.AbsoluteSize.X'), [1,1,720])
        result=self.host.call({'op':'update','timeout_ms':100,'delta':{
            'version':1,'delta':True,'actions':[], 'display':{'size':[800,600]}}})
        self.assertTrue(result['ok'], result.get('error'))
        self.assertEqual(self.run_luau('return calls,childCalls,f.AbsoluteSize.X,f.AbsoluteSize.Y'),
                         [2,2,560,280])

    def test_mode_switch_zero_parent_and_combined_constraint_boundary(self):
        self.assertEqual(self.run_luau('''
a.AspectType=Enum.AspectType.ScaleWithParentSize;a.AspectRatio=2
a.DominantAxis=Enum.DominantAxis.Height
local width=f.AbsoluteSize.X
a.AspectType=Enum.AspectType.FitWithinMaxSize
local fit=f.AbsoluteSize.X
local bound=Instance.new("UISizeConstraint",f)
local ok,err=pcall(function()return f.AbsoluteSize end)
bound:Destroy();a:Destroy()
f.Size=UDim2.fromOffset(0,0)
local child=f.Child
local aspect=Instance.new("UIAspectRatioConstraint",child)
aspect.AspectType=Enum.AspectType.ScaleWithParentSize
child.Size=UDim2.fromOffset(100,100)
return width,fit,ok,string.find(err,"combined size and aspect",1,true)~=nil,
 child.AbsoluteSize.X,child.AbsoluteSize.Y
'''), [720,500,False,True,0,0])

    def test_duplicate_constraints_are_explicit_and_detached_geometry_is_zero(self):
        self.assertEqual(self.run_luau('''
Instance.new("UIAspectRatioConstraint",f)
local ok,err=pcall(function()return f.AbsoluteSize end)
s.Parent=nil
return ok,string.find(err,"multiple active GUI components",1,true)~=nil,
 f.AbsoluteSize.X,f.AbsoluteSize.Y
'''), [False,True,0,0])


class GuiAspectOneShotTests(unittest.TestCase):
    def test_parent_scaling_in_both_compiled_workers(self):
        from test_cframe_transforms import CFrameTransformTests
        CFrameTransformTests.run_script(self, '''
local screen=game:GetService("Players").LocalPlayer.Gui.Screen
local frame=screen.Frame
local aspect=Instance.new("UIAspectRatioConstraint",frame)
aspect.AspectType=Enum.AspectType.ScaleWithParentSize
aspect.DominantAxis=Enum.DominantAxis.Height
aspect.AspectRatio=2
assert(frame.AbsoluteSize==Vector2.new(720,360))
assert(frame.AbsolutePosition==Vector2.new(130,200))
assert(frame.Child.AbsoluteSize==Vector2.new(360,180))
frame.Size=UDim2.fromOffset(0,2000)
assert(frame.AbsoluteSize==Vector2.new(980,490))
aspect.DominantAxis=Enum.DominantAxis.Width
frame.Size=UDim2.fromOffset(300,0)
assert(frame.AbsoluteSize==Vector2.new(300,150))
''', layout_snapshot())

    def test_fit_and_enum_clone_in_both_compiled_workers(self):
        from test_cframe_transforms import CFrameTransformTests
        CFrameTransformTests.run_script(self, '''
local screen=game:GetService("Players").LocalPlayer.Gui.Screen
local frame=screen.Frame
local aspect=Instance.new("UIAspectRatioConstraint",frame)
aspect.AspectRatio=2
assert(frame.AbsoluteSize==Vector2.new(500,250))
assert(frame.AbsolutePosition==Vector2.new(240,255))
assert(frame.Child.AbsoluteSize==Vector2.new(250,125))
aspect.DominantAxis=Enum.DominantAxis.Height
local copy=aspect:Clone()
assert(copy.AspectType==Enum.AspectType.FitWithinMaxSize)
assert(copy.DominantAxis==Enum.DominantAxis.Height)
assert(copy.AspectRatio==2)
''', layout_snapshot())


if __name__ == '__main__': unittest.main()
