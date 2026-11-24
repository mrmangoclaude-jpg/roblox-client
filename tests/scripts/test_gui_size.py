"""Size constraint behavior in actual compiled Luau workers."""
import unittest
from persistent_runtime import PersistentLuauHost
from test_display_layout import layout_snapshot


class GuiSizeTests(unittest.TestCase):
    def setUp(self):
        self.host=PersistentLuauHost(layout_snapshot())
        self.addCleanup(self.host.close)
        self.execute('''
getgenv().s=game:GetService("Players").LocalPlayer.Gui.Screen
getgenv().f=s.Frame
getgenv().limit=Instance.new("UISizeConstraint",f)
''')

    def execute(self,source):
        r=self.host.call({'op':'execute','source':source,'timeout_ms':1000})
        self.assertTrue(r['ok'],r.get('error'))
        self.assertEqual(r.get('task_errors',[]),[])
        return r['values']

    def update(self,actions,**fields):
        r=self.host.call({'op':'update','timeout_ms':100,'delta':{
            'version':1,'delta':True,'actions':actions,**fields}})
        self.assertTrue(r['ok'],r.get('error'))

    def test_default_unbounded_vector_and_independent_axes(self):
        self.assertEqual(self.execute('''
local defaults=limit.MinSize==Vector2.zero and limit.MaxSize.X==math.huge and limit.MaxSize.Y==math.huge
limit.MinSize=Vector2.new(100,400);limit.MaxSize=Vector2.new(300,450)
return defaults,f.AbsoluteSize.X,f.AbsoluteSize.Y,f.AbsolutePosition.X,f.AbsolutePosition.Y,
 f.Child.AbsoluteSize.X,f.Child.AbsoluteSize.Y
'''),[True,300,400,340,180,150,200])

    def test_infinity_is_preserved_in_clones_and_attributes(self):
        self.assertEqual(self.execute('''
limit.MaxSize=Vector2.new(math.huge,200)
limit:SetAttribute("Bound",Vector2.new(math.huge,200))
local clone=limit:Clone()
local bound=clone:GetAttribute("Bound")
return f.AbsoluteSize.X,f.AbsoluteSize.Y,clone.MaxSize.X==math.huge,
 clone.MaxSize.Y,bound.X==math.huge,bound.Y,typeof(clone.MaxSize)
'''),[500,200,True,200,True,200,'Vector2'])

    def test_minimum_maximum_order_validation_is_atomic(self):
        self.assertEqual(self.execute('''
limit.MinSize=Vector2.new(100,100);limit.MaxSize=Vector2.new(300,300)
local bad=0
for _,v in ipairs({Vector2.new(-1,0),Vector2.new(400,100),Vector2.new(math.huge,100),Vector2.zero.Unit})do
 if not pcall(function()limit.MinSize=v end)then bad+=1 end
end
for _,v in ipairs({Vector2.new(99,300),Vector2.new(-math.huge,300),Vector2.zero.Unit,"bad"})do
 if not pcall(function()limit.MaxSize=v end)then bad+=1 end
end
return bad,limit.MinSize.X,limit.MaxSize.X,f.AbsoluteSize.X,f.AbsoluteSize.Y
'''),[8,100,300,300,300])

    def test_nested_scale_and_zero_scale(self):
        self.assertEqual(self.execute('''
limit.MaxSize=Vector2.new(300,200)
local scale=Instance.new("UIScale",f);scale.Scale=2
local child=f.Child
local childLimit=Instance.new("UISizeConstraint",child)
childLimit.MaxSize=Vector2.new(100,80)
Instance.new("UIScale",child).Scale=.5
local w,h,x,y=f.AbsoluteSize.X,f.AbsoluteSize.Y,child.AbsoluteSize.X,child.AbsoluteSize.Y
scale.Scale=0
return w,h,x,y,f.AbsoluteSize.X,f.AbsoluteSize.Y,child.AbsoluteSize.X,child.AbsoluteSize.Y
'''),[600,400,100,80,0,0,0,0])

    def test_same_value_no_duplicate_callbacks_and_destroy(self):
        self.execute('''
getgenv().calls=0
f:GetPropertyChangedSignal("AbsoluteSize"):Connect(function()calls+=1 end)
limit.MaxSize=Vector2.new(300,200)
''')
        self.assertEqual(self.execute('return calls'),[1])
        self.execute('limit.MaxSize=Vector2.new(300,200)')
        self.assertEqual(self.execute('return calls'),[1])
        self.execute('limit:Destroy()')
        self.assertEqual(self.execute('return calls,f.AbsoluteSize.X,f.AbsoluteSize.Y'),[2,500,360])

    def test_resize_honors_limits_without_changing_authored_size(self):
        self.execute('limit.MinSize=Vector2.new(100,100);limit.MaxSize=Vector2.new(300,200)')
        self.update([],display={'size':[400,300]})
        self.assertEqual(self.execute('return f.AbsoluteSize.X,f.AbsoluteSize.Y,f.Size.X.Scale,f.Size.X.Offset'),[210,130,.5,10])
        self.update([],display={'size':[100,100]})
        self.assertEqual(self.execute('return f.AbsoluteSize.X,f.AbsoluteSize.Y'),[100,100])

    def test_reparent_and_detach_change_geometry(self):
        self.execute('limit.MaxSize=Vector2.new(300,200)')
        self.assertEqual(self.execute('''
limit.Parent=f.Child
local w,h=f.AbsoluteSize.X,f.Child.AbsoluteSize.X
s.Parent=nil
return w,h,f.AbsoluteSize.X,f.Child.AbsoluteSize.X
'''),[500,250,0,0])

    def test_replicated_bounds_and_updates(self):
        self.execute('limit:Destroy()')
        self.update([{'sequence':50,'kind':'create','node':{
            'id':'bounds','name':'Bounds','class_name':'UISizeConstraint','parent':'Frame',
            'properties':{'MinSize':{'$vector2':[0,0]},'MaxSize':{'$vector2':[300,200]}}}}])
        self.assertEqual(self.execute('return f.AbsoluteSize.X,f.AbsoluteSize.Y'),[300,200])
        self.update([{'sequence':51,'kind':'set','id':'bounds','fields':{'MaxSize':{'$vector2':[250,150]}}}])
        self.assertEqual(self.execute('return f.AbsoluteSize.X,f.AbsoluteSize.Y'),[250,150])

    def test_duplicate_and_mixed_constraints_are_explicit(self):
        self.assertEqual(self.execute('''
local duplicate=Instance.new("UISizeConstraint",f)
local ok,err=pcall(function()return f.AbsoluteSize end)
duplicate:Destroy()
Instance.new("UIAspectRatioConstraint",f)
local mixed,msg=pcall(function()return f.AbsoluteSize end)
return ok,string.find(err,"multiple active GUI components",1,true)~=nil,
 mixed,string.find(msg,"combined size and aspect",1,true)~=nil
'''),[False,True,False,True])


class GuiSizeOneShotTests(unittest.TestCase):
    def test_size_constraint_and_unbounded_clone_in_both_workers(self):
        from test_cframe_transforms import CFrameTransformTests
        CFrameTransformTests.run_script(self,'''
local f=game:GetService("Players").LocalPlayer.Gui.Screen.Frame
local c=Instance.new("UISizeConstraint",f)
assert(c.MinSize==Vector2.zero and c.MaxSize.X==math.huge)
c.MinSize=Vector2.new(0,400);c.MaxSize=Vector2.new(300,math.huge)
assert(f.AbsoluteSize==Vector2.new(300,400))
local clone=c:Clone()
assert(clone.MaxSize.X==300 and clone.MaxSize.Y==math.huge)
assert(clone.MinSize==Vector2.new(0,400))
''',layout_snapshot())


if __name__=='__main__':unittest.main()
