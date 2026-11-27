"""Documented BrickColor behavior through both real native workers."""
import copy
import json
import random
import subprocess
import tempfile
from pathlib import Path
import unittest

import test_motion_math as motion

ROOT=Path(__file__).resolve().parents[2]
REFERENCE=json.loads((ROOT/'tests/fixtures/references/brickcolor-reference.json').read_text())


@unittest.skipUnless(motion.RUST_HOST.is_file(),'build the persistent worker first')
class BrickColorCompatTests(unittest.TestCase):
    setUp=motion.MotionMathTests.setUp
    execute=motion.MotionMathTests.execute

    def test_all_128_palette_indices_match_the_published_studio_palette(self):
        expected=','.join(str(value) for value in REFERENCE['palette'])
        self.execute('local expected={'+expected+'''}
local unique={}
for i,number in ipairs(expected) do
 local color=BrickColor.palette(i-1)
 assert(typeof(color)=="BrickColor" and color.Number==number,"palette index "..(i-1))
 assert(color==BrickColor.new(number))
 assert(not unique[number]);unique[number]=true
end
assert(BrickColor.palette(70).Name=="Gold")
''')

    def test_named_constructors_and_unknown_value_fallbacks(self):
        result=self.execute('''
local expected={White=1,Black=26,Gray=194,DarkGray=199,Red=21,Yellow=24,Green=28,Blue=23}
for name,number in pairs(expected)do
 assert(BrickColor[name]().Number==number,name)
end
for _,value in ipairs({-1,4,999,1033,65536,1e100,"unknown color","bright red","White\\0ignored"})do
 assert(BrickColor.new(value)==BrickColor.Gray())
end
return BrickColor.Green().Name,BrickColor.Gray().Name
''')
        self.assertEqual(result['values'],['Dark green','Medium stone grey'])

    def test_rgb_matching_uses_absolute_distance_over_the_full_catalog(self):
        colors=REFERENCE['colors']
        rng=random.Random(20261103)
        probes=[[rng.random() for _ in range(3)] for _ in range(160)]
        probes.extend([[0,0,0],[1,1,1],[1,0,0],[.502,.734,.859],
                       [.21675735631958404,.07309946986725258,.41319812351449514]])
        cases=[]
        for rgb in probes:
            expected=min(colors,key=lambda c:sum(abs(a-b/255) for a,b in zip(rgb,c['rgb'])))['number']
            cases.append('{'+','.join(repr(value) for value in [*rgb,expected])+'}')
        self.execute('local cases={'+','.join(cases)+'''}
for i,c in ipairs(cases)do
 local numeric=BrickColor.new(c[1],c[2],c[3])
 local color=BrickColor.new(Color3.new(c[1],c[2],c[3]))
 assert(numeric.Number==c[4],"nearest RGB case "..i..": "..numeric.Number)
 assert(color==numeric,"Color3 overload "..i)
end
assert(BrickColor.new(.21675735631958404,.07309946986725258,.41319812351449514).Number==308)
''')

    def test_random_draws_stay_in_palette_without_script_global_dependencies(self):
        self.execute('''
local palette={}
for i=0,127 do palette[BrickColor.palette(i).Number]=true end
local oldmath,oldrandom=math,Random
math={random=function()error("script RNG must not replace BrickColor.random")end}
Random={new=function()error("script constructor must not replace native RNG")end}
for i=1,1024 do
 local color=BrickColor.random()
 assert(typeof(color)=="BrickColor" and palette[color.Number])
 assert(color==BrickColor.new(color.Number))
end
math=oldmath;Random=oldrandom
''')

    def test_palette_validation_and_immutable_values(self):
        self.execute('''
-- Verified on a live Roblox client: out-of-range numbers and non-coercible
-- types error, but booleans coerce (true=1, false=0) and NaN coerces to 0.
for _,value in ipairs({-1,128,129,200,math.huge,-math.huge,{},Color3.new()})do
 assert(not pcall(BrickColor.palette,value))
end
assert(not pcall(BrickColor.palette))
assert(BrickColor.palette(true)==BrickColor.palette(1))
assert(BrickColor.palette(false)==BrickColor.palette(0))
assert(BrickColor.palette(0/0)==BrickColor.palette(0))
assert(not pcall(BrickColor.random,1))
-- Roblox rounds the palette index half away from zero and coerces numeric strings.
assert(BrickColor.palette(0.5)==BrickColor.palette(1))
assert(BrickColor.palette(1.5)==BrickColor.palette(2))
assert(BrickColor.palette("1")==BrickColor.palette(1))
local color=BrickColor.Red()
assert(not pcall(function()color.Number=23 end))
assert(not pcall(function()BrickColor.palette=function()end end))
-- Non-finite BrickColor.new falls back to Medium stone grey instead of erroring.
assert(BrickColor.new(0/0)==BrickColor.Gray())
assert(BrickColor.new(math.huge)==BrickColor.Gray())
''')

    def test_new_floors_numeric_palette_id(self):
        self.execute('''
assert(BrickColor.new(1.5)==BrickColor.new(1))
assert(BrickColor.new(2.7)==BrickColor.new(2))
assert(BrickColor.new(0.5)==BrickColor.Gray())
assert(BrickColor.new(0)==BrickColor.Gray())
assert(BrickColor.new(194).Number==194)
''')

    def test_palette_colors_survive_attributes_clone_and_bindable_transport(self):
        self.execute('''
local folder=Instance.new("Folder")
local color=BrickColor.palette(70)
folder:SetAttribute("Color",color)
assert(folder:GetAttribute("Color")==color)
local clone=folder:Clone()
assert(clone:GetAttribute("Color")==color)
local fn=Instance.new("BindableFunction")
fn.OnInvoke=function(payload)return payload[1],{color=payload[1]}end
local returned,nested=fn:Invoke({color})
assert(typeof(returned)=="BrickColor" and returned==color and nested.color==color)
folder:Destroy();clone:Destroy();fn:Destroy()
''')

    @unittest.skipUnless(motion.STANDALONE.is_file(),'build the standalone worker first')
    def test_standalone_and_rust_workers_share_the_new_constructors(self):
        source=(ROOT/'runtime/scripts/brickcolor_demo.luau').read_text()
        with tempfile.TemporaryDirectory(prefix='brickcolor-compat-') as directory:
            path=Path(directory)/'test.luau';path.write_text(source)
            for host in (motion.STANDALONE,motion.RUST_HOST):
                with self.subTest(host=host.name):
                    result=subprocess.run([str(host),'--source',str(path)],capture_output=True,text=True,timeout=10)
                    self.assertEqual(result.returncode,0,result.stderr)
                    body=json.loads(result.stdout)
                    self.assertTrue(body['ok'],body)
                    self.assertEqual(body['values'],[128,'Pastel Blue','Gold'])


if __name__=='__main__':unittest.main()
